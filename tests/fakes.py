"""In-memory fakes of every port."""
from datetime import datetime, timezone

from signal_app.core.errors import PublishError
from signal_app.core.models import Feedback

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def __init__(self, now: datetime = NOW):
        self._now = now

    def now(self) -> datetime:
        return self._now


class InMemoryPublisher:
    def __init__(self):
        self.messages: list[dict] = []
        self.fail = False

    def publish(self, message: dict) -> None:
        if self.fail:
            raise PublishError("broker down")
        self.messages.append(message)


class InMemoryKeyStore:
    def __init__(self):
        self.keys: dict[str, tuple[str, str]] = {}

    def get(self, key: str) -> str | None:
        found = self.keys.get(key)
        return found[1] if found else None

    def save(self, key: str, tenant: str, feedback_id: str) -> None:
        self.keys.setdefault(key, (tenant, feedback_id))


class InMemoryFeedbackRepository:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def save(self, message: dict) -> None:
        self.rows.setdefault(message["feedback_id"], message)

    def list(self, tenant: str, limit: int, before: datetime | None) -> list[Feedback]:
        def ts(m, k):
            return datetime.fromisoformat(m[k])
        rows = [m for m in self.rows.values() if m["tenant_id"] == tenant
                and (before is None or ts(m, "created_at") < before)]
        rows.sort(key=lambda m: ts(m, "created_at"), reverse=True)
        return [Feedback(m["feedback_id"], m["channel"], m["market"], m["language"], m["text"],
                         ts(m, "created_at"), ts(m, "received_at")) for m in rows[:limit]]


class InMemoryApiKeyDirectory:
    def __init__(self, keys: dict[str, tuple[str, str]] | None = None):
        self.keys = keys or {}

    def lookup(self, api_key: str) -> tuple[str, str] | None:
        return self.keys.get(api_key)
