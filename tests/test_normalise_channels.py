from datetime import datetime, timezone

import pytest

from signal_app.core.errors import Rejected
from signal_app.core.normalise import NORMALISERS, mask_pii

RCV = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def run(channel, payload, tenant="ridgeline"):
    return NORMALISERS[channel](tenant, payload, RCV, "salt")


def app_review(**over):
    p = {"review_id": "rv_1", "author": "priya5385", "platform": "android", "rating": 3,
         "title": "How long do I have to return a bed linen", "body": "How long do I have to return a bed linen set?",
         "reviewed_at": "2026-07-21T00:34:42Z", "territory": "GB"}
    p.update(over)
    return p


def nps(**over):
    p = {"response_id": "nps-1", "score": 10, "comment": "Free returns made me confident.",
         "submitted": "21/07/2026 02:52", "customer_id": "C803469", "market": "UK"}
    p.update(over)
    return p


def in_app_msg(**over):
    p = {"event": "feedback_submitted", "ts": "2026-07-21T02:18:34.000+01:00",
         "user": {"id": "C1", "locale": "en-GB"},
         "payload": {"screen": "orders/tracking", "message": "Delivery slot was missed.", "mood": "angry"}}
    p.update(over)
    return p


def post(**over):
    p = {"post_id": "1790000000000087109", "author_handle": "@jan1134", "text": "Parcel marked as delivered but nothing arrived.",
         "created_at": "Tue, 21 Jul 2026 01:52:52 +0000", "lang": "en"}
    p.update(over)
    return p


# ---- app_store
def test_app_store_maps_fields():
    r = run("app_store", app_review())
    assert r["source_id"] == "rv_1" and r["market"] == "UK" and r["sentiment_hint"] == "neutral"
    assert r["text"].endswith("set?") and r["customer_ref"] != "priya5385"
    assert r["created_at"] == "2026-07-21T00:34:42+00:00"


def test_app_store_uses_title_when_body_missing_and_rating_word():
    r = run("app_store", app_review(body=None, rating="five"))
    assert r["text"].startswith("How long") and r["sentiment_hint"] == "positive"


@pytest.mark.parametrize("rating,hint", [(1, "negative"), (2, "negative"), (3, "neutral"), (4, "positive"), (5, "positive"), ("x", None)])
def test_app_store_rating_hint(rating, hint):
    assert run("app_store", app_review(rating=rating))["sentiment_hint"] == hint


def test_app_store_no_text_is_rejected():
    with pytest.raises(Rejected):
        run("app_store", app_review(body="", title=None))


# ---- nps
def test_nps_local_time_is_converted_to_utc():
    # 02:52 on a summer day in the UK is 01:52 UTC; in Germany it would be 00:52 UTC.
    assert run("nps_survey", nps())["created_at"] == "2026-07-21T01:52:00+00:00"
    assert run("nps_survey", nps(market="DE"))["created_at"] == "2026-07-21T00:52:00+00:00"


def test_nps_bad_date_falls_back_to_received_at():
    assert run("nps_survey", nps(submitted="31/02/2026 25:61"))["created_at"] == RCV.isoformat()


@pytest.mark.parametrize("score,hint", [(0, "negative"), (6, "negative"), (7, "neutral"), (8, "neutral"), (9, "positive"), ("ten", "positive"), (None, None)])
def test_nps_score_hint(score, hint):
    assert run("nps_survey", nps(score=score))["sentiment_hint"] == hint


def test_nps_without_comment_is_rejected():
    for c in (None, "", "   "):
        with pytest.raises(Rejected):
            run("nps_survey", nps(comment=c))


# ---- in_app
def test_in_app_has_no_source_id_and_reads_mood_and_offset():
    r = run("in_app", in_app_msg())
    assert r["source_id"] is None and r["sentiment_hint"] == "negative" and r["market"] == "UK"
    assert r["created_at"] == "2026-07-21T01:18:34+00:00"


def test_in_app_rejects_string_payload_and_missing_message():
    with pytest.raises(Rejected):
        run("in_app", in_app_msg(payload="oops"))
    with pytest.raises(Rejected):
        run("in_app", in_app_msg(payload={"screen": "x", "message": None}))


# ---- social
def test_social_maps_fields():
    r = run("social", post())
    assert r["source_id"] == "1790000000000087109" and r["language"] == "en" and r["market"] is None
    assert r["created_at"] == "2026-07-21T01:52:52+00:00"


def test_social_empty_text_rejected_and_odd_language_ignored():
    with pytest.raises(Rejected):
        run("social", post(text=""))
    assert run("social", post(lang="xx"))["language"] is None


# ---- all channels
@pytest.mark.parametrize("channel", list(NORMALISERS))
@pytest.mark.parametrize("bad", [None, [], "x", 5, {}])
def test_every_normaliser_rejects_non_usable_payloads(channel, bad):
    with pytest.raises(Rejected):
        run(channel, bad)


def test_control_characters_and_spaces_are_cleaned():
    assert run("social", post(text="Parcel\n late\t\tagain "))["text"] == "Parcel late again"


# ---- PII
def test_pii_is_masked():
    t = mask_pii("Email ines.garcia64@example.com or ring +44 7700 900187. Order #123456 is late, order 1 ok.")
    assert "example.com" not in t and "7700" not in t and "123456" not in t
    assert "[email]" in t and "[phone]" in t and "[order]" in t
    assert "order 1 ok" in t  # a short number is not an order number


def test_pii_is_masked_in_the_stored_text():
    assert "[email]" in run("social", post(text="Write to jo@example.org please"))["text"]
