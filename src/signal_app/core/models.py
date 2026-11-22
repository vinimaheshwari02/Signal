from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class IngestResult:
    feedback_id: str
    status: Literal["accepted", "duplicate"]


@dataclass(frozen=True)
class Feedback:
    feedback_id: str
    channel: str
    market: str | None
    language: str | None
    text: str
    created_at: datetime
    received_at: datetime
    sentiment: str | None = None
    kind: str | None = None
    area: str | None = None
    topic: str | None = None


@dataclass(frozen=True)
class FeedbackFilter:
    """Optional filters for listing feedback. None means "do not filter on this field".
    Every value is an exact match, and all the given ones must match (AND)."""
    area: str | None = None
    topic: str | None = None
    channel: str | None = None
    market: str | None = None
    sentiment: str | None = None
    kind: str | None = None
    language: str | None = None
