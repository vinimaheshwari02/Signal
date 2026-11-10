import json

import pytest

from signal_app.core.errors import (BadJson, Forbidden, PayloadTooLarge, PublishError, Rejected,
                                    UnknownChannel, Unauthorized)
from signal_app.core.ingest import IngestFeedback

from .fakes import FixedClock, InMemoryApiKeyDirectory, InMemoryKeyStore, InMemoryPublisher

KEY = "sk_test"


def body(**over):
    t = {"id": "ZD-1", "created": 1700000000000, "description": "Where is my order?",
         "requester": {"customer_ref": "C1", "locale": "de-DE"}}
    t.update(over)
    return json.dumps({"ticket": t}).encode()


@pytest.fixture
def env():
    publisher, store = InMemoryPublisher(), InMemoryKeyStore()
    keys = InMemoryApiKeyDirectory({KEY: ("ridgeline", "support_ticket"), "sk_other": ("ridgeline", "app_store")})
    use = IngestFeedback(publisher, store, keys, FixedClock(), "salt", 1024)
    return use, publisher, store


def test_new_item_is_accepted_and_published_once(env):
    use, publisher, store = env
    r = use.run("support_ticket", KEY, body(), None)
    assert r.status == "accepted" and r.feedback_id.startswith("fb_")
    assert len(publisher.messages) == 1
    assert publisher.messages[0]["feedback_id"] == r.feedback_id
    assert publisher.messages[0]["tenant_id"] == "ridgeline"
    assert len(store.keys) == 1


def test_same_item_twice_is_duplicate_and_published_once(env):
    use, publisher, _ = env
    first = use.run("support_ticket", KEY, body(), None)
    second = use.run("support_ticket", KEY, body(), None)
    assert second.status == "duplicate" and second.feedback_id == first.feedback_id
    assert len(publisher.messages) == 1


def test_publish_failure_does_not_save_key_and_retry_succeeds(env):
    use, publisher, store = env
    publisher.fail = True
    with pytest.raises(PublishError):
        use.run("support_ticket", KEY, body(), None)
    assert store.keys == {}
    publisher.fail = False
    r = use.run("support_ticket", KEY, body(), None)
    assert r.status == "accepted" and len(publisher.messages) == 1


def test_key_for_other_channel_is_forbidden(env):
    use, publisher, _ = env
    with pytest.raises(Forbidden):
        use.run("support_ticket", "sk_other", body(), None)
    assert publisher.messages == []


def test_unknown_channel(env):
    use, _, _ = env
    with pytest.raises(UnknownChannel):
        use.run("carrier_pigeon", KEY, body(), None)


@pytest.mark.parametrize("key", [None, "", "nope"])
def test_missing_or_invalid_key(env, key):
    use, _, _ = env
    with pytest.raises(Unauthorized):
        use.run("support_ticket", key, body(), None)


def test_bad_json(env):
    use, _, _ = env
    with pytest.raises(BadJson):
        use.run("support_ticket", KEY, b"{not json", None)


def test_oversized_body(env):
    use, _, _ = env
    with pytest.raises(PayloadTooLarge):
        use.run("support_ticket", KEY, b" " * 2000, None)


def test_unusable_payload_is_rejected(env):
    use, publisher, _ = env
    with pytest.raises(Rejected):
        use.run("support_ticket", KEY, b'{"ticket": "x"}', None)
    assert publisher.messages == []
