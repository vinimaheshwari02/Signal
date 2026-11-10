import json

import pytest
from fastapi.testclient import TestClient

from signal_app.adapters.http.app import create_app
from signal_app.core.ingest import IngestFeedback
from signal_app.core.query import ListFeedback

from .fakes import (FixedClock, InMemoryApiKeyDirectory, InMemoryFeedbackRepository, InMemoryKeyStore,
                    InMemoryPublisher)

H = {"X-Api-Key": "sk_test"}
BODY = {"ticket": {"id": "ZD-1", "created": 1700000000000, "description": "Parcel never arrived",
                   "requester": {"customer_ref": "C1", "locale": "en-GB"}}}
URL = "/v1/sources/support_ticket/feedback"


@pytest.fixture
def wired():
    publisher, repo = InMemoryPublisher(), InMemoryFeedbackRepository()
    keys = InMemoryApiKeyDirectory({"sk_test": ("ridgeline", "support_ticket")})
    ingest = IngestFeedback(publisher, InMemoryKeyStore(), keys, FixedClock(), "salt", 1024)
    return TestClient(create_app(ingest, ListFeedback(repo, keys))), publisher, repo


def test_accepted_then_duplicate(wired):
    client, publisher, _ = wired
    r1 = client.post(URL, json=BODY, headers=H)
    assert r1.status_code == 202 and r1.json()["status"] == "accepted"
    r2 = client.post(URL, json=BODY, headers=H)
    assert r2.status_code == 200 and r2.json() == {"feedback_id": r1.json()["feedback_id"], "status": "duplicate"}
    assert len(publisher.messages) == 1


def test_invalid_key_is_401(wired):
    client, _, _ = wired
    r = client.post(URL, json=BODY, headers={"X-Api-Key": "bad"})
    assert r.status_code == 401 and r.json() == {"error": "invalid API key"}
    assert client.post(URL, json=BODY).json() == {"error": "missing X-Api-Key"}


def test_error_mapping(wired):
    client, publisher, _ = wired
    assert client.post("/v1/sources/nope/feedback", json=BODY, headers=H).status_code == 404
    assert client.post(URL, content=b"{x", headers=H).status_code == 400
    assert client.post(URL, json={"ticket": "x"}, headers=H).json() == {
        "error": "expected an object with a 'ticket' field"}
    publisher.fail = True
    r = client.post(URL, json=BODY, headers=H)
    assert r.status_code == 503 and r.json() == {"error": "temporarily unavailable, please retry"}


def test_list_and_validation(wired):
    client, publisher, repo = wired
    client.post(URL, json=BODY, headers=H)
    repo.save(publisher.messages[0])  # what the worker does
    repo.save({"feedback_id": "fb_x", "tenant_id": "other", "channel": "c", "market": None,
               "language": None, "text": "t", "created_at": "2026-01-01T00:00:00+00:00",
               "received_at": "2026-01-01T00:00:00+00:00"})
    items = client.get("/v1/feedback", headers=H).json()["items"]
    assert len(items) == 1 and items[0]["text"] == "Parcel never arrived"
    assert client.get("/v1/feedback?limit=0", headers=H).status_code == 422
    assert client.get("/health").json() == {"status": "ok"}
