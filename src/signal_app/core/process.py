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
        labels = enrich(text=message["text"], language=message.get("language"),
                        sentiment_hint=message.get("sentiment_hint"))
        row = dict(message)  # a copy: everything the API sent, plus the labels
        row["language"] = labels.language
        row["sentiment"] = labels.sentiment
        row["kind"] = labels.kind
        row["area"] = labels.area
        row["topic"] = labels.topic
        self.repository.save(row)
