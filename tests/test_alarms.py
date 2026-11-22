"""The three alarm checks and the quiet period (ADR 0008), one rule per test."""
from datetime import datetime, timedelta, timezone

from signal_app.core.alarms import (INCIDENT_LIMIT, QUIET_PERIOD, SOURCE_LIMIT, Alert, Arrivals,
                                    after_quiet_period, check_declines, check_incidents, check_sources)
from signal_app.core.themes import BusinessDay, ProblemItem

NOW = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)


# ---------- 1. source flood ----------

def test_a_source_at_the_limit_fires():
    [alert] = check_sources([Arrivals("t1", "support_ticket", SOURCE_LIMIT)], NOW)
    assert (alert.alarm, alert.subject, alert.tenant) == ("source_flood", "t1|support_ticket", "t1")
    assert alert.details["requests"] == SOURCE_LIMIT


def test_normal_traffic_does_not_fire():
    assert check_sources([Arrivals("t1", "social", SOURCE_LIMIT - 1)], NOW) == []


# ---------- 2. incident ----------

def problem(customer, minutes_ago=5, market="UK", topic="payment_failed", estimated=False, tenant="t1"):
    return ProblemItem(tenant=tenant, area="payments", topic=topic, market=market, customer_ref=customer,
                       created_at=NOW - timedelta(minutes=minutes_ago), created_at_estimated=estimated)


def customers(count, **kwargs):
    return [problem(f"c{number}", **kwargs) for number in range(count)]


def test_enough_customers_in_one_theme_and_market_fire():
    [alert] = check_incidents(customers(INCIDENT_LIMIT), NOW)
    assert alert.alarm == "incident"
    assert alert.subject == "t1|payments|payment_failed|UK"
    assert alert.details["customers"] == INCIDENT_LIMIT


def test_one_customer_complaining_many_times_is_one_customer():
    assert check_incidents([problem("c1") for _ in range(20)], NOW) == []


def test_markets_are_counted_separately():
    half = INCIDENT_LIMIT // 2 + 1
    assert check_incidents(customers(half, market="UK") + customers(half, market="DE"), NOW) == []


def test_only_the_last_fifteen_minutes_count():
    assert check_incidents(customers(INCIDENT_LIMIT, minutes_ago=16), NOW) == []


def test_estimated_times_do_not_count():
    # A source sending broken dates must not be able to fake an incident.
    assert check_incidents(customers(INCIDENT_LIMIT, estimated=True), NOW) == []


def test_items_without_a_market_are_grouped_as_unknown():
    [alert] = check_incidents(customers(INCIDENT_LIMIT, market=None), NOW)
    assert alert.subject.endswith("|unknown")


# ---------- 3. slow decline ----------

def business(late_this_week, late_normally, market="DE"):
    rows = []
    for days_back in range(1, 36):
        late = late_this_week if days_back <= 7 else late_normally
        rows.append(BusinessDay(tenant="t1", market=market, day=NOW.date() - timedelta(days=days_back),
                                orders=100, revenue_gbp=5000.0, payment_attempts=1000, payment_failures=10,
                                deliveries_due=1000, deliveries_late=late, returns_requested=5))
    return rows


def test_a_rate_well_above_normal_fires():
    alerts = check_declines(business(late_this_week=160, late_normally=100), NOW, NOW)
    assert [a.subject for a in alerts] == ["t1|delivery|DE"]
    assert alerts[0].details["times_worse"] == 1.6


def test_a_small_rise_does_not_fire():
    assert check_declines(business(late_this_week=140, late_normally=100), NOW, NOW) == []


# ---------- quiet period ----------

def alert(fired_at=NOW):
    return Alert(tenant="t1", alarm="incident", subject="t1|payments|payment_failed|UK", fired_at=fired_at)


def test_the_same_subject_stays_quiet_for_thirty_minutes():
    last_fired = {("incident", "t1|payments|payment_failed|UK"): NOW - QUIET_PERIOD + timedelta(minutes=1)}
    assert after_quiet_period([alert()], last_fired, NOW) == []


def test_it_fires_again_after_the_quiet_period():
    last_fired = {("incident", "t1|payments|payment_failed|UK"): NOW - QUIET_PERIOD}
    assert after_quiet_period([alert()], last_fired, NOW) == [alert()]


def test_another_subject_is_not_kept_quiet():
    last_fired = {("incident", "t1|payments|payment_failed|DE"): NOW}
    assert after_quiet_period([alert()], last_fired, NOW) == [alert()]
