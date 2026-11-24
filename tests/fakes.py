"""In-memory fakes of every port."""
from datetime import datetime, timezone

from signal_app.core.errors import PublishError
from signal_app.core.alarms import Arrivals
from signal_app.core.models import Feedback, FeedbackFilter
from signal_app.core.themes import RankedThemes

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


def matches_filters(row: dict, filters: FeedbackFilter) -> bool:
    """True if the row has the value of every filter that is set (None means "any")."""
    wanted = {"area": filters.area, "topic": filters.topic, "channel": filters.channel,
              "market": filters.market, "sentiment": filters.sentiment, "kind": filters.kind,
              "language": filters.language}
    for column, value in wanted.items():
        if value is not None and row.get(column) != value:
            return False
    return True


class InMemoryFeedbackRepository:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def save(self, message: dict) -> None:
        self.rows.setdefault(message["feedback_id"], message)

    def list(self, tenant: str, limit: int, before: datetime | None,
             filters: FeedbackFilter) -> list[Feedback]:
        # Keep this tenant's rows, only those older than `before` if it is given, and only
        # those that match every filter that is given (like the WHERE in the Postgres version).
        matching = []
        for row in self.rows.values():
            if row["tenant_id"] != tenant:
                continue
            if before is not None and created_at_of(row) >= before:
                continue
            if not matches_filters(row, filters):
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


class InMemoryThemeInputs:
    def __init__(self, items=None, business_days=None):
        self.items = list(items or [])
        self.business = list(business_days or [])

    def problem_items(self, start, end, tenant=None):
        found = []
        for item in self.items:
            if start <= item.created_at < end and (tenant is None or item.tenant == tenant):
                found.append(item)
        return found

    def business_days(self, start, end, tenant=None):
        found = []
        for row in self.business:
            if start <= row.day < end and (tenant is None or row.tenant == tenant):
                found.append(row)
        return found


class InMemoryThemeStore:
    def __init__(self):
        self.ranked = None
        self.fail = False

    def replace_all(self, ranked):
        if self.fail:
            raise RuntimeError("database is down")
        self.ranked = ranked

    def latest(self, tenant, limit, area=None, market=None, topic=None):
        if self.ranked is None:
            return None
        mine = []
        for theme in self.ranked.themes:
            if theme.tenant == tenant:
                mine.append(theme)
        if not mine:
            return None
        # Filter before limit, like the WHERE in the Postgres version.
        matching = []
        for theme in mine:
            if area is not None and theme.area != area:
                continue
            if topic is not None and theme.topic != topic:
                continue
            if market is not None and market not in theme.customers_by_market:
                continue
            matching.append(theme)
        return RankedThemes(as_of=self.ranked.as_of, computed_at=self.ranked.computed_at,
                            themes=matching[:limit])


class InMemoryArrivals:
    def __init__(self):
        self.requests = []  # (tenant, channel, at)

    def record(self, tenant, channel, at):
        self.requests.append((tenant, channel, at))

    def counts(self, start, end):
        totals = {}
        for tenant, channel, at in self.requests:
            minute = at.replace(second=0, microsecond=0)
            if start <= minute < end:
                totals[(tenant, channel)] = totals.get((tenant, channel), 0) + 1
        found = []
        for (tenant, channel), requests in sorted(totals.items()):
            found.append(Arrivals(tenant=tenant, channel=channel, requests=requests))
        return found


class InMemoryAlertStore:
    def __init__(self):
        self.alerts = []

    def last_fired(self, since):
        latest = {}
        for alert in self.alerts:
            key = (alert.alarm, alert.subject)
            if alert.fired_at >= since and (key not in latest or alert.fired_at > latest[key]):
                latest[key] = alert.fired_at
        return latest

    def save(self, alerts):
        self.alerts.extend(alerts)

    def latest(self, tenant, limit):
        mine = []
        for alert in reversed(self.alerts):
            if alert.tenant == tenant:
                mine.append(alert)
        return mine[:limit]
