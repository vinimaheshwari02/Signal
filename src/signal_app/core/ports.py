"""What the core needs from the outside world. Adapters implement these."""
from datetime import datetime
from typing import Protocol

from .models import Feedback


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

    def list(self, tenant: str, limit: int, before: datetime | None) -> list[Feedback]:
        """Newest first, for one tenant."""


class ApiKeyDirectory(Protocol):
    def lookup(self, api_key: str) -> tuple[str, str] | None:
        """(tenant, channel) for a key, or None if unknown."""


class Clock(Protocol):
    def now(self) -> datetime: ...
