"""Tests against a real PostgreSQL (the migration, the SQL, idempotency and row-level security).

They are skipped unless two environment variables are set, for example with `docker compose up -d postgres`:
    export TEST_OWNER_URL=postgresql://signal:signal@localhost:5432/signal
    export TEST_API_URL=postgresql://signal_api:signal_api@localhost:5432/signal
    uv run pytest tests/integration
Kafka is replaced by an in-memory publisher here; the tests clean up the rows they create.
"""
import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.adapters.postgres import PostgresApiKeyDirectory, PostgresFeedbackRepository, PostgresKeyStore
from signal_app.core.ids import hash_api_key
from signal_app.core.ingest import IngestFeedback
from signal_app.core.process import ProcessFeedback
from signal_app.core.query import ListFeedback

from ..fakes import FixedClock, InMemoryPublisher

OWNER = os.getenv("TEST_OWNER_URL")
API = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not (OWNER and API), reason="set TEST_OWNER_URL and TEST_API_URL to run")

KEY_A, KEY_B = "it_key_a", "it_key_b"
TICKET = {"ticket": {"id": "IT-1", "created": 1784597786000, "description": "Password reset email never arrives.",
                     "requester": {"customer_ref": "C1", "locale": "en-GB"}}}


@pytest.fixture
def db():
    with psycopg.connect(OWNER, autocommit=True) as conn:
        def clean():
            conn.execute("DELETE FROM feedback WHERE tenant_id LIKE 'it-%'")
            conn.execute("DELETE FROM idempotency_keys WHERE tenant_id LIKE 'it-%'")
            conn.execute("DELETE FROM api_keys WHERE tenant_id LIKE 'it-%'")
            conn.execute("DELETE FROM tenants WHERE tenant_id LIKE 'it-%'")
        clean()
        for tenant, key in (("it-a", KEY_A), ("it-b", KEY_B)):
            conn.execute("INSERT INTO tenants VALUES (%s)", (tenant,))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,'support_ticket')",
                         (hash_api_key(key), tenant))
        yield conn
        clean()


@pytest.fixture
def system(db):
    publisher = InMemoryPublisher()
    keys = PostgresApiKeyDirectory(API)
    ingest = IngestFeedback(publisher, PostgresKeyStore(API), keys, FixedClock(), "salt", 4096)
    app = create_app(ingest, ListFeedback(PostgresFeedbackRepository(API), keys))
    return TestClient(app), publisher, ProcessFeedback(PostgresFeedbackRepository(OWNER))


def post(client, key, body=TICKET):
    return client.post("/v1/sources/support_ticket/feedback", content=json.dumps(body), headers={"X-Api-Key": key})


def test_post_then_worker_then_get_with_real_postgres(system):
    client, publisher, process = system
    r = post(client, KEY_A)
    assert r.status_code == 202
    process.run(json.dumps(publisher.messages[0]))                    # the worker's step
    items = client.get("/v1/feedback", headers={"X-Api-Key": KEY_A}).json()["items"]
    assert [i["feedback_id"] for i in items] == [r.json()["feedback_id"]]
    assert items[0]["market"] == "UK" and items[0]["language"] == "en"


def test_sending_the_same_item_twice_gives_200_the_second_time(system):
    client, publisher, _ = system
    assert post(client, KEY_A).status_code == 202
    second = post(client, KEY_A)
    assert second.status_code == 200 and second.json()["status"] == "duplicate"
    assert len(publisher.messages) == 1


def test_a_failed_publish_saves_no_key_so_a_retry_is_accepted(system, db):
    client, publisher, _ = system
    publisher.fail = True
    assert post(client, KEY_A).status_code == 503
    assert db.execute("SELECT count(*) FROM idempotency_keys WHERE tenant_id = 'it-a'").fetchone()[0] == 0
    publisher.fail = False
    assert post(client, KEY_A).status_code == 202


def test_each_tenant_only_sees_its_own_feedback(system, db):
    client, publisher, process = system
    post(client, KEY_A)
    process.run(json.dumps(publisher.messages[0]))
    assert len(client.get("/v1/feedback", headers={"X-Api-Key": KEY_A}).json()["items"]) == 1
    assert client.get("/v1/feedback", headers={"X-Api-Key": KEY_B}).json()["items"] == []


def test_row_level_security_hides_rows_even_without_a_where_clause(system, db):
    client, publisher, process = system
    post(client, KEY_A)
    process.run(json.dumps(publisher.messages[0]))
    assert db.execute("SELECT count(*) FROM feedback WHERE tenant_id = 'it-a'").fetchone()[0] == 1   # owner sees it
    with psycopg.connect(API) as conn:                                                              # API role: nothing set
        assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0


def test_the_api_role_cannot_write_or_change_feedback(db):
    with psycopg.connect(API, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO feedback (feedback_id, tenant_id, channel, text, created_at, received_at) "
                         "VALUES ('x','it-a','social','t', now(), now())")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM feedback")


def test_saving_the_same_feedback_twice_keeps_one_row(db):
    repo = PostgresFeedbackRepository(OWNER)
    msg = {"feedback_id": "fb_it", "tenant_id": "it-a", "channel": "support_ticket", "source_id": "IT-9",
           "customer_ref": None, "market": "UK", "language": "en", "text": "hello", "created_at": "2026-07-21T01:00:00+00:00",
           "received_at": "2026-07-21T01:00:01+00:00", "sentiment": "neutral", "kind": "other", "area": "general", "topic": "other"}
    repo.save(msg)
    repo.save(msg)
    assert db.execute("SELECT count(*) FROM feedback WHERE feedback_id = 'fb_it'").fetchone()[0] == 1


def test_the_key_store_survives_a_parallel_save(db):
    store = PostgresKeyStore(API)
    store.save("k_it", "it-a", "fb_x")
    store.save("k_it", "it-a", "fb_x")   # a second request saving the same key must not raise
    assert store.get("k_it") == "fb_x"
