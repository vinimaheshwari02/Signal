"""Themes and their impact score (ADR 0007). Pure calculation: no database, no clock.

A theme is one (tenant, area, topic), such as ridgeline | delivery | delay.

    score = problem customers x severity        (per market, then added up)

- problem customers: different customers who reported a problem about the theme in the 7 days
  before `as_of`. Items without a customer count one each.
- severity: how many times worse than normal the area's business number is in that market,
  never below 1. "Normal" is the 4 weeks before those 7 days. Areas without a business number,
  items without a market, and missing business data all use severity 1.
- trend: customers this week against the week before (more than +20% rising, below -20% falling).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

WEEK = timedelta(days=7)
NORMAL_PERIOD = timedelta(days=28)  # the 4 weeks before this week
TREND_CHANGE = 0.20

# Which business number belongs to which area: (what went wrong, out of how many).
RATES = {
    "delivery": ("deliveries_late", "deliveries_due"),
    "payments": ("payment_failures", "payment_attempts"),
    "returns": ("returns_requested", "orders"),
}
# Checkout is different: there is no failure count, so fewer orders than normal means worse.
CHECKOUT = "checkout"


@dataclass(frozen=True)
class ProblemItem:
    """One feedback item of kind "problem", with only what the score needs."""
    tenant: str
    area: str
    topic: str
    market: str | None
    customer_ref: str | None
    created_at: datetime
    created_at_estimated: bool = False  # True if the source's time was unusable (see normalise.py)


@dataclass(frozen=True)
class BusinessDay:
    """One row of business_daily: one tenant, one market, one day."""
    tenant: str
    market: str
    day: date
    orders: int
    revenue_gbp: float
    payment_attempts: int
    payment_failures: int
    deliveries_due: int
    deliveries_late: int
    returns_requested: int


@dataclass(frozen=True)
class Theme:
    tenant: str
    theme_id: str
    area: str
    topic: str
    score: float
    problem_customers: int
    last_week_customers: int
    trend: str                                   # rising / falling / stable
    customers_by_market: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)  # one dict per market that is worse than normal


@dataclass(frozen=True)
class RankedThemes:
    as_of: datetime
    computed_at: datetime
    themes: list


def theme_id(tenant: str, area: str, topic: str) -> str:
    """The same theme always gets the same id, so trends and alarms can refer to it."""
    return f"{tenant}|{area}|{topic}"


def input_window(as_of: datetime) -> tuple[datetime, datetime, date, date]:
    """What rank_themes needs for a given as_of: problem items written in [item_start, as_of)
    (this week and last week) and business days in [day_start, day_end) (normal weeks + this week)."""
    item_start = as_of - 2 * WEEK
    day_end = as_of.date()
    day_start = day_end - WEEK - NORMAL_PERIOD
    return item_start, as_of, day_start, day_end


# ---------- counting customers ----------

def count_customers(items: list[ProblemItem], start: datetime, end: datetime) -> dict:
    """{(tenant, area, topic, market): different customers} for items written in [start, end)."""
    customers = defaultdict(set)   # known customers, each counted once
    anonymous = defaultdict(int)   # items without a customer, each counted once
    for item in items:
        if not (start <= item.created_at < end):
            continue
        group = (item.tenant, item.area, item.topic, item.market)
        if item.customer_ref is None:
            anonymous[group] += 1
        else:
            customers[group].add(item.customer_ref)
    counts = {}
    # Sorted, so every run goes through the groups in the same order and gives the same result.
    for group in sorted(set(customers) | set(anonymous), key=group_order):
        counts[group] = len(customers[group]) + anonymous[group]
    return counts


def group_order(group: tuple) -> tuple:
    tenant, area, topic, market = group
    return (tenant, area, topic, market or "")  # a missing market sorts first


def trend(this_week: int, last_week: int) -> str:
    if last_week == 0:
        return "rising" if this_week > 0 else "stable"
    change = (this_week - last_week) / last_week
    if change > TREND_CHANGE:
        return "rising"
    if change < -TREND_CHANGE:
        return "falling"
    return "stable"


# ---------- severity from business numbers ----------

def days_between(business: dict, tenant: str, market: str, start: date, end: date) -> list[BusinessDay]:
    """The business rows for one tenant and market for the days in [start, end)."""
    rows = []
    day = start
    while day < end:
        row = business.get((tenant, market, day))
        if row is not None:
            rows.append(row)
        day += timedelta(days=1)
    return rows


def total(rows: list[BusinessDay], column: str) -> float:
    result = 0.0
    for row in rows:
        result += getattr(row, column)
    return result


def compare_with_normal(area: str, this_week: list[BusinessDay],
                        normal: list[BusinessDay]) -> tuple[float, dict | None]:
    """(severity, evidence) for one area in one market: how this week's business number compares
    with the normal weeks. (1.0, None) when it cannot be compared."""
    if not this_week or not normal:
        return 1.0, None
    orders = total(this_week, "orders")
    average_order_value = total(this_week, "revenue_gbp") / orders if orders else 0.0

    if area == CHECKOUT:
        # Orders per day: fewer than normal is worse.
        current = orders / len(this_week)
        usual = total(normal, "orders") / len(normal)
        if current == 0 or usual == 0:
            return 1.0, None
        times_worse = usual / current
        extra = (usual - current) * len(this_week)     # orders we would normally have had
        metric = "orders per day"
    else:
        wrong, out_of = RATES[area]
        if total(this_week, out_of) == 0 or total(normal, out_of) == 0:
            return 1.0, None
        current = total(this_week, wrong) / total(this_week, out_of)
        usual = total(normal, wrong) / total(normal, out_of)
        if usual == 0:
            return 1.0, None
        times_worse = current / usual
        extra = (current - usual) * total(this_week, out_of)   # e.g. extra late deliveries
        metric = f"{wrong} / {out_of}"

    # Severity is never below 1: good business numbers do not make a problem smaller.
    severity = max(1.0, times_worse)
    extra = max(0.0, extra)
    evidence = {"metric": metric, "current": round(current, 4), "normal": round(usual, 4),
                "times_worse": round(times_worse, 2), "extra_affected_orders": round(extra),
                "estimated_value_gbp": round(extra * average_order_value, 2)}
    return severity, evidence


def has_business_number(area: str) -> bool:
    return area in RATES or area == CHECKOUT


# ---------- the ranking ----------

def worst_first(evidence: dict) -> tuple:
    # The market settles ties, so the order never changes between runs.
    return (-evidence["times_worse"], evidence["market"])


def highest_score_first(theme: Theme) -> tuple:
    # The theme id settles ties, so the order never changes between runs.
    return (-theme.score, theme.theme_id)


@dataclass
class ThemeTotals:
    """One theme's numbers, collected while we go through its markets."""
    score: float = 0.0
    customers: int = 0
    by_market: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)


def index_by_day(business_days: list[BusinessDay]) -> dict:
    """{(tenant, market, day): row}, so one day's numbers can be looked up directly."""
    business = {}
    for row in business_days:
        business[(row.tenant, row.market, row.day)] = row
    return business


def market_severity(business: dict, tenant: str, area: str, market: str | None,
                    as_of: datetime) -> tuple[float, dict | None]:
    """(severity, evidence) for one theme in one market. Business numbers are per day: the 7 full
    days before as_of's date are compared with the 4 weeks before those."""
    if market is None or not has_business_number(area):
        return 1.0, None
    week_end = as_of.date()
    week_start = week_end - WEEK
    normal_start = week_start - NORMAL_PERIOD
    this_week = days_between(business, tenant, market, week_start, week_end)
    normal = days_between(business, tenant, market, normal_start, week_start)
    return compare_with_normal(area, this_week, normal)


def add_market(totals: ThemeTotals, market: str | None, count: int, severity: float,
               evidence: dict | None) -> None:
    """Add one market's customers to its theme: score = customers x severity."""
    totals.score += count * severity
    totals.customers += count
    totals.by_market[market or "unknown"] = count
    if evidence is not None and evidence["times_worse"] > 1:  # only markets worse than normal
        shown = {"market": market}
        shown.update(evidence)
        totals.evidence.append(shown)

def customers_last_week(last_week: dict, tenant: str, area: str, topic: str) -> int:
    """Last week's customers for one theme, all its markets added up (for the trend)."""
    count = 0
    for (item_tenant, item_area, item_topic, _market), customers in last_week.items():
        if (item_tenant, item_area, item_topic) == (tenant, area, topic):
            count += customers
    return count


def build_theme(tenant: str, area: str, topic: str, totals: ThemeTotals, last_week: int) -> Theme:
    return Theme(tenant=tenant, theme_id=theme_id(tenant, area, topic), area=area, topic=topic,
                 score=round(totals.score, 1), problem_customers=totals.customers,
                 last_week_customers=last_week, trend=trend(totals.customers, last_week),
                 customers_by_market=dict(sorted(totals.by_market.items())),
                 evidence=sorted(totals.evidence, key=worst_first))


def rank_themes(items: list[ProblemItem], business_days: list[BusinessDay], as_of: datetime,
                computed_at: datetime) -> RankedThemes:
    """All themes with at least one problem customer in the week before `as_of`, highest score
    first. `items` must be problem items; anything older than two weeks is ignored."""
    # 1. Count different customers per theme and market, for this week and the week before.
    this_week = count_customers(items, as_of - WEEK, as_of)
    last_week = count_customers(items, as_of - 2 * WEEK, as_of - WEEK)
    business = index_by_day(business_days)

    # 2. Add up each theme over<^ its markets: customers x severity.
    totals = defaultdict(ThemeTotals)
    for (tenant, area, topic, market), count in this_week.items():
        severity, evidence = market_severity(business, tenant, area, market, as_of)
        add_market(totals[(tenant, area, topic)], market, count, severity, evidence)

    # 3. Turn the totals into themes and put the highest score first.
    themes = []
    for (tenant, area, topic), theme_totals in totals.items():
        previous = customers_last_week(last_week, tenant, area, topic)
        themes.append(build_theme(tenant, area, topic, theme_totals, previous))
    themes.sort(key=highest_score_first)
    return RankedThemes(as_of=as_of, computed_at=computed_at, themes=themes)
