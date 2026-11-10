import json

import pytest

from signal_app.core.ingest import IngestFeedback
from signal_app.core.process import ProcessFeedback

from .fakes import FixedClock, InMemoryApiKeyDirectory, InMemoryFeedbackRepository, InMemoryKeyStore, InMemoryPublisher

CHANNEL_BODIES = {
    "support_ticket": {"ticket": {"id": "ZD-1", "created": 1784597786000, "description": "Parcel marked as delivered but nothing arrived.",
                                  "requester": {"customer_ref": "C1", "locale": "en-GB"}}},
    "app_store": {"review_id": "rv_1", "author": "a", "rating": 1, "title": "t", "body": "Payment failed three times with no error message, gave up.",
                  "reviewed_at": "2026-07-21T00:34:42Z", "territory": "GB"},
    "nps_survey": {"response_id": "n1", "score": 10, "comment": "Free returns made me confident to order the tent.",
                   "submitted": "21/07/2026 02:52", "customer_id": "C2", "market": "UK"},
    "in_app": {"event": "feedback_submitted", "ts": "2026-07-21T02:18:34.000+01:00", "user": {"id": "C3", "locale": "de-DE"},
               "payload": {"screen": "x", "message": "Die Suche findet nichts Passendes.", "mood": "angry"}},
    "social": {"post_id": "p1", "author_handle": "@x", "text": "Love the wishlist, saved my lamp for later.",
               "created_at": "Tue, 21 Jul 2026 01:52:52 +0000", "lang": "en"},
}
EXPECTED = {  # channel -> (area, topic, kind, sentiment, language)
    "support_ticket": ("delivery", "missing_parcel", "problem", "negative", "en"),
    "app_store": ("payments", "payment_failed", "problem", "negative", "en"),
    "nps_survey": ("returns", "returns_policy", "praise", "positive", "en"),
    "in_app": ("search", "relevance", "problem", "negative", "de"),
    "social": ("account", "wishlist", "praise", "positive", "en"),
}


@pytest.fixture
def pipeline():
    publisher, repo = InMemoryPublisher(), InMemoryFeedbackRepository()
    keys = {f"key_{c}": ("ridgeline", c) for c in CHANNEL_BODIES}
    ingest = IngestFeedback(publisher, InMemoryKeyStore(), InMemoryApiKeyDirectory(keys), FixedClock(), "salt", 4096)
    return ingest, publisher, ProcessFeedback(repo), repo


@pytest.mark.parametrize("channel", list(CHANNEL_BODIES))
def test_every_channel_goes_from_api_to_a_labelled_row(pipeline, channel):
    ingest, publisher, process, repo = pipeline
    result = ingest.run(channel, f"key_{channel}", json.dumps(CHANNEL_BODIES[channel]).encode(), None)
    assert result.status == "accepted"
    process.run(json.dumps(publisher.messages[-1]))      # what the worker does with the Kafka message
    row = repo.rows[result.feedback_id]
    got = (row["area"], row["topic"], row["kind"], row["sentiment"], row["language"])
    assert got == EXPECTED[channel]
    assert row["tenant_id"] == "ridgeline" and row["channel"] == channel


def test_processing_the_same_message_twice_stores_one_row(pipeline):
    ingest, publisher, process, repo = pipeline
    ingest.run("social", "key_social", json.dumps(CHANNEL_BODIES["social"]).encode(), None)
    for _ in range(2):
        process.run(json.dumps(publisher.messages[0]))
    assert len(repo.rows) == 1


def test_unreadable_messages_raise_the_errors_the_consumer_skips():
    process = ProcessFeedback(InMemoryFeedbackRepository())
    for bad in ("not json", "{}", "[]", "5"):
        with pytest.raises((ValueError, KeyError, TypeError)):
            process.run(bad)


def test_raw_line_breaks_inside_the_body_are_accepted(pipeline):
    ingest, publisher, _, _ = pipeline
    body = b'{"post_id": "p9", "author_handle": "@x", "text": "Parcel\nnever arrived", "lang": "en"}'
    assert ingest.run("social", "key_social", body, None).status == "accepted"
    assert publisher.messages[0]["text"] == "Parcel never arrived"
