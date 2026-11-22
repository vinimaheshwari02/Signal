"""Replay the data pack through the real alarm checks, minute by minute, and print when each alarm
would have fired. This is how the limits in core/alarms.py were chosen (ADR 0008).

usage: python scripts/alarm_backtest.py path/to/feedback_all.jsonl path/to/business_daily.csv
           [--source-limit 50] [--incident-limit 8] [--decline-limit 1.5]

It uses the same code as the scheduler: normalise, enrich, then check_sources, check_incidents,
check_declines and the quiet period. Nothing is sent anywhere and no database is needed.
"""
import argparse
import bisect
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_app.core import alarms  # noqa: E402
from signal_app.core.enrich import enrich  # noqa: E402
from signal_app.core.errors import Rejected  # noqa: E402
from signal_app.core.normalise import NORMALISERS  # noqa: E402
from signal_app.core.themes import BusinessDay, ProblemItem  # noqa: E402

TENANTS = {"ridgeline", "harbour-home"}  # the tenants that have keys; others get a 401
MINUTE = timedelta(minutes=1)

parser = argparse.ArgumentParser()
parser.add_argument("feedback")
parser.add_argument("business")
parser.add_argument("--source-limit", type=int, default=alarms.SOURCE_LIMIT)
parser.add_argument("--incident-limit", type=int, default=alarms.INCIDENT_LIMIT)
parser.add_argument("--decline-limit", type=float, default=alarms.DECLINE_LIMIT)
args = parser.parse_args()
alarms.SOURCE_LIMIT = args.source_limit
alarms.INCIDENT_LIMIT = args.incident_limit
alarms.DECLINE_LIMIT = args.decline_limit


def to_minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


# ---------- read the data the way the system would see it ----------
arrival_minutes = defaultdict(int)  # (tenant, channel, minute) -> requests, duplicates included
problems = []
with open(args.feedback, encoding="utf-8") as feedback_file:
    for line in feedback_file:
        try:
            row = json.loads(line, strict=False)
        except ValueError:
            continue  # a cut-off line: the API cannot even tell which tenant sent it
        if row["tenant"] not in TENANTS or row["channel"] not in NORMALISERS:
            continue  # rejected before it is counted (401 / 404)
        received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
        arrival_minutes[(row["tenant"], row["channel"], to_minute(received))] += 1
        try:
            item = NORMALISERS[row["channel"]](row["tenant"], row["payload"], received, "salt")
        except Rejected:
            continue
        labels = enrich(text=item["text"], language=item["language"], sentiment_hint=item["sentiment_hint"])
        if labels.kind == "problem":
            problems.append(ProblemItem(
                tenant=row["tenant"], area=labels.area, topic=labels.topic, market=item["market"],
                customer_ref=item["customer_ref"], created_at=datetime.fromisoformat(item["created_at"]),
                created_at_estimated=item["created_at_estimated"]))
# Duplicates are counted at the API but stored once, so keep one copy per item for alarm 2.
problems = sorted(set(problems), key=lambda problem: problem.created_at)
problem_times = [problem.created_at for problem in problems]

arrivals_by_minute = defaultdict(list)  # minute -> [(tenant, channel, requests)]
for (tenant, channel, minute), requests in arrival_minutes.items():
    arrivals_by_minute[minute].append((tenant, channel, requests))

business_days = []
with open(args.business, newline="", encoding="utf-8") as business_file:
    for row in csv.DictReader(business_file):
        business_days.append(BusinessDay(
            tenant=row["tenant"], market=row["market"], day=date.fromisoformat(row["date"]),
            orders=int(row["orders"]), revenue_gbp=float(row["revenue_gbp"]),
            payment_attempts=int(row["payment_attempts"]), payment_failures=int(row["payment_failures"]),
            deliveries_due=int(row["deliveries_due"]), deliveries_late=int(row["deliveries_late"]),
            returns_requested=int(row["returns_requested"])))

# ---------- alarms 1 and 2: every minute ----------
first = to_minute(min(min(arrivals_by_minute), problem_times[0]))
last = to_minute(max(max(arrivals_by_minute), problem_times[-1])) + 2 * alarms.QUIET_PERIOD
fired = []
last_fired = {}
now = first
while now <= last:
    counts = defaultdict(int)
    minute = now - alarms.SOURCE_WINDOW
    while minute < now:
        for tenant, channel, requests in arrivals_by_minute.get(minute, []):
            counts[(tenant, channel)] += requests
        minute += MINUTE
    window_start = bisect.bisect_left(problem_times, now - alarms.INCIDENT_WINDOW)
    window_end = bisect.bisect_left(problem_times, now)
    if counts or window_end > window_start:
        candidates = alarms.check_sources(
            [alarms.Arrivals(tenant, channel, requests) for (tenant, channel), requests in counts.items()], now)
        candidates += alarms.check_incidents(problems[window_start:window_end], now)
        for alert in alarms.after_quiet_period(candidates, last_fired, now):
            fired.append(alert)
            last_fired[(alert.alarm, alert.subject)] = now
    now += MINUTE

# ---------- alarm 3: once a day ----------
decline_days = defaultdict(list)
first_day = min(row.day for row in business_days) + timedelta(days=35)  # needs 5 weeks of history
last_day = max(row.day for row in business_days) + timedelta(days=1)
day = first_day
while day <= last_day:
    as_of = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    for alert in alarms.check_declines(business_days, as_of, as_of):
        decline_days[alert.subject].append((day, alert.details["times_worse"]))
    day += timedelta(days=1)

# ---------- report ----------
print(f"limits: source {alarms.SOURCE_LIMIT} per {alarms.SOURCE_WINDOW}, incident "
      f"{alarms.INCIDENT_LIMIT} customers per {alarms.INCIDENT_WINDOW}, decline {alarms.DECLINE_LIMIT}x; "
      f"quiet period {alarms.QUIET_PERIOD}")
print(f"data: {sum(arrival_minutes.values())} requests, {len(problems)} problem items, "
      f"{len(business_days)} business rows\n")
for alarm_name in ("source_flood", "incident"):
    mine = [alert for alert in fired if alert.alarm == alarm_name]
    print(f"{alarm_name}: fired {len(mine)} times")
    for alert in mine:
        print(f"  {alert.fired_at:%Y-%m-%d %H:%M}  {alert.subject:45} {alert.details}")
print(f"\ndecline (daily): {len(decline_days)} subjects")
for subject, days in sorted(decline_days.items()):
    worst = max(times for _, times in days)
    print(f"  {subject:30} {len(days):3} days, {days[0][0]} to {days[-1][0]}, worst {worst}x")
