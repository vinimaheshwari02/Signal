"""API entry point: builds the adapters, wires them into the use cases, exposes `app`."""
from ..adapters.clock import SystemClock
from ..adapters.http.app import create_app
from ..adapters.kafka import KafkaPublisher
from ..adapters.postgres import (PostgresAlertStore, PostgresApiKeyDirectory, PostgresArrivalCounter,
                                 PostgresFeedbackRepository, PostgresKeyStore, PostgresThemeInputs,
                                 PostgresThemeStore)
from ..core.alarm_jobs import ListAlerts
from ..core.ingest import IngestFeedback
from ..core.query import ListFeedback
from ..core.theme_jobs import ListThemes
from ..shared import config


def build_app():
    # API uses the restricted DATABASE_URL role (row-level security applies).
    keys = PostgresApiKeyDirectory(config.DATABASE_URL)
    clock = SystemClock()
    ingest = IngestFeedback(publisher=KafkaPublisher(),
                            key_store=PostgresKeyStore(config.DATABASE_URL),
                            keys=keys,
                            clock=clock,
                            salt=config.CUSTOMER_SALT,
                            max_body_bytes=config.MAX_BODY_BYTES,
                            arrivals=PostgresArrivalCounter(config.DATABASE_URL))
    list_feedback = ListFeedback(repository=PostgresFeedbackRepository(config.DATABASE_URL), keys=keys)
    list_themes = ListThemes(store=PostgresThemeStore(config.DATABASE_URL),
                             inputs=PostgresThemeInputs(config.DATABASE_URL),
                             keys=keys,
                             clock=clock)
    list_alerts = ListAlerts(store=PostgresAlertStore(config.DATABASE_URL), keys=keys)
    return create_app(ingest=ingest, list_feedback=list_feedback, list_themes=list_themes,
                      list_alerts=list_alerts)


app = build_app()
