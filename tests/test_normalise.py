from datetime import datetime, timezone

import pytest

from signal_app.core.normalise import Rejected, support_ticket

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def ticket(**over):
    t = {"id": "ZD-1", "created": 1784597786000, "subject": "s", "description": "Where is my order?",
         "requester": {"customer_ref": "C1", "locale": "de-DE"}}
    t.update(over)
    return {"ticket": t}


def test_maps_fields():
    r = support_ticket("ridgeline", ticket(), NOW, "salt")
    assert r["source_id"] == "ZD-1" and r["market"] == "DE" and r["language"] == "de"
    assert r["customer_ref"] != "C1"  # hashed


def test_falls_back_to_subject():
    assert support_ticket("t", ticket(description=None, subject="Broken"), NOW, "s")["text"] == "Broken"


@pytest.mark.parametrize("bad", [None, [], "x", {}, {"ticket": "x"}, ticket(description="  ", subject="")])
def test_rejects_unusable_input(bad):
    with pytest.raises(Rejected):
        support_ticket("t", bad, NOW, "s")


def test_implausible_date_uses_received_at():
    r = support_ticket("t", ticket(created=99999999999999999), NOW, "s")
    assert r["created_at"] == NOW.isoformat()
