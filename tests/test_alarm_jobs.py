"""Alarm use cases with fakes: counting arrivals at the API, firing, quiet period, GET /v1/alerts."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.core.alarm_jobs import CheckAlarms, ListAlerts
from signal_app.core.alarms import INCIDENT_LIMIT, SOURCE_LIMIT
from signal_app.core.ingest import IngestFeedback
from signal_app.core.normalise import NORMALISERS
from signal_app.core.query import ListFeedback
from signal_app.core.themes import ProblemItem

from .fakes import (FixedClock, InMemoryAlertStore, InMemoryApiKeyDirectory, InMemoryArrivals,
                    InMemoryFeedbackRepository, InMemoryKeyStore, InMemoryPublisher, InMemoryThemeInputs)

KEYS = InMemoryApiKeyDirectory({"key_a": ("tenant-a", "social"), "key_b": ("tenant-b", "social")})
NOW = FixedClock().now()


def post(n=1):
    return {"post_id": f"p{n}", "text": "card declined again", "created_at": "2026-07-21T11:00:00Z"}


@pytest.fixture
def system():
    arrivals, store = InMemoryArrivals(), InMemoryAlertStore()
    ingest = IngestFeedback(InMemoryPublisher(), InMemoryKeyStore(), KEYS, FixedClock(), "salt", 4096,
                            arrivals=arrivals)
    problems = [ProblemItem(tenant="tenant-a", area="payments", topic="payment_failed", market="UK",
                            customer_ref=f"c{n}", created_at=NOW - timedelta(minutes=2))
                for n in range(INCIDENT_LIMIT)]
    alarms = CheckAlarms(inputs=InMemoryThemeInputs(problems), arrivals=arrivals, store=store,
                         clock=FixedClock())
    client = TestClient(create_app(ingest, ListFeedback(InMemoryFeedbackRepository(), KEYS),
                                   list_alerts=ListAlerts(store=store, keys=KEYS)))
    return client, arrivals, alarms, store


def send(client, body, key="key_a"):
    return client.post("/v1/sources/social/feedback", content=json.dumps(body), headers={"X-Api-Key": key})


def test_duplicates_and_bad_bodies_are_counted_too(system):
    client, arrivals, _, _ = system
    assert send(client, post()).status_code == 202
    assert send(client, post()).status_code == 200          # duplicate
    assert send(client, {"post_id": "x"}).status_code == 422  # no text
    assert len(arrivals.requests) == 3


def test_requests_with_a_wrong_key_are_not_counted(system):
    client, arrivals, _, _ = system
    assert send(client, post(), key="wrong").status_code == 401
    assert arrivals.requests == []


def test_a_resend_flood_fires_the_source_alarm(system):
    client, _, alarms, _ = system
    for _ in range(SOURCE_LIMIT):
        send(client, post())                  # the same item again and again
    fired = alarms.run_frequent(NOW + timedelta(minutes=1))
    assert ("source_flood", "tenant-a|social") in [(a.alarm, a.subject) for a in fired]


def test_an_incident_fires_once_then_stays_quiet(system):
    _, _, alarms, store = system
    assert [a.alarm for a in alarms.run_frequent(NOW)] == ["incident"]
    assert alarms.run_frequent(NOW + timedelta(minutes=1)) == []   # quiet period
    assert len(store.alerts) == 1


def test_get_alerts_shows_only_the_callers_tenant(system):
    client, _, alarms, _ = system
    alarms.run_frequent(NOW)
    mine = client.get("/v1/alerts", headers={"X-Api-Key": "key_a"}).json()["items"]
    assert [a["subject"] for a in mine] == ["tenant-a|payments|payment_failed|UK"]
    assert mine[0]["details"]["customers"] == INCIDENT_LIMIT
    assert client.get("/v1/alerts", headers={"X-Api-Key": "key_b"}).json()["items"] == []


def test_get_alerts_needs_a_key(system):
    client, _, _, _ = system
    assert client.get("/v1/alerts").status_code == 401


# ---------- the estimated-time flag ----------

RCV = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("created,estimated", [("2026-07-21T11:00:00Z", False), ("yesterday", True),
                                               (None, True)])
def test_the_normaliser_says_when_the_time_is_estimated(created, estimated):
    item = NORMALISERS["social"]("t", {"post_id": "1", "text": "hi", "created_at": created}, RCV, "s")
    assert item["created_at_estimated"] is estimated
    if estimated:
        assert item["created_at"] == RCV.isoformat()
