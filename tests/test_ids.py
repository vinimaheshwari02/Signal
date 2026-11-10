from signal_app.core.ids import feedback_id, idempotency_key


def test_same_source_id_gives_same_key():
    a = idempotency_key("t", "support_ticket", "ZD-1", None, {"x": 1})
    b = idempotency_key("t", "support_ticket", "ZD-1", "other-header", {"x": 2})
    assert a == b


def test_tenant_and_channel_separate_keys():
    assert idempotency_key("t1", "c", "1", None, {}) != idempotency_key("t2", "c", "1", None, {})
    assert idempotency_key("t", "c1", "1", None, {}) != idempotency_key("t", "c2", "1", None, {})


def test_header_used_when_no_source_id():
    assert idempotency_key("t", "c", None, "h1", {"a": 1}) == idempotency_key("t", "c", None, "h1", {"a": 2})
    assert idempotency_key("t", "c", None, "h1", {}) != idempotency_key("t", "c", None, "h2", {})


def test_payload_hash_ignores_key_order():
    a = idempotency_key("t", "c", None, None, {"a": 1, "b": 2})
    b = idempotency_key("t", "c", None, None, {"b": 2, "a": 1})
    assert a == b


def test_feedback_id_is_stable():
    k = idempotency_key("t", "c", "1", None, {})
    assert feedback_id(k) == feedback_id(k) and feedback_id(k).startswith("fb_")
