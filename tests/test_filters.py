"""Optional filters on GET /v1/feedback and GET /v1/themes, with in-memory fakes."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.core.ingest import IngestFeedback
from signal_app.core.models import FeedbackFilter
from signal_app.core.query import ListFeedback
from signal_app.core.theme_jobs import ListThemes, keep_matching_themes
from signal_app.core.themes import ProblemItem, RankedThemes, Theme

from .fakes import (FixedClock, InMemoryApiKeyDirectory, InMemoryFeedbackRepository, InMemoryKeyStore,
                    InMemoryPublisher, InMemoryThemeInputs, InMemoryThemeStore)

KEYS = InMemoryApiKeyDirectory({"key_a": ("tenant-a", "social"), "key_b": ("tenant-b", "social")})
HEADERS_A = {"X-Api-Key": "key_a"}
AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)


# ---------- feedback ----------

def feedback_row(feedback_id, minutes_ago, tenant="tenant-a", channel="support_ticket", market="UK",
                 language="en", sentiment="negative", kind="problem", area="delivery", topic="delay"):
    """One stored feedback row, as the worker saves it."""
    created_at = (AS_OF - timedelta(minutes=minutes_ago)).isoformat()
    return {"feedback_id": feedback_id, "tenant_id": tenant, "channel": channel, "market": market,
            "language": language, "text": "some text", "created_at": created_at,
            "received_at": created_at, "sentiment": sentiment, "kind": kind, "area": area,
            "topic": topic}


ROWS = [
    feedback_row("fb_1", minutes_ago=1),                                          # delivery / delay, UK
    feedback_row("fb_2", minutes_ago=2, market="DE", language="de"),              # delivery / delay, DE
    feedback_row("fb_3", minutes_ago=3, topic="missing_parcel"),                  # delivery, other topic
    feedback_row("fb_4", minutes_ago=4, area="payments", topic="declined", channel="app_store"),
    feedback_row("fb_5", minutes_ago=5, sentiment="positive", kind="praise", area="product",
                 topic="quality", channel="nps_survey"),
    feedback_row("fb_6", minutes_ago=6),                                          # delivery / delay, UK
    feedback_row("fb_other", minutes_ago=0, tenant="tenant-b"),                   # matches, other tenant
]


@pytest.fixture
def feedback_client():
    repo = InMemoryFeedbackRepository()
    for row in ROWS:
        repo.save(row)
    ingest = IngestFeedback(InMemoryPublisher(), InMemoryKeyStore(), KEYS, FixedClock(), "salt", 1024)
    return TestClient(create_app(ingest, ListFeedback(repo, KEYS)))


def feedback_ids(client, query=""):
    response = client.get("/v1/feedback" + query, headers=HEADERS_A)
    assert response.status_code == 200
    ids = []
    for item in response.json()["items"]:
        ids.append(item["feedback_id"])
    return ids


def test_without_filters_feedback_is_listed_as_before(feedback_client):
    assert feedback_ids(feedback_client) == ["fb_1", "fb_2", "fb_3", "fb_4", "fb_5", "fb_6"]


@pytest.mark.parametrize("query, expected", [
    ("?area=payments", ["fb_4"]),
    ("?topic=missing_parcel", ["fb_3"]),
    ("?channel=nps_survey", ["fb_5"]),
    ("?market=DE", ["fb_2"]),
    ("?sentiment=positive", ["fb_5"]),
    ("?kind=praise", ["fb_5"]),
    ("?language=de", ["fb_2"]),
])
def test_each_feedback_filter_keeps_only_matching_items(feedback_client, query, expected):
    assert feedback_ids(feedback_client, query) == expected


def test_area_and_topic_give_the_feedback_behind_a_theme(feedback_client):
    assert feedback_ids(feedback_client, "?area=delivery&topic=delay") == ["fb_1", "fb_2", "fb_6"]


def test_feedback_filters_are_combined_with_and(feedback_client):
    assert feedback_ids(feedback_client, "?area=delivery&topic=delay&market=UK") == ["fb_1", "fb_6"]


def test_feedback_filters_are_applied_before_limit(feedback_client):
    # Without filtering first, limit=2 would return fb_1 and fb_2 and then drop fb_2 (DE).
    assert feedback_ids(feedback_client, "?market=UK&topic=delay&limit=2") == ["fb_1", "fb_6"]


def test_feedback_filters_work_with_before(feedback_client):
    before = (AS_OF - timedelta(minutes=1, seconds=30)).isoformat().replace("+00:00", "Z")
    assert feedback_ids(feedback_client, "?topic=delay&before=" + before) == ["fb_2", "fb_6"]


def test_an_unknown_filter_value_returns_no_items(feedback_client):
    assert feedback_ids(feedback_client, "?area=nonsense") == []


def test_another_tenants_matching_feedback_never_appears(feedback_client):
    assert "fb_other" not in feedback_ids(feedback_client, "?area=delivery&topic=delay")


def test_an_absurdly_long_filter_value_is_422(feedback_client):
    response = feedback_client.get("/v1/feedback?area=" + "x" * 51, headers=HEADERS_A)
    assert response.status_code == 422


def test_the_use_case_without_filters_passes_an_empty_filter():
    repo = InMemoryFeedbackRepository()
    for row in ROWS:
        repo.save(row)
    list_feedback = ListFeedback(repo, KEYS)
    without = list_feedback.run("key_a", limit=10, before=None)
    with_empty = list_feedback.run("key_a", limit=10, before=None, filters=FeedbackFilter())
    assert without == with_empty
    assert len(without) == 6


# ---------- themes ----------

def theme(tenant, area, topic, score, markets):
    return Theme(tenant=tenant, theme_id=f"{tenant}|{area}|{topic}", area=area, topic=topic,
                 score=score, problem_customers=10, last_week_customers=8, trend="stable",
                 customers_by_market=markets)


STORED = RankedThemes(as_of=AS_OF, computed_at=AS_OF, themes=[
    theme("tenant-a", "payments", "declined", 90.0, {"UK": 5, "DE": 5}),
    theme("tenant-a", "delivery", "delay", 80.0, {"UK": 10}),
    theme("tenant-a", "checkout", "slow", 70.0, {"FR": 10}),
    theme("tenant-a", "delivery", "missing_parcel", 60.0, {"DE": 10}),
    theme("tenant-a", "delivery", "damaged", 50.0, {"UK": 4, "IE": 6}),
    theme("tenant-b", "delivery", "delay", 99.0, {"UK": 10}),   # another tenant
])


def problem(area, topic, market, customer, tenant="tenant-a"):
    return ProblemItem(tenant=tenant, area=area, topic=topic, market=market, customer_ref=customer,
                       created_at=AS_OF - timedelta(days=1))


# Raw problems for ?as_of=: more customers means a higher score (no business data, severity 1).
ITEMS = [problem("payments", "declined", "UK", "c1"), problem("payments", "declined", "DE", "c2"),
         problem("payments", "declined", "DE", "c3"), problem("payments", "declined", "DE", "c4"),
         problem("delivery", "delay", "UK", "c5"), problem("delivery", "delay", "UK", "c6"),
         problem("delivery", "missing_parcel", "DE", "c7"),
         problem("delivery", "delay", "UK", "c8", tenant="tenant-b")]


@pytest.fixture
def themes_client():
    store = InMemoryThemeStore()
    store.replace_all(STORED)
    list_themes = ListThemes(store=store, inputs=InMemoryThemeInputs(ITEMS), keys=KEYS, clock=FixedClock())
    ingest = IngestFeedback(InMemoryPublisher(), InMemoryKeyStore(), KEYS, FixedClock(), "salt", 1024)
    return TestClient(create_app(ingest, ListFeedback(InMemoryFeedbackRepository(), KEYS), list_themes))


def theme_ids(client, query=""):
    response = client.get("/v1/themes" + query, headers=HEADERS_A)
    assert response.status_code == 200
    ids = []
    for item in response.json()["items"]:
        ids.append(item["theme_id"])
    return ids


def test_without_filters_the_stored_ranking_is_listed_as_before(themes_client):
    assert theme_ids(themes_client) == ["tenant-a|payments|declined", "tenant-a|delivery|delay",
                                        "tenant-a|checkout|slow", "tenant-a|delivery|missing_parcel",
                                        "tenant-a|delivery|damaged"]


def test_area_filter_on_the_stored_ranking(themes_client):
    assert theme_ids(themes_client, "?area=delivery") == ["tenant-a|delivery|delay",
                                                          "tenant-a|delivery|missing_parcel",
                                                          "tenant-a|delivery|damaged"]


def test_market_filter_on_the_stored_ranking(themes_client):
    assert theme_ids(themes_client, "?market=DE") == ["tenant-a|payments|declined",
                                                      "tenant-a|delivery|missing_parcel"]


def test_area_and_market_together_on_the_stored_ranking(themes_client):
    assert theme_ids(themes_client, "?area=delivery&market=UK") == ["tenant-a|delivery|delay",
                                                                    "tenant-a|delivery|damaged"]


def test_theme_filters_are_applied_before_limit(themes_client):
    # The two highest delivery themes, not "delivery themes among the two highest overall".
    assert theme_ids(themes_client, "?area=delivery&limit=2") == ["tenant-a|delivery|delay",
                                                                  "tenant-a|delivery|missing_parcel"]


def test_market_filter_keeps_the_numbers_of_every_market(themes_client):
    response = themes_client.get("/v1/themes?market=DE", headers=HEADERS_A)
    first = response.json()["items"][0]
    assert first["score"] == 90.0
    assert first["customers_by_market"] == {"UK": 5, "DE": 5}


def test_a_filter_that_matches_nothing_still_shows_the_ranking_date(themes_client):
    body = themes_client.get("/v1/themes?area=nonsense", headers=HEADERS_A).json()
    assert body["items"] == []
    assert body["as_of"] == "2026-10-19T00:00:00+00:00"


def test_before_the_first_run_a_filter_still_returns_no_ranking():
    list_themes = ListThemes(store=InMemoryThemeStore(), inputs=InMemoryThemeInputs(), keys=KEYS,
                             clock=FixedClock())
    assert list_themes.run("key_a", limit=10, area="delivery") is None


def test_theme_filters_never_show_another_tenant(themes_client):
    assert "tenant-b|delivery|delay" not in theme_ids(themes_client, "?area=delivery&market=UK")


def test_without_filters_as_of_is_listed_as_before(themes_client):
    assert theme_ids(themes_client, "?as_of=2026-10-19") == ["tenant-a|payments|declined",
                                                             "tenant-a|delivery|delay",
                                                             "tenant-a|delivery|missing_parcel"]


def test_area_filter_with_as_of(themes_client):
    assert theme_ids(themes_client, "?as_of=2026-10-19&area=delivery") == ["tenant-a|delivery|delay",
                                                                          "tenant-a|delivery|missing_parcel"]


def test_market_filter_with_as_of(themes_client):
    assert theme_ids(themes_client, "?as_of=2026-10-19&market=UK") == ["tenant-a|payments|declined",
                                                                      "tenant-a|delivery|delay"]


def test_theme_filters_with_as_of_are_applied_before_limit(themes_client):
    assert theme_ids(themes_client, "?as_of=2026-10-19&market=DE&limit=1") == ["tenant-a|payments|declined"]
    assert theme_ids(themes_client, "?as_of=2026-10-19&area=delivery&limit=1") == ["tenant-a|delivery|delay"]


def test_keep_matching_themes_without_filters_keeps_everything():
    assert keep_matching_themes(STORED.themes, area=None, market=None) == STORED.themes


# ---------- topic filter on themes ----------

def test_area_and_topic_give_exactly_one_stored_theme(themes_client):
    assert theme_ids(themes_client, "?area=delivery&topic=delay") == ["tenant-a|delivery|delay"]


def test_topic_alone_on_the_stored_ranking(themes_client):
    assert theme_ids(themes_client, "?topic=missing_parcel") == ["tenant-a|delivery|missing_parcel"]


def test_topic_and_market_together(themes_client):
    assert theme_ids(themes_client, "?area=delivery&topic=delay&market=DE") == []   # delay has UK only
    assert theme_ids(themes_client, "?area=delivery&topic=delay&market=UK") == ["tenant-a|delivery|delay"]


def test_topic_filter_with_as_of(themes_client):
    assert theme_ids(themes_client, "?as_of=2026-10-19&area=delivery&topic=missing_parcel") == [
        "tenant-a|delivery|missing_parcel"]


def test_topic_filter_never_shows_another_tenant(themes_client):
    # tenant-b's delivery|delay scores higher, but tenant-a's key must only see its own.
    assert theme_ids(themes_client, "?area=delivery&topic=delay") == ["tenant-a|delivery|delay"]


def test_an_overlong_topic_is_rejected(themes_client):
    response = themes_client.get("/v1/themes?topic=" + "x" * 51, headers=HEADERS_A)
    assert response.status_code == 422
