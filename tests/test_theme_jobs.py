"""Theme use cases, the scheduler's run and GET /v1/themes, with in-memory fakes."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.core.errors import Unauthorized
from signal_app.core.ingest import IngestFeedback
from signal_app.core.query import ListFeedback
from signal_app.core.theme_jobs import ListThemes, RecomputeThemes, as_of_from_setting
from signal_app.core.themes import ProblemItem
from signal_app.entrypoints.scheduler import run_once

from .fakes import (FixedClock, InMemoryApiKeyDirectory, InMemoryFeedbackRepository, InMemoryKeyStore,
                    InMemoryPublisher, InMemoryThemeInputs, InMemoryThemeStore)

AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)
KEYS = InMemoryApiKeyDirectory({"key_a": ("tenant-a", "social"), "key_b": ("tenant-b", "social")})


def problem(tenant, customer, topic="delay", when=AS_OF - timedelta(days=1)):
    return ProblemItem(tenant=tenant, area="delivery", topic=topic, market="UK",
                       customer_ref=customer, created_at=when)


ITEMS = [problem("tenant-a", "c1"), problem("tenant-a", "c2"), problem("tenant-b", "c9", topic="missing_parcel"),
         # a problem a month earlier, only visible when looking back
         problem("tenant-a", "c3", topic="missing_parcel", when=AS_OF - timedelta(days=30))]


@pytest.fixture
def parts():
    inputs, store = InMemoryThemeInputs(ITEMS), InMemoryThemeStore()
    recompute = RecomputeThemes(inputs=inputs, store=store, clock=FixedClock())
    list_themes = ListThemes(store=store, inputs=inputs, keys=KEYS, clock=FixedClock())
    return recompute, list_themes, store


def test_recompute_stores_every_tenant(parts):
    recompute, _, store = parts
    recompute.run(AS_OF)
    assert {t.theme_id for t in store.ranked.themes} == {"tenant-a|delivery|delay", "tenant-b|delivery|missing_parcel"}


def test_list_returns_only_the_callers_tenant(parts):
    recompute, list_themes, _ = parts
    recompute.run(AS_OF)
    ranked = list_themes.run("key_a", limit=10)
    assert [t.theme_id for t in ranked.themes] == ["tenant-a|delivery|delay"]
    assert ranked.as_of == AS_OF


def test_list_before_the_first_run_is_empty(parts):
    _, list_themes, _ = parts
    assert list_themes.run("key_a", limit=10) is None


def test_list_with_as_of_computes_for_that_date_and_tenant(parts):
    _, list_themes, _ = parts
    ranked = list_themes.run("key_a", limit=10, as_of=AS_OF - timedelta(days=29))
    assert [t.theme_id for t in ranked.themes] == ["tenant-a|delivery|missing_parcel"]


def test_list_needs_a_valid_key(parts):
    _, list_themes, _ = parts
    with pytest.raises(Unauthorized):
        list_themes.run("wrong", limit=10)


def test_a_failed_run_keeps_the_last_good_ranking(parts, monkeypatch):
    recompute, _, store = parts
    monkeypatch.setattr("signal_app.shared.config.AS_OF", "2026-10-19")
    run_once(recompute, FixedClock())
    good = store.ranked
    store.fail = True
    run_once(recompute, FixedClock())   # must not raise: the scheduler keeps running
    assert store.ranked is good


@pytest.mark.parametrize("setting,expected", [
    ("", FixedClock().now()),
    ("2026-10-19", AS_OF),
    ("2026-10-19T12:00:00+02:00", datetime(2026, 10, 19, 10, tzinfo=timezone.utc)),
])
def test_as_of_setting(setting, expected):
    assert as_of_from_setting(setting, FixedClock().now()) == expected


# ---------- HTTP ----------

@pytest.fixture
def client(parts):
    recompute, list_themes, _ = parts
    recompute.run(AS_OF)
    ingest = IngestFeedback(InMemoryPublisher(), InMemoryKeyStore(), KEYS, FixedClock(), "salt", 1024)
    app = create_app(ingest, ListFeedback(InMemoryFeedbackRepository(), KEYS), list_themes)
    return TestClient(app)


def test_get_themes_returns_the_ranking(client):
    response = client.get("/v1/themes", headers={"X-Api-Key": "key_a"})
    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-10-19T00:00:00+00:00"
    item = body["items"][0]
    assert item["theme_id"] == "tenant-a|delivery|delay"
    assert (item["score"], item["problem_customers"], item["trend"]) == (2.0, 2, "rising")
    assert item["customers_by_market"] == {"UK": 2}


def test_get_themes_accepts_a_plain_date_for_as_of(client):
    response = client.get("/v1/themes?as_of=2026-09-20", headers={"X-Api-Key": "key_a"})
    assert response.status_code == 200
    assert response.json()["as_of"] == "2026-09-20T00:00:00+00:00"
    assert response.json()["items"][0]["topic"] == "missing_parcel"


@pytest.mark.parametrize("query,status", [("?as_of=yesterday", 422), ("?limit=0", 422), ("?limit=101", 422)])
def test_get_themes_rejects_bad_parameters(client, query, status):
    assert client.get("/v1/themes" + query, headers={"X-Api-Key": "key_a"}).status_code == status


def test_get_themes_needs_a_key(client):
    assert client.get("/v1/themes").status_code == 401
