"""Filters on GET /v1/feedback and GET /v1/themes against a real PostgreSQL: the filters run in SQL,
row-level security still keeps tenants apart, and the stored ranking filters before limit.
Skipped unless TEST_OWNER_URL and TEST_API_URL are set (see test_postgres.py)."""
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
from signal_app.core.models import FeedbackFilter
from signal_app.core.query import ListFeedback
from signal_app.core.theme_jobs import ListThemes, RecomputeThemes

from ..fakes import FixedClock, InMemoryPublisher

OWNER = os.getenv("TEST_OWNER_URL")
API = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not (OWNER and API), reason="set TEST_OWNER_URL and TEST_API_URL to run")

AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)
TENANTS = {"it-fl-a": "it_fl_key_a", "it-fl-b": "it_fl_key_b"}

# (feedback_id, tenant, channel, market, language, sentiment, kind, area, topic, customer, days back)
FEEDBACK = [
    ("it-fl-1", "it-fl-a", "support_ticket", "UK", "en", "negative", "problem", "delivery", "delay", "c1", 1),
    ("it-fl-2", "it-fl-a", "support_ticket", "DE", "de", "negative", "problem", "delivery", "delay", "c2", 2),
    ("it-fl-3", "it-fl-a", "app_store", "UK", "en", "negative", "problem", "payments", "declined", "c3", 3),
    ("it-fl-4", "it-fl-a", "app_store", "UK", "en", "negative", "problem", "payments", "declined", "c4", 3),
    ("it-fl-5", "it-fl-a", "nps_survey", "FR", "fr", "positive", "praise", "product", "quality", "c5", 4),
    ("it-fl-6", "it-fl-a", "support_ticket", "UK", "en", "negative", "problem", "delivery", "missing_parcel", "c6", 5),
    # Tenant b has items that match the same filters: they must never reach tenant a.
    ("it-fl-b1", "it-fl-b", "support_ticket", "UK", "en", "negative", "problem", "delivery", "delay", "x1", 1),
    ("it-fl-b2", "it-fl-b", "app_store", "DE", "de", "negative", "problem", "payments", "declined", "x2", 1),
]


def clean(conn):
    for table in ("feedback", "business_daily", "themes", "api_keys"):
        conn.execute(f"DELETE FROM {table} WHERE tenant_id LIKE 'it-fl-%'")
    conn.execute("DELETE FROM tenants WHERE tenant_id LIKE 'it-fl-%'")


@pytest.fixture
def client():
    with psycopg.connect(OWNER, autocommit=True) as conn:
        clean(conn)
        for tenant, key in TENANTS.items():
            conn.execute("INSERT INTO tenants VALUES (%s)", (tenant,))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,'social')",
                         (hash_api_key(key), tenant))
        for (feedback_id, tenant, channel, market, language, sentiment, kind, area, topic, customer,
             days_back) in FEEDBACK:
            created_at = AS_OF - timedelta(days=days_back)
            conn.execute("""INSERT INTO feedback (feedback_id, tenant_id, channel, customer_ref, market, language,
                                                  text, created_at, received_at, sentiment, kind, area, topic)
                            VALUES (%s, %s, %s, %s, %s, %s, 'some text', %s, %s, %s, %s, %s, %s)""",
                         (feedback_id, tenant, channel, customer, market, language, created_at, created_at,
                          sentiment, kind, area, topic))

        keys = PostgresApiKeyDirectory(API)
        # The scheduler's run stores the ranking of both tenants (the stored ranking the filters read).
        RecomputeThemes(inputs=PostgresThemeInputs(OWNER), store=PostgresThemeStore(OWNER),
                        clock=FixedClock()).run(AS_OF)
        list_themes = ListThemes(store=PostgresThemeStore(API), inputs=PostgresThemeInputs(API), keys=keys,
                                 clock=FixedClock())
        ingest = IngestFeedback(InMemoryPublisher(), PostgresKeyStore(API), keys, FixedClock(), "salt", 4096)
        yield TestClient(create_app(ingest, ListFeedback(PostgresFeedbackRepository(API), keys), list_themes))
        clean(conn)


def ids(client, path, tenant="it-fl-a"):
    response = client.get(path, headers={"X-Api-Key": TENANTS[tenant]})
    assert response.status_code == 200
    found = []
    for item in response.json()["items"]:
        if "feedback_id" in item:
            found.append(item["feedback_id"])
        else:
            found.append(item["theme_id"])
    return found


# ---------- feedback ----------

def test_without_filters_feedback_is_listed_as_before(client):
    assert ids(client, "/v1/feedback") == ["it-fl-1", "it-fl-2", "it-fl-3", "it-fl-4", "it-fl-5", "it-fl-6"]


@pytest.mark.parametrize("query, expected", [
    ("?area=payments", ["it-fl-3", "it-fl-4"]),
    ("?topic=missing_parcel", ["it-fl-6"]),
    ("?channel=nps_survey", ["it-fl-5"]),
    ("?market=DE", ["it-fl-2"]),
    ("?sentiment=positive", ["it-fl-5"]),
    ("?kind=praise", ["it-fl-5"]),
    ("?language=fr", ["it-fl-5"]),
    ("?area=delivery&topic=delay", ["it-fl-1", "it-fl-2"]),          # the feedback behind a theme
    ("?area=delivery&topic=delay&market=UK", ["it-fl-1"]),
    ("?area=nonsense", []),
])
def test_feedback_filters_run_in_sql(client, query, expected):
    assert ids(client, "/v1/feedback" + query) == expected


def test_feedback_filters_are_applied_before_limit(client):
    # Newest UK items overall are 1 and 3; the newest UK delivery items are 1 and 6.
    assert ids(client, "/v1/feedback?market=UK&area=delivery&limit=2") == ["it-fl-1", "it-fl-6"]


def test_feedback_filters_keep_tenants_apart(client):
    assert ids(client, "/v1/feedback?area=delivery&topic=delay") == ["it-fl-1", "it-fl-2"]
    assert ids(client, "/v1/feedback?area=delivery&topic=delay", tenant="it-fl-b") == ["it-fl-b1"]
    assert ids(client, "/v1/feedback?market=DE", tenant="it-fl-b") == ["it-fl-b2"]


def test_the_repository_never_returns_another_tenants_rows_even_when_they_match(client):
    # Straight to the adapter with the restricted role: row-level security, not the HTTP layer,
    # keeps tenant b's matching rows out.
    found = PostgresFeedbackRepository(API).list("it-fl-a", 50, None, FeedbackFilter(area="payments"))
    feedback_ids = []
    for feedback in found:
        feedback_ids.append(feedback.feedback_id)
    assert feedback_ids == ["it-fl-3", "it-fl-4"]


# ---------- themes (stored ranking) ----------

def test_without_filters_the_stored_ranking_is_listed_as_before(client):
    assert ids(client, "/v1/themes") == ["it-fl-a|delivery|delay", "it-fl-a|payments|declined",
                                         "it-fl-a|delivery|missing_parcel"]


def test_area_filter_on_the_stored_ranking(client):
    assert ids(client, "/v1/themes?area=delivery") == ["it-fl-a|delivery|delay",
                                                       "it-fl-a|delivery|missing_parcel"]


def test_area_filter_is_applied_before_limit(client):
    # Overall the second theme is payments; the second delivery theme is missing_parcel.
    assert ids(client, "/v1/themes?area=delivery&limit=2") == ["it-fl-a|delivery|delay",
                                                               "it-fl-a|delivery|missing_parcel"]
    assert ids(client, "/v1/themes?market=UK&limit=1") == ["it-fl-a|delivery|delay"]


def test_market_filter_uses_the_customers_by_market_keys(client):
    assert ids(client, "/v1/themes?market=DE") == ["it-fl-a|delivery|delay"]
    response = client.get("/v1/themes?market=DE", headers={"X-Api-Key": TENANTS["it-fl-a"]})
    [theme] = response.json()["items"]
    assert theme["customers_by_market"] == {"DE": 1, "UK": 1}     # all markets, not just DE
    assert theme["problem_customers"] == 2


def test_theme_filters_keep_tenants_apart(client):
    assert ids(client, "/v1/themes?area=payments&market=DE") == []
    assert ids(client, "/v1/themes?area=payments&market=DE", tenant="it-fl-b") == ["it-fl-b|payments|declined"]


def test_a_theme_filter_that_matches_nothing_still_shows_the_ranking_date(client):
    response = client.get("/v1/themes?area=nonsense", headers={"X-Api-Key": TENANTS["it-fl-a"]})
    body = response.json()
    assert body["items"] == []
    assert body["as_of"] == "2026-10-19T00:00:00+00:00"


def test_theme_filters_with_as_of(client):
    assert ids(client, "/v1/themes?as_of=2026-10-19&area=delivery&limit=1") == ["it-fl-a|delivery|delay"]
    assert ids(client, "/v1/themes?as_of=2026-10-19&market=UK") == ["it-fl-a|delivery|delay",
                                                                   "it-fl-a|payments|declined",
                                                                   "it-fl-a|delivery|missing_parcel"]
