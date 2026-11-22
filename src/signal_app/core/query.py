"""Use case: list a tenant's feedback, newest first."""
from datetime import datetime

from .auth import authenticate
from .models import Feedback, FeedbackFilter
from .ports import ApiKeyDirectory, FeedbackRepository


class ListFeedback:
    def __init__(self, repository: FeedbackRepository, keys: ApiKeyDirectory):
        self.repository = repository
        self.keys = keys

    def run(self, api_key: str | None, limit: int, before: datetime | None,
            filters: FeedbackFilter | None = None) -> list[Feedback]:
        """Without filters, every item of the tenant (as before filters existed)."""
        tenant, _ = authenticate(self.keys, api_key)
        if filters is None:
            filters = FeedbackFilter()  # every field None: no filtering
        return self.repository.list(tenant, limit, before, filters)
