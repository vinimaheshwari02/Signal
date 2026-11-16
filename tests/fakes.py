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
        if found is None:
            return None
        tenant, feedback_id = found
        return feedback_id

    def save(self, key: str, tenant: str, feedback_id: str) -> None:
        self.keys.setdefault(key, (tenant, feedback_id))


def created_at_of(row: dict) -> datetime:
    return datetime.fromisoformat(row["created_at"])


class InMemoryFeedbackRepository:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def save(self, message: dict) -> None:
        self.rows.setdefault(message["feedback_id"], message)

    def list(self, tenant: str, limit: int, before: datetime | None) -> list[Feedback]:
        # Keep this tenant's rows, and only those older than `before` if it is given.
        matching = []
        for row in self.rows.values():
            if row["tenant_id"] != tenant:
                continue
            if before is not None and created_at_of(row) >= before:
                continue
            matching.append(row)
        matching.sort(key=created_at_of, reverse=True)  # newest first

        feedback = []
        for row in matching[:limit]:
            feedback.append(Feedback(
                feedback_id=row["feedback_id"], channel=row["channel"], market=row["market"],
                language=row["language"], text=row["text"],
                created_at=created_at_of(row),
                received_at=datetime.fromisoformat(row["received_at"]),
                sentiment=row.get("sentiment"), kind=row.get("kind"),
                area=row.get("area"), topic=row.get("topic")))
        return feedback


class InMemoryApiKeyDirectory:
    def __init__(self, keys: dict[str, tuple[str, str]] | None = None):
        self.keys = keys or {}

    def lookup(self, api_key: str) -> tuple[str, str] | None:
        return self.keys.get(api_key)
