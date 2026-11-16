"""API entry point: builds the adapters, wires them into the use cases, exposes `app`."""
from datetime import datetime, timezone

from ..adapters.http.app import create_app
from ..adapters.kafka import KafkaPublisher
from ..adapters.postgres import PostgresApiKeyDirectory, PostgresKeyStore, PostgresFeedbackRepository
from ..core.ingest import IngestFeedback
from ..core.query import ListFeedback
from ..shared import config


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def build_app():
    # API uses the restricted DATABASE_URL role (row-level security applies).
    keys = PostgresApiKeyDirectory(config.DATABASE_URL)
    ingest = IngestFeedback(publisher=KafkaPublisher(),
                            key_store=PostgresKeyStore(config.DATABASE_URL),
                            keys=keys,
                            clock=SystemClock(),
                            salt=config.CUSTOMER_SALT,
                            max_body_bytes=config.MAX_BODY_BYTES)
    list_feedback = ListFeedback(repository=PostgresFeedbackRepository(config.DATABASE_URL), keys=keys)
    return create_app(ingest=ingest, list_feedback=list_feedback)


app = build_app()
