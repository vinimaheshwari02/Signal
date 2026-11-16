"""HTTP adapter: thin FastAPI routes over the use cases."""
import logging
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...core import errors
from ...core.ingest import IngestFeedback
from ...core.models import Feedback
from ...core.query import ListFeedback

log = logging.getLogger("signal.api")

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


def create_app(ingest: IngestFeedback, list_feedback: ListFeedback) -> FastAPI:
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
        # Read the whole body, then let the use case check channel, key, size and JSON.
        raw = await request.body()
        result = ingest.run(channel, x_api_key, raw, idempotency_key_header)
        if result.status == "duplicate":
            status_code = 200
        else:
            status_code = 202  # accepted: the worker stores it shortly
        return JSONResponse({"feedback_id": result.feedback_id, "status": result.status},
                            status_code=status_code)

    @app.get("/v1/feedback")
    def list_route(x_api_key: str | None = Header(default=None),
                   limit: int = Query(50, ge=1, le=200),
                   before: datetime | None = None):
        """Newest first. Row-level security limits the rows to the caller's tenant."""
        items = []
        for feedback in list_feedback.run(x_api_key, limit, before):
            items.append(feedback_to_json(feedback))
        return {"items": items}

    return app
