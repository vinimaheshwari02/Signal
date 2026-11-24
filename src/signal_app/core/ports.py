"""What the core needs from the outside world. Adapters implement these."""
from datetime import date, datetime
from typing import Protocol

from .models import Feedback, FeedbackFilter
from .alarms import Alert, Arrivals
from .themes import BusinessDay, ProblemItem, RankedThemes


class FeedbackPublisher(Protocol):
    def publish(self, message: dict) -> None:
        """Deliver the message durably. Raises PublishError on failure."""


class KeyStore(Protocol):
    def get(self, key: str) -> str | None:
        """feedback_id already accepted for this idempotency key, if any."""

    def save(self, key: str, tenant: str, feedback_id: str) -> None: ...


class FeedbackRepository(Protocol):
    def save(self, message: dict) -> None:
        """Idempotent: saving the same feedback_id twice is harmless."""

    def list(self, tenant: str, limit: int, before: datetime | None,
             filters: FeedbackFilter) -> list[Feedback]:
        """Newest first, for one tenant. Only items matching every field set in `filters`;
        the filters are applied before `limit`."""


class ApiKeyDirectory(Protocol):
    def lookup(self, api_key: str) -> tuple[str, str] | None:
        """(tenant, channel) for a key, or None if unknown."""


class Clock(Protocol):
    def now(self) -> datetime: ...


class ThemeInputs(Protocol):
    """What the theme calculation reads. tenant=None means every tenant (the scheduler);
    the API always passes its own tenant."""

    def problem_items(self, start: datetime, end: datetime, tenant: str | None = None) -> list[ProblemItem]:
        """Feedback of kind "problem" written in [start, end)."""

    def business_days(self, start: date, end: date, tenant: str | None = None) -> list[BusinessDay]:
        """Business rows for the days in [start, end)."""


class ThemeStore(Protocol):
    def replace_all(self, ranked: RankedThemes) -> None:
        """Swap the stored ranking for this one in a single step: on failure the old one stays."""

    def latest(self, tenant: str, limit: int, area: str | None = None,
               market: str | None = None, topic: str | None = None) -> RankedThemes | None:
        """The stored ranking for one tenant, highest score first. None before the first run.
        `area` and `topic` keep only themes of that area or topic; `market` keeps only themes with
        customers in that market. All are applied before `limit`. If the ranking exists but no theme matches,
        the result has the ranking's as_of and computed_at and an empty list of themes."""


class ArrivalCounter(Protocol):
    def record(self, tenant: str, channel: str, at: datetime) -> None:
        """Count one request. Must never fail the request: monitoring is not worth a lost item."""

    def counts(self, start: datetime, end: datetime) -> list[Arrivals]:
        """Requests per tenant + channel that arrived in [start, end)."""


class AlertStore(Protocol):
    def last_fired(self, since: datetime) -> dict:
        """{(alarm, subject): latest fired_at} for alerts fired at or after `since`."""

    def save(self, alerts: list[Alert]) -> None:
        ...

    def latest(self, tenant: str, limit: int) -> list[Alert]:
        """One tenant's alerts, newest first."""
