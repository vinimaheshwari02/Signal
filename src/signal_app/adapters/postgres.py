"""PostgreSQL adapters: idempotency keys, feedback storage, API key lookup, themes and alarms."""
import logging
from datetime import date, datetime

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..core.alarms import Alert, Arrivals
from ..core.ids import hash_api_key
from ..core.models import Feedback, FeedbackFilter
from ..core.themes import BusinessDay, ProblemItem, RankedThemes, Theme
from ..shared import config

log = logging.getLogger("signal.postgres")

_pools: dict[str, ConnectionPool] = {}


def pool(url: str | None = None) -> ConnectionPool:
    url = url or config.DATABASE_URL
    if url not in _pools:
        # Every connection talks UTC, so times come back the same whatever the server's zone is.
        _pools[url] = ConnectionPool(url, min_size=1, max_size=config.DB_POOL_SIZE, open=True,
                                     kwargs={"options": "-c timezone=UTC"})
    return _pools[url]


class PostgresKeyStore:
    def __init__(self, url: str | None = None):
        self.url = url

    def get(self, key: str) -> str | None:
        with pool(self.url).connection() as conn:
            row = conn.execute("SELECT feedback_id FROM idempotency_keys WHERE key = %s", (key,)).fetchone()
        if row is None:
            return None
        feedback_id = row[0]
        return feedback_id

    def save(self, key: str, tenant: str, feedback_id: str) -> None:
        with pool(self.url).connection() as conn:
            try:
                conn.execute("INSERT INTO idempotency_keys (key, tenant_id, feedback_id) VALUES (%s,%s,%s)",
                             (key, tenant, feedback_id))
            except UniqueViolation:
                pass  # a parallel request got there first; the worker de-duplicates by feedback_id


INSERT_FEEDBACK_SQL = """
INSERT INTO feedback (feedback_id, tenant_id, channel, source_id, customer_ref, market, language,
                      text, created_at, created_at_estimated, received_at, sentiment, kind, area, topic)
VALUES (%(feedback_id)s, %(tenant_id)s, %(channel)s, %(source_id)s, %(customer_ref)s, %(market)s,
        %(language)s, %(text)s, %(created_at)s, %(created_at_estimated)s, %(received_at)s, %(sentiment)s, %(kind)s, %(area)s, %(topic)s)
ON CONFLICT (feedback_id) DO NOTHING
"""


class PostgresFeedbackRepository:
    def __init__(self, url: str | None = None):
        self.url = url

    def save(self, message: dict) -> None:
        row = dict(message)
        # Messages published before this field existed may still be in Kafka.
        row.setdefault("created_at_estimated", False)
        with pool(self.url).connection() as conn:
            conn.execute(INSERT_FEEDBACK_SQL, row)

    def list(self, tenant: str, limit: int, before: datetime | None,
             filters: FeedbackFilter) -> list[Feedback]:
        """Row-level security limits the rows to the tenant set on the transaction.
        Each filter is "(value IS NULL OR column = value)": a filter that is not given (None)
        matches every row, so without filters the query returns what it always did."""
        params = {"before": before, "limit": limit,
                  "area": filters.area, "topic": filters.topic, "channel": filters.channel,
                  "market": filters.market, "sentiment": filters.sentiment, "kind": filters.kind,
                  "language": filters.language}
        with pool(self.url).connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                rows = conn.execute(
                    """SELECT feedback_id, channel, market, language, text, created_at, received_at,
                              sentiment, kind, area, topic
                       FROM feedback
                       WHERE (%(before)s::timestamptz IS NULL OR created_at < %(before)s)
                         AND (%(area)s::text IS NULL OR area = %(area)s)
                         AND (%(topic)s::text IS NULL OR topic = %(topic)s)
                         AND (%(channel)s::text IS NULL OR channel = %(channel)s)
                         AND (%(market)s::text IS NULL OR market = %(market)s)
                         AND (%(sentiment)s::text IS NULL OR sentiment = %(sentiment)s)
                         AND (%(kind)s::text IS NULL OR kind = %(kind)s)
                         AND (%(language)s::text IS NULL OR language = %(language)s)
                       ORDER BY created_at DESC LIMIT %(limit)s""",
                    params).fetchall()
        feedback = []
        for row in rows:  # the columns come back in the order of the SELECT above
            feedback.append(Feedback(feedback_id=row[0], channel=row[1], market=row[2], language=row[3],
                                     text=row[4], created_at=row[5], received_at=row[6],
                                     sentiment=row[7], kind=row[8], area=row[9], topic=row[10]))
        return feedback


class PostgresApiKeyDirectory:
    def __init__(self, url: str | None = None):
        self.url = url

    def lookup(self, api_key: str) -> tuple[str, str] | None:
        with pool(self.url).connection() as conn:
            row = conn.execute("SELECT tenant_id, channel FROM api_keys WHERE key_hash = %s",
                               (hash_api_key(api_key),)).fetchone()
        if row is None:
            return None
        tenant_id, channel = row
        return tenant_id, channel


# ---------- themes (ADR 0007) ----------

def _read(url: str | None, sql: str, params: dict, tenant: str | None) -> list[tuple]:
    """Run a SELECT. With a tenant, set it on the transaction first, so row-level security
    applies for the API role (the owner role used by the scheduler bypasses it)."""
    with pool(url).connection() as conn:
        with conn.transaction():
            if tenant is not None:
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            return conn.execute(sql, params).fetchall()


class PostgresThemeInputs:
    def __init__(self, url: str | None = None):
        self.url = url

    def problem_items(self, start: datetime, end: datetime, tenant: str | None = None) -> list[ProblemItem]:
        rows = _read(self.url,
                     """SELECT tenant_id, area, topic, market, customer_ref, created_at,
                               created_at_estimated
                        FROM feedback
                        WHERE kind = 'problem' AND created_at >= %(start)s AND created_at < %(end)s
                          AND (%(tenant)s::text IS NULL OR tenant_id = %(tenant)s)""",
                     {"start": start, "end": end, "tenant": tenant}, tenant)
        items = []
        for row in rows:
            items.append(ProblemItem(tenant=row[0], area=row[1], topic=row[2], market=row[3],
                                     customer_ref=row[4], created_at=row[5],
                                     created_at_estimated=row[6]))
        return items

    def business_days(self, start: date, end: date, tenant: str | None = None) -> list[BusinessDay]:
        rows = _read(self.url,
                     """SELECT tenant_id, market, day, orders, revenue_gbp, payment_attempts,
                               payment_failures, deliveries_due, deliveries_late, returns_requested
                        FROM business_daily
                        WHERE day >= %(start)s AND day < %(end)s
                          AND (%(tenant)s::text IS NULL OR tenant_id = %(tenant)s)""",
                     {"start": start, "end": end, "tenant": tenant}, tenant)
        days = []
        for row in rows:
            days.append(BusinessDay(tenant=row[0], market=row[1], day=row[2], orders=row[3],
                                    revenue_gbp=float(row[4]),  # numeric comes back as Decimal
                                    payment_attempts=row[5], payment_failures=row[6],
                                    deliveries_due=row[7], deliveries_late=row[8],
                                    returns_requested=row[9]))
        return days


INSERT_THEME_SQL = """
INSERT INTO themes (tenant_id, theme_id, area, topic, score, problem_customers, last_week_customers,
                    trend, customers_by_market, evidence, as_of, computed_at)
VALUES (%(tenant)s, %(theme_id)s, %(area)s, %(topic)s, %(score)s, %(problem_customers)s,
        %(last_week_customers)s, %(trend)s, %(customers_by_market)s, %(evidence)s, %(as_of)s,
        %(computed_at)s)
"""


class PostgresThemeStore:
    def __init__(self, url: str | None = None):
        self.url = url

    def replace_all(self, ranked: RankedThemes) -> None:
        rows = []
        for theme in ranked.themes:
            rows.append({"tenant": theme.tenant, "theme_id": theme.theme_id, "area": theme.area,
                         "topic": theme.topic, "score": theme.score,
                         "problem_customers": theme.problem_customers,
                         "last_week_customers": theme.last_week_customers, "trend": theme.trend,
                         "customers_by_market": Jsonb(theme.customers_by_market),
                         "evidence": Jsonb(theme.evidence),
                         "as_of": ranked.as_of, "computed_at": ranked.computed_at})
        with pool(self.url).connection() as conn:
            with conn.transaction():  # all or nothing: a failed run keeps the last good ranking
                conn.execute("DELETE FROM themes")
                with conn.cursor() as cursor:
                    cursor.executemany(INSERT_THEME_SQL, rows)

    def latest(self, tenant: str, limit: int, area: str | None = None,
               market: str | None = None, topic: str | None = None) -> RankedThemes | None:
        """Filters work like in PostgresFeedbackRepository.list: None matches every row.
        `customers_by_market ? market` is true when the jsonb object has that market as a key."""
        rows = _read(self.url,
                     """SELECT tenant_id, theme_id, area, topic, score, problem_customers,
                               last_week_customers, trend, customers_by_market, evidence,
                               as_of, computed_at
                        FROM themes
                        WHERE tenant_id = %(tenant)s
                          AND (%(area)s::text IS NULL OR area = %(area)s)
                          AND (%(topic)s::text IS NULL OR topic = %(topic)s)
                          AND (%(market)s::text IS NULL OR customers_by_market ? %(market)s)
                        ORDER BY score DESC, theme_id LIMIT %(limit)s""",
                     {"tenant": tenant, "limit": limit, "area": area, "topic": topic,
                      "market": market}, tenant)
        if not rows:
            return self._empty_ranking(tenant)
        themes = []
        for row in rows:
            themes.append(Theme(tenant=row[0], theme_id=row[1], area=row[2], topic=row[3],
                                score=row[4], problem_customers=row[5], last_week_customers=row[6],
                                trend=row[7], customers_by_market=row[8], evidence=row[9]))
        first = rows[0]
        return RankedThemes(as_of=first[10], computed_at=first[11], themes=themes)

    def _empty_ranking(self, tenant: str) -> RankedThemes | None:
        """No theme matched. If the tenant has a stored ranking, return its dates with no themes
        (a filter matched nothing); if not, None (no ranking yet, as before filters existed)."""
        rows = _read(self.url,
                     "SELECT as_of, computed_at FROM themes WHERE tenant_id = %(tenant)s LIMIT 1",
                     {"tenant": tenant}, tenant)
        if not rows:
            return None
        as_of, computed_at = rows[0]
        return RankedThemes(as_of=as_of, computed_at=computed_at, themes=[])


# ---------- alarms (ADR 0008) ----------

class PostgresArrivalCounter:
    """Requests per tenant, channel and minute. The API writes, the scheduler reads."""

    def __init__(self, url: str | None = None):
        self.url = url

    def record(self, tenant: str, channel: str, at: datetime) -> None:
        minute = at.replace(second=0, microsecond=0)
        try:
            with pool(self.url).connection() as conn:
                conn.execute("""INSERT INTO arrivals (tenant_id, channel, minute, requests)
                                VALUES (%s, %s, %s, 1)
                                ON CONFLICT (tenant_id, channel, minute)
                                DO UPDATE SET requests = arrivals.requests + 1""",
                             (tenant, channel, minute))
        except Exception:
            # Counting is for monitoring only: never fail the request because of it.
            log.warning("could not count an arrival for %s/%s", tenant, channel, exc_info=True)

    def counts(self, start: datetime, end: datetime) -> list[Arrivals]:
        rows = _read(self.url,
                     """SELECT tenant_id, channel, sum(requests) FROM arrivals
                        WHERE minute >= %(start)s AND minute < %(end)s
                        GROUP BY tenant_id, channel""",
                     {"start": start, "end": end}, None)
        found = []
        for row in rows:
            found.append(Arrivals(tenant=row[0], channel=row[1], requests=int(row[2])))
        return found


class PostgresAlertStore:
    def __init__(self, url: str | None = None):
        self.url = url

    def last_fired(self, since: datetime) -> dict:
        rows = _read(self.url,
                     """SELECT alarm, subject, max(fired_at) FROM alerts
                        WHERE fired_at >= %(since)s GROUP BY alarm, subject""",
                     {"since": since}, None)
        latest = {}
        for alarm, subject, fired_at in rows:
            latest[(alarm, subject)] = fired_at
        return latest

    def save(self, alerts: list[Alert]) -> None:
        if not alerts:
            return
        rows = []
        for alert in alerts:
            rows.append({"tenant": alert.tenant, "alarm": alert.alarm, "subject": alert.subject,
                         "fired_at": alert.fired_at, "details": Jsonb(alert.details)})
        with pool(self.url).connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany("""INSERT INTO alerts (tenant_id, alarm, subject, fired_at, details)
                                      VALUES (%(tenant)s, %(alarm)s, %(subject)s, %(fired_at)s, %(details)s)""",
                                   rows)

    def latest(self, tenant: str, limit: int) -> list[Alert]:
        rows = _read(self.url,
                     """SELECT tenant_id, alarm, subject, fired_at, details FROM alerts
                        WHERE tenant_id = %(tenant)s
                        ORDER BY fired_at DESC, alert_id DESC LIMIT %(limit)s""",
                     {"tenant": tenant, "limit": limit}, tenant)
        alerts = []
        for row in rows:
            alerts.append(Alert(tenant=row[0], alarm=row[1], subject=row[2], fired_at=row[3], details=row[4]))
        return alerts
