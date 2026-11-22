"""The theme calculation (ADR 0007), one rule per test."""
from datetime import date, datetime, timedelta, timezone

import pytest

from signal_app.core.themes import BusinessDay, ProblemItem, rank_themes, trend

AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def item(customer="c1", area="delivery", topic="delay", market="UK", days_ago=1, tenant="t1"):
    return ProblemItem(tenant=tenant, area=area, topic=topic, market=market, customer_ref=customer,
                       created_at=AS_OF - timedelta(days=days_ago))


def business(rate_this_week=None, normal_rate=None, orders_this_week=100, normal_orders=100,
             tenant="t1", market="UK"):
    """35 days of business numbers: 4 'normal' weeks, then the week before AS_OF.
    A rate sets late deliveries, payment failures and returns, all out of 1000."""
    rows = []
    for days_back in range(1, 36):
        day = AS_OF.date() - timedelta(days=days_back)
        this_week = days_back <= 7
        rate = rate_this_week if this_week else normal_rate
        bad = round((rate or 0) * 1000)
        rows.append(BusinessDay(tenant=tenant, market=market, day=day,
                                orders=orders_this_week if this_week else normal_orders,
                                revenue_gbp=(orders_this_week if this_week else normal_orders) * 50.0,
                                payment_attempts=1000, payment_failures=bad,
                                deliveries_due=1000, deliveries_late=bad,
                                returns_requested=bad))
    return rows


def rank(items, business_days=()):
    return rank_themes(list(items), list(business_days), AS_OF, NOW).themes


def only(items, business_days=()):
    themes = rank(items, business_days)
    assert len(themes) == 1
    return themes[0]


# ---------- counting customers ----------

def test_the_same_customer_counts_once():
    theme = only([item("c1"), item("c1"), item("c2")])
    assert theme.problem_customers == 2


def test_items_without_a_customer_count_one_each():
    theme = only([item(None), item(None), item("c1")])
    assert theme.problem_customers == 3


def test_only_the_last_seven_days_count():
    themes = rank([item(days_ago=1), item("c2", days_ago=7), item("c3", days_ago=8), item("c4", days_ago=0)])
    # 7 days ago is inside the week; 8 days ago is last week; days_ago=0 is at as_of itself: outside.
    assert themes[0].problem_customers == 2
    assert themes[0].last_week_customers == 1


def test_a_theme_is_tenant_area_and_topic():
    themes = rank([item(tenant="t1"), item(tenant="t2"), item(topic="missing_parcel")])
    assert {t.theme_id for t in themes} == {"t1|delivery|delay", "t2|delivery|delay", "t1|delivery|missing_parcel"}


def test_customers_are_counted_per_market():
    theme = only([item("c1", market="UK"), item("c1", market="DE"), item("c2", market=None)])
    assert theme.customers_by_market == {"DE": 1, "UK": 1, "unknown": 1}
    assert theme.problem_customers == 3


def test_a_theme_with_no_problems_this_week_is_not_listed():
    assert rank([item(days_ago=10)]) == []


# ---------- severity ----------

def test_without_business_numbers_severity_is_one():
    assert only([item("c1"), item("c2")]).score == 2


def test_a_worse_rate_multiplies_the_score():
    theme = only([item("c1"), item("c2")], business(rate_this_week=0.10, normal_rate=0.05))
    assert theme.score == 4.0          # 2 customers x 2 times worse
    assert theme.evidence[0]["times_worse"] == 2.0


def test_a_better_rate_never_shrinks_the_score():
    theme = only([item("c1"), item("c2")], business(rate_this_week=0.02, normal_rate=0.05))
    assert theme.score == 2.0
    assert theme.evidence == []        # only markets that are worse than normal are shown


def test_severity_is_per_market():
    items = [item("c1", market="UK"), item("c2", market="DE")]
    days = business(0.10, 0.05, market="UK") + business(0.05, 0.05, market="DE")
    assert only(items, days).score == 3.0   # UK 1 x 2 + DE 1 x 1


def test_an_unknown_market_has_severity_one():
    assert only([item(market=None)], business(0.10, 0.05)).score == 1.0


def test_areas_without_a_business_number_have_severity_one():
    assert only([item(area="search", topic="relevance")], business(0.10, 0.05)).score == 1.0


@pytest.mark.parametrize("area,topic", [("payments", "payment_failed"), ("returns", "refund")])
def test_payments_and_returns_use_their_own_rate(area, topic):
    assert only([item(area=area, topic=topic)], business(0.10, 0.05)).score == 2.0


def test_checkout_is_worse_when_there_are_fewer_orders_than_normal():
    days = business(orders_this_week=50, normal_orders=100)
    theme = only([item(area="checkout", topic="checkout_error")], days)
    assert theme.score == 2.0
    assert theme.evidence[0]["extra_affected_orders"] == 350   # 50 fewer a day for 7 days


def test_evidence_shows_extra_orders_and_their_value():
    theme = only([item()], business(rate_this_week=0.10, normal_rate=0.05))
    evidence = theme.evidence[0]
    assert evidence["market"] == "UK"
    assert (evidence["current"], evidence["normal"]) == (0.1, 0.05)
    assert evidence["extra_affected_orders"] == 350      # 0.05 more late x 7000 due
    assert evidence["estimated_value_gbp"] == 350 * 50.0  # average order value is 50


def test_missing_business_days_mean_severity_one_not_a_crash():
    this_week_only = [row for row in business(0.10, 0.05) if row.day >= date(2026, 10, 12)]
    assert only([item()], this_week_only).score == 1.0


# ---------- ranking and trend ----------

def test_highest_score_first():
    themes = rank([item("c1", topic="delay"), item("c1", topic="missing_parcel"), item("c2", topic="missing_parcel")])
    assert [t.topic for t in themes] == ["missing_parcel", "delay"]


def test_ties_are_ordered_by_theme_id_so_runs_agree():
    themes = rank([item(topic="b_topic"), item(topic="a_topic")])
    assert [t.topic for t in themes] == ["a_topic", "b_topic"]


@pytest.mark.parametrize("this_week,last_week,expected", [
    (13, 10, "rising"), (12, 10, "stable"), (8, 10, "stable"), (7, 10, "falling"), (3, 0, "rising"), (0, 0, "stable")])
def test_trend(this_week, last_week, expected):
    assert trend(this_week, last_week) == expected


def test_evidence_with_equal_severity_is_ordered_by_market_so_runs_agree():
    items = [item("c1", market="UK"), item("c2", market="DE"), item("c3", market="AT")]
    days = business(0.10, 0.05, market="UK") + business(0.10, 0.05, market="DE") + business(0.10, 0.05, market="AT")
    assert [e["market"] for e in only(items, days).evidence] == ["AT", "DE", "UK"]
