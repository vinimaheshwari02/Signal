"""Use case: list a tenant's feedback, newest first."""
from datetime import datetime

from .auth import authenticate
from .models import Feedback
from .ports import ApiKeyDirectory, FeedbackRepository


class ListFeedback:
    def __init__(self, repository: FeedbackRepository, keys: ApiKeyDirectory):
        self.repository = repository
        self.keys = keys

    def run(self, api_key: str | None, limit: int, before: datetime | None) -> list[Feedback]:
        tenant, _ = authenticate(self.keys, api_key)
        return self.repository.list(tenant, limit, before)
