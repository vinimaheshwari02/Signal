"""Use case: take one message from the log, label it and store it (the worker's job)."""
import json

from .enrich import enrich
from .ports import FeedbackRepository


class ProcessFeedback:
    def __init__(self, repository: FeedbackRepository):
        self.repository = repository

    def run(self, raw: bytes | str) -> None:
        """Raises ValueError/KeyError/TypeError for a message that cannot be read (the consumer skips
        those); any other error, such as the database being down, means "try again"."""
        message = json.loads(raw)
        e = enrich(message["text"], message.get("language"), message.get("sentiment_hint"))
        self.repository.save({**message, "language": e.language, "sentiment": e.sentiment, "kind": e.kind,
                              "area": e.area, "topic": e.topic})
