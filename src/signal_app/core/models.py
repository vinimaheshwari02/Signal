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
