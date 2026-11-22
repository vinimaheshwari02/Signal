"""Themes against a real PostgreSQL: business data, the scheduler's recompute, GET /v1/themes and
tenant isolation. Skipped unless TEST_OWNER_URL and TEST_API_URL are set (see test_postgres.py)."""
import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.adapters.postgres import (PostgresApiKeyDirectory, PostgresFeedbackRepository, PostgresKeyStore,
                                          PostgresThemeInputs, PostgresThemeStore)
from signal_app.core.ids import hash_api_key
from signal_app.core.ingest import IngestFeedback
from signal_app.core.query import ListFeedback
from signal_app.core.theme_jobs import ListThemes, RecomputeThemes

from ..fakes import FixedClock, InMemoryPublisher

OWNER = os.getenv("TEST_OWNER_URL")
API = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not (OWNER and API), reason="set TEST_OWNER_URL and TEST_API_URL to run")

AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)
TENANTS = {"it-th-a": "it_th_key_a", "it-th-b": "it_th_key_b"}


def clean(conn):
    for table in ("feedback", "business_daily", "themes", "api_keys"):
        conn.execute(f"DELETE FROM {table} WHERE tenant_id LIKE 'it-th-%'")
    conn.execute("DELETE FROM tenants WHERE tenant_id LIKE 'it-th-%'")


@pytest.fixture
def client():
    with psycopg.connect(OWNER, autocommit=True) as conn:
        clean(conn)
        for tenant, key in TENANTS.items():
            conn.execute("INSERT INTO tenants VALUES (%s)", (tenant,))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,'social')",
                         (hash_api_key(key), tenant))
        # Tenant a: 3 customers with late deliveries in the UK; late rate doubled this week.
        for number, customer in enumerate(["c1", "c2", "c2", "c3"]):
            conn.execute("""INSERT INTO feedback (feedback_id, tenant_id, channel, customer_ref, market, text,
                                                  created_at, received_at, kind, area, topic, sentiment)
                            VALUES (%s, 'it-th-a', 'social', %s, 'UK', 'late', %s, %s, 'problem', 'delivery',
                                    'delay', 'negative')""",
                         (f"it-th-{number}", customer, AS_OF - timedelta(days=1), AS_OF - timedelta(days=1)))
        # Tenant b: one problem, nothing else.
        conn.execute("""INSERT INTO feedback (feedback_id, tenant_id, channel, customer_ref, market, text,
                                              created_at, received_at, kind, area, topic, sentiment)
                        VALUES ('it-th-b1', 'it-th-b', 'social', 'x', 'UK', 'slow search', %s, %s, 'problem',
                                'search', 'relevance', 'negative')""", (AS_OF - timedelta(days=2),) * 2)
        for days_back in range(1, 36):
            late = 100 if days_back <= 7 else 50
            conn.execute("""INSERT INTO business_daily VALUES ('it-th-a', 'UK', %s, 100, 5000, 1000, 10,
                                                                1000, %s, 5, 900)""",
                         (AS_OF.date() - timedelta(days=days_back), late))

        keys = PostgresApiKeyDirectory(API)
        RecomputeThemes(inputs=PostgresThemeInputs(OWNER), store=PostgresThemeStore(OWNER),
                        clock=FixedClock()).run(AS_OF)
        list_themes = ListThemes(store=PostgresThemeStore(API), inputs=PostgresThemeInputs(API), keys=keys,
                                 clock=FixedClock())
        ingest = IngestFeedback(InMemoryPublisher(), PostgresKeyStore(API), keys, FixedClock(), "salt", 4096)
        yield TestClient(create_app(ingest, ListFeedback(PostgresFeedbackRepository(API), keys), list_themes))
        clean(conn)


def themes(client, tenant, query=""):
    response = client.get("/v1/themes" + query, headers={"X-Api-Key": TENANTS[tenant]})
    assert response.status_code == 200
    return response.json()


def test_the_stored_ranking_uses_customers_and_business_numbers(client):
    body = themes(client, "it-th-a")
    assert body["as_of"] == "2026-10-19T00:00:00+00:00"
    [theme] = body["items"]
    assert theme["theme_id"] == "it-th-a|delivery|delay"
    assert theme["problem_customers"] == 3
    assert theme["score"] == 6.0                       # 3 customers x late rate twice as high
    assert theme["evidence"][0]["market"] == "UK"
    assert theme["evidence"][0]["times_worse"] == 2.0


def test_each_tenant_only_sees_its_own_themes(client):
    assert [t["theme_id"] for t in themes(client, "it-th-b")["items"]] == ["it-th-b|search|relevance"]


def test_as_of_computes_with_the_api_role_and_stays_within_the_tenant(client):
    # Computed on the spot by the restricted role: row-level security must still allow the
    # tenant's own feedback and business numbers, and nothing else.
    body = themes(client, "it-th-a", "?as_of=2026-10-19")
    assert [t["theme_id"] for t in body["items"]] == ["it-th-a|delivery|delay"]
    assert body["items"][0]["score"] == 6.0


def test_the_api_role_cannot_write_themes_or_business_numbers():
    with psycopg.connect(API, autocommit=True) as conn:
        for sql in ("DELETE FROM themes", "INSERT INTO business_daily (tenant_id, market, day) VALUES ('x','UK','2026-01-01')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)
