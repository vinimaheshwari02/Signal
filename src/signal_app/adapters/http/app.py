"""HTTP adapter: thin FastAPI routes over the use cases."""
import logging
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...core import errors
from ...core.ingest import IngestFeedback
from ...core.query import ListFeedback

log = logging.getLogger("signal.api")

STATUS = {errors.Unauthorized: 401, errors.Forbidden: 403, errors.UnknownChannel: 404,
          errors.PayloadTooLarge: 413, errors.BadJson: 400}


def err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(ingest: IngestFeedback, list_feedback: ListFeedback) -> FastAPI:
    app = FastAPI(title="Signal", version="0.1.0")

    @app.exception_handler(HTTPException)
    async def http_error(_, exc: HTTPException):
        return err(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc: RequestValidationError):
        return err(422, "invalid query parameters")

    @app.exception_handler(Exception)
    async def unexpected(_, exc: Exception):
        # Bad input must never cause a 5xx; real outages are reported as 503.
        log.exception("unexpected error")
        return err(503, "temporarily unavailable")

    def business_error(status: int):
        async def handler(_, exc: Exception):
            return err(status, str(exc))
        return handler

    for cls, status in STATUS.items():
        app.add_exception_handler(cls, business_error(status))

    @app.exception_handler(errors.Rejected)
    async def rejected(_, exc: errors.Rejected):
        return err(422, exc.reason)

    @app.exception_handler(errors.PublishError)
    async def publish_failed(_, exc: errors.PublishError):
        return err(503, "temporarily unavailable, please retry")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/sources/{channel}/feedback")
    async def ingest_route(channel: str, request: Request,
                           x_api_key: str | None = Header(default=None),
                           idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key")):
        # Cheap checks (channel, key) come first in the use case, as before; the body is only read here.
        raw = await request.body()
        result = ingest.run(channel, x_api_key, raw, idempotency_key_header)
        status_code = 200 if result.status == "duplicate" else 202
        return JSONResponse({"feedback_id": result.feedback_id, "status": result.status},
                            status_code=status_code)

    @app.get("/v1/feedback")
    def list_route(x_api_key: str | None = Header(default=None),
                   limit: int = Query(50, ge=1, le=200),
                   before: datetime | None = None):
        """Newest first. Row-level security limits the rows to the caller's tenant."""
        rows = list_feedback.run(x_api_key, limit, before)
        return {"items": [{"feedback_id": f.feedback_id, "channel": f.channel, "market": f.market,
                           "language": f.language, "text": f.text,
                           "created_at": f.created_at.isoformat(),
                           "received_at": f.received_at.isoformat()} for f in rows]}

    return app
