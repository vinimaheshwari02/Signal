"""The three alarms (ADR 0008). Pure checks: no database, no clock.

1. source_flood  A source sends far more than usual: at least SOURCE_LIMIT requests from one
                 tenant + channel in SOURCE_WINDOW, counted as they arrive, duplicates included.
                 Catches a source resending old items or stuck in a loop.
2. incident      Something breaks right now: at least INCIDENT_LIMIT different customers report a
                 problem about the same theme in the same market within INCIDENT_WINDOW, by the
                 time they wrote it. Items whose time is estimated do not count.
3. decline       A slow decline: an area's business number is at least DECLINE_LIMIT times worse
                 than normal in a market (the same comparison as the theme score). Checked daily.

After an alarm fires, the same alarm about the same subject stays quiet for QUIET_PERIOD.
The limits are starting values, tuned with scripts/alarm_backtest.py on the data pack.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .themes import (CHECKOUT, NORMAL_PERIOD, RATES, WEEK, BusinessDay, ProblemItem,
                     compare_with_normal, days_between)

SOURCE_WINDOW = timedelta(minutes=5)
SOURCE_LIMIT = 50          # normal traffic in the data pack: at most 4 per 5 minutes
INCIDENT_WINDOW = timedelta(minutes=15)
INCIDENT_LIMIT = 8         # normal in the data pack: at most 3 customers per 15 minutes
DECLINE_LIMIT = 1.5        # times worse than normal
QUIET_PERIOD = timedelta(minutes=30)


@dataclass(frozen=True)
class Alert:
    tenant: str
    alarm: str          # source_flood / incident / decline
    subject: str        # what it is about, e.g. "ridgeline|support_ticket"
    fired_at: datetime
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Arrivals:
    """Requests from one tenant + channel within a window."""
    tenant: str
    channel: str
    requests: int


# ---------- 1. source flood ----------

def check_sources(arrivals: list[Arrivals], now: datetime) -> list[Alert]:
    """`arrivals` are the counts for [now - SOURCE_WINDOW, now)."""
    alerts = []
    for counted in arrivals:
        if counted.requests >= SOURCE_LIMIT:
            alerts.append(Alert(
                tenant=counted.tenant, alarm="source_flood",
                subject=f"{counted.tenant}|{counted.channel}", fired_at=now,
                details={"channel": counted.channel, "requests": counted.requests,
                         "window_minutes": int(SOURCE_WINDOW.total_seconds() // 60),
                         "limit": SOURCE_LIMIT}))
    return alerts


# ---------- 2. incident ----------

def check_incidents(items: list[ProblemItem], now: datetime) -> list[Alert]:
    """`items` are problem items; only those written in [now - INCIDENT_WINDOW, now) with a real
    (not estimated) time count."""
    customers = defaultdict(set)
    anonymous = defaultdict(int)
    for item in items:
        if item.created_at_estimated:
            continue
        if not (now - INCIDENT_WINDOW <= item.created_at < now):
            continue
        group = (item.tenant, item.area, item.topic, item.market or "unknown")
        if item.customer_ref is None:
            anonymous[group] += 1
        else:
            customers[group].add(item.customer_ref)

    alerts = []
    for group in sorted(set(customers) | set(anonymous)):
        count = len(customers[group]) + anonymous[group]
        if count < INCIDENT_LIMIT:
            continue
        tenant, area, topic, market = group
        alerts.append(Alert(
            tenant=tenant, alarm="incident", subject=f"{tenant}|{area}|{topic}|{market}", fired_at=now,
            details={"area": area, "topic": topic, "market": market, "customers": count,
                     "window_minutes": int(INCIDENT_WINDOW.total_seconds() // 60),
                     "limit": INCIDENT_LIMIT}))
    return alerts


# ---------- 3. slow decline ----------

def check_declines(business_days: list[BusinessDay], as_of: datetime, now: datetime) -> list[Alert]:
    """Compare the 7 full days before as_of's date with the 4 weeks before those, for every
    tenant, market and area that has a business number."""
    business = {}
    tenant_markets = set()
    for row in business_days:
        business[(row.tenant, row.market, row.day)] = row
        tenant_markets.add((row.tenant, row.market))
    week_end = as_of.date()
    week_start = week_end - WEEK
    normal_start = week_start - NORMAL_PERIOD

    alerts = []
    for tenant, market in sorted(tenant_markets):
        this_week = days_between(business, tenant, market, week_start, week_end)
        normal = days_between(business, tenant, market, normal_start, week_start)
        for area in [*RATES, CHECKOUT]:
            severity, evidence = compare_with_normal(area, this_week, normal)
            if evidence is None or severity < DECLINE_LIMIT:
                continue
            shown = {"area": area, "market": market, "as_of": as_of.isoformat(), "limit": DECLINE_LIMIT}
            shown.update(evidence)
            alerts.append(Alert(tenant=tenant, alarm="decline", subject=f"{tenant}|{area}|{market}",
                                fired_at=now, details=shown))
    return alerts


# ---------- quiet period ----------

def after_quiet_period(candidates: list[Alert], last_fired: dict, now: datetime) -> list[Alert]:
    """Drop candidates whose alarm + subject already fired less than QUIET_PERIOD ago.
    `last_fired` is {(alarm, subject): fired_at}."""
    allowed = []
    for alert in candidates:
        previous = last_fired.get((alert.alarm, alert.subject))
        if previous is not None and now - previous < QUIET_PERIOD:
            continue
        allowed.append(alert)
    return allowed
