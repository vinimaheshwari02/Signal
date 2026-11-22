"""The real clock (tests use a fixed one)."""
from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
