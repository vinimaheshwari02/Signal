"""Alarms against a real PostgreSQL: the API role counting arrivals, alerts per tenant, the quiet
period across runs, and the estimated-time flag being stored. Skipped unless TEST_OWNER_URL and
TEST_API_URL are set (see test_postgres.py)."""
import json
import os
from datetime import timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.adapters.postgres import (PostgresAlertStore, PostgresApiKeyDirectory, PostgresArrivalCounter,
                                          PostgresFeedbackRepository, PostgresKeyStore, PostgresThemeInputs)
from signal_app.core.alarm_jobs import CheckAlarms, ListAlerts
from signal_app.core.alarms import SOURCE_LIMIT
from signal_app.core.ids import hash_api_key
from signal_app.core.ingest import IngestFeedback
from signal_app.core.process import ProcessFeedback
from signal_app.core.query import ListFeedback

from ..fakes import FixedClock, InMemoryPublisher

OWNER = os.getenv("TEST_OWNER_URL")
API = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not (OWNER and API), reason="set TEST_OWNER_URL and TEST_API_URL to run")

TENANTS = {"it-al-a": "it_al_key_a", "it-al-b": "it_al_key_b"}
NOW = FixedClock().now()


def clean(conn):
    for table in ("feedback", "arrivals", "alerts", "idempotency_keys", "api_keys"):
        conn.execute(f"DELETE FROM {table} WHERE tenant_id LIKE 'it-al-%'")
    conn.execute("DELETE FROM tenants WHERE tenant_id LIKE 'it-al-%'")


@pytest.fixture
def system():
    with psycopg.connect(OWNER, autocommit=True) as conn:
        clean(conn)
        for tenant, key in TENANTS.items():
            conn.execute("INSERT INTO tenants VALUES (%s)", (tenant,))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,'social')",
                         (hash_api_key(key), tenant))
        keys = PostgresApiKeyDirectory(API)
        publisher = InMemoryPublisher()
        ingest = IngestFeedback(publisher, PostgresKeyStore(API), keys, FixedClock(), "salt", 4096,
                                arrivals=PostgresArrivalCounter(API))   # the API role writes the counts
        app = create_app(ingest, ListFeedback(PostgresFeedbackRepository(API), keys),
                         list_alerts=ListAlerts(store=PostgresAlertStore(API), keys=keys))
        alarms = CheckAlarms(inputs=PostgresThemeInputs(OWNER), arrivals=PostgresArrivalCounter(OWNER),
                             store=PostgresAlertStore(OWNER), clock=FixedClock())
        yield TestClient(app), alarms, publisher
        clean(conn)


def send(client, body, tenant="it-al-a"):
    return client.post("/v1/sources/social/feedback", content=json.dumps(body),
                       headers={"X-Api-Key": TENANTS[tenant]})


def test_a_resend_flood_fires_once_and_only_the_tenant_sees_it(system):
    client, alarms, _ = system
    for _ in range(SOURCE_LIMIT):
        send(client, {"post_id": "same", "text": "late again"})   # one new, the rest duplicates
    fired = alarms.run_frequent(NOW + timedelta(minutes=1))
    assert [(a.alarm, a.subject) for a in fired] == [("source_flood", "it-al-a|social")]
    assert alarms.run_frequent(NOW + timedelta(minutes=2)) == []   # quiet period, read from the table

    mine = client.get("/v1/alerts", headers={"X-Api-Key": TENANTS["it-al-a"]}).json()["items"]
    assert [a["subject"] for a in mine] == ["it-al-a|social"]
    assert mine[0]["details"]["requests"] == SOURCE_LIMIT
    assert client.get("/v1/alerts", headers={"X-Api-Key": TENANTS["it-al-b"]}).json()["items"] == []


def test_the_estimated_time_flag_is_stored(system):
    client, _, publisher = system
    send(client, {"post_id": "e1", "text": "late", "created_at": "yesterday"})
    ProcessFeedback(PostgresFeedbackRepository(OWNER)).run(json.dumps(publisher.messages[0]))
    with psycopg.connect(OWNER) as conn:
        [estimated] = conn.execute("SELECT created_at_estimated FROM feedback WHERE tenant_id = 'it-al-a'").fetchone()
    assert estimated is True
