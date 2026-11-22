"""HTTP adapter: thin FastAPI routes over the use cases."""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...core import errors
from ...core.alarm_jobs import ListAlerts
from ...core.alarms import Alert
from ...core.ingest import IngestFeedback
from ...core.models import Feedback, FeedbackFilter
from ...core.query import ListFeedback
from ...core.theme_jobs import ListThemes
from ...core.themes import RankedThemes, Theme

log = logging.getLogger("signal.api")

# Filter values are short words such as "delivery" or "UK". This limit only stops absurd input
# (422); an unknown value of normal length is fine and simply matches nothing.
MAX_FILTER_LENGTH = 50

STATUS = {errors.Unauthorized: 401, errors.Forbidden: 403, errors.UnknownChannel: 404,
          errors.PayloadTooLarge: 413, errors.BadJson: 400}


def error_response(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def feedback_to_json(feedback: Feedback) -> dict:
    """One stored item as it appears in the GET response."""
    return {"feedback_id": feedback.feedback_id, "channel": feedback.channel,
            "market": feedback.market, "language": feedback.language, "text": feedback.text,
            "created_at": feedback.created_at.isoformat(),
            "received_at": feedback.received_at.isoformat(),
            "sentiment": feedback.sentiment, "kind": feedback.kind, "area": feedback.area,
            "topic": feedback.topic}


def theme_to_json(theme: Theme) -> dict:
    """One ranked theme as it appears in the GET /v1/themes response."""
    return {"theme_id": theme.theme_id, "area": theme.area, "topic": theme.topic,
            "score": theme.score, "problem_customers": theme.problem_customers,
            "last_week_customers": theme.last_week_customers, "trend": theme.trend,
            "customers_by_market": theme.customers_by_market, "evidence": theme.evidence}


def ranking_to_json(ranked: RankedThemes | None) -> dict:
    if ranked is None:  # the scheduler has not run yet, or this tenant has no problems
        return {"as_of": None, "computed_at": None, "items": []}
    items = []
    for theme in ranked.themes:
        items.append(theme_to_json(theme))
    return {"as_of": ranked.as_of.isoformat(), "computed_at": ranked.computed_at.isoformat(),
            "items": items}


def alert_to_json(alert: Alert) -> dict:
    return {"alarm": alert.alarm, "subject": alert.subject, "fired_at": alert.fired_at.isoformat(),
            "details": alert.details}


async def read_capped(request: Request, limit: int) -> bytes:
    """The body, but stop reading after `limit` bytes."""
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) >= limit:
            break
    return bytes(received[:limit])


def create_app(ingest: IngestFeedback, list_feedback: ListFeedback,
               list_themes: ListThemes | None = None, list_alerts: ListAlerts | None = None) -> FastAPI:
    app = FastAPI(title="Signal", version="0.1.0")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc: HTTPException):
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc: RequestValidationError):
        return error_response(422, "invalid query parameters")

    @app.exception_handler(Exception)
    async def unexpected(request, exc: Exception):
        # Bad input must never cause a 5xx; real outages are reported as 503.
        log.exception("unexpected error")
        return error_response(503, "temporarily unavailable")

    async def business_error(request, exc: Exception):
        """One handler for the errors in STATUS: look up the status code for this kind of error."""
        return error_response(STATUS[type(exc)], str(exc))

    for error_class in STATUS:
        app.add_exception_handler(error_class, business_error)

    @app.exception_handler(errors.Rejected)
    async def rejected(request, exc: errors.Rejected):
        return error_response(422, exc.reason)

    @app.exception_handler(errors.PublishError)
    async def publish_failed(request, exc: errors.PublishError):
        return error_response(503, "temporarily unavailable, please retry")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/sources/{channel}/feedback")
    async def ingest_route(channel: str, request: Request,
                           x_api_key: str | None = Header(default=None),
                           idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key")):
        # Read at most one byte more than allowed: enough for the use case to answer 413,
        # without ever holding a huge body in memory.
        raw = await read_capped(request, ingest.max_body_bytes + 1)
        # ingest.run waits for Postgres and Kafka. Run it on a worker thread, so that while one
        # request waits, the event loop keeps serving the others.
        result = await run_in_threadpool(ingest.run, channel, x_api_key, raw, idempotency_key_header)
        if result.status == "duplicate":
            status_code = 200
        else:
            status_code = 202  # accepted: the worker stores it shortly
        return JSONResponse({"feedback_id": result.feedback_id, "status": result.status},
                            status_code=status_code)

    @app.get("/v1/feedback")
    def list_route(x_api_key: str | None = Header(default=None),
                   limit: int = Query(50, ge=1, le=200),
                   before: datetime | None = None,
                   area: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   topic: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   channel: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   market: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   sentiment: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   kind: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                   language: str | None = Query(None, max_length=MAX_FILTER_LENGTH)):
        """Newest first. Row-level security limits the rows to the caller's tenant.
        Optional exact-match filters, combined with AND; ?area=delivery&topic=delay gives the
        feedback behind one theme."""
        filters = FeedbackFilter(area=area, topic=topic, channel=channel, market=market,
                                 sentiment=sentiment, kind=kind, language=language)
        items = []
        for feedback in list_feedback.run(x_api_key, limit, before, filters):
            items.append(feedback_to_json(feedback))
        return {"items": items}

    if list_themes is not None:
        @app.get("/v1/themes")
        def themes_route(x_api_key: str | None = Header(default=None),
                         limit: int = Query(20, ge=1, le=100),
                         as_of: datetime | None = None,
                         area: str | None = Query(None, max_length=MAX_FILTER_LENGTH),
                         market: str | None = Query(None, max_length=MAX_FILTER_LENGTH)):
            """Highest impact first. Without as_of: the latest ranking from the scheduler.
            With as_of (e.g. 2026-09-22): the ranking for the week before that moment.
            area / market keep only matching themes (before limit); a theme's numbers still
            cover all its markets."""
            if as_of is not None and as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)  # a date or time without zone is UTC
            ranked = list_themes.run(x_api_key, limit, as_of, area=area, market=market)
            return ranking_to_json(ranked)

    if list_alerts is not None:
        @app.get("/v1/alerts")
        def alerts_route(x_api_key: str | None = Header(default=None),
                         limit: int = Query(50, ge=1, le=200)):
            """This tenant's alarms, newest first (ADR 0008)."""
            items = []
            for alert in list_alerts.run(x_api_key, limit):
                items.append(alert_to_json(alert))
            return {"items": items}

    return app
