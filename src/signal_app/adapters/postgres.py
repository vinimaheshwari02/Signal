"""PostgreSQL adapters: idempotency keys, feedback storage and API key lookup."""
from datetime import datetime

from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool

from ..core.ids import hash_api_key
from ..core.models import Feedback
from ..shared import config

_pools: dict[str, ConnectionPool] = {}


def pool(url: str | None = None) -> ConnectionPool:
    url = url or config.DATABASE_URL
    if url not in _pools:
        _pools[url] = ConnectionPool(url, min_size=1, max_size=5, open=True)
    return _pools[url]


class PostgresKeyStore:
    def __init__(self, url: str | None = None):
        self.url = url

    def get(self, key: str) -> str | None:
        with pool(self.url).connection() as conn:
            row = conn.execute("SELECT feedback_id FROM idempotency_keys WHERE key = %s", (key,)).fetchone()
        return row[0] if row else None

    def save(self, key: str, tenant: str, feedback_id: str) -> None:
        with pool(self.url).connection() as conn:
            try:
                conn.execute("INSERT INTO idempotency_keys (key, tenant_id, feedback_id) VALUES (%s,%s,%s)",
                             (key, tenant, feedback_id))
            except UniqueViolation:
                pass  # a parallel request got there first; the worker de-duplicates by feedback_id


INSERT = """
INSERT INTO feedback (feedback_id, tenant_id, channel, source_id, customer_ref, market, language,
                      text, created_at, received_at, sentiment, kind, area, topic)
VALUES (%(feedback_id)s, %(tenant_id)s, %(channel)s, %(source_id)s, %(customer_ref)s, %(market)s,
        %(language)s, %(text)s, %(created_at)s, %(received_at)s, %(sentiment)s, %(kind)s, %(area)s, %(topic)s)
ON CONFLICT (feedback_id) DO NOTHING
"""


class PostgresFeedbackRepository:
    def __init__(self, url: str | None = None):
        self.url = url

    def save(self, message: dict) -> None:
        with pool(self.url).connection() as conn:
            conn.execute(INSERT, message)

    def list(self, tenant: str, limit: int, before: datetime | None) -> list[Feedback]:
        """Row-level security limits the rows to the tenant set on the transaction."""
        with pool(self.url).connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                rows = conn.execute(
                    """SELECT feedback_id, channel, market, language, text, created_at, received_at
                       FROM feedback WHERE (%(b)s::timestamptz IS NULL OR created_at < %(b)s)
                       ORDER BY created_at DESC LIMIT %(l)s""", {"b": before, "l": limit}).fetchall()
        return [Feedback(*r) for r in rows]


class PostgresApiKeyDirectory:
    def __init__(self, url: str | None = None):
        self.url = url

    def lookup(self, api_key: str) -> tuple[str, str] | None:
        with pool(self.url).connection() as conn:
            row = conn.execute("SELECT tenant_id, channel FROM api_keys WHERE key_hash = %s",
                               (hash_api_key(api_key),)).fetchone()
        return (row[0], row[1]) if row else None
