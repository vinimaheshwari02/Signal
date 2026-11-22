# ADR 0008: Three alarms with a quiet period

Status: Accepted

## Context

Two audiences need alerts. On-call engineers need to hear quickly when something breaks. Product managers need to hear when something is slowly getting worse. A single generic alert would mix very different problems, including problems with the data source itself, and would be noisy. Alerts that fire repeatedly for the same issue lead to alert fatigue.

## Decision

Signal has three alarms, each answering one question:

| Alarm | Question | Fires when (starting values, tunable) | Cadence | Audience |
|---|---|---|---|---|
| 1. Source misbehaving | Is a source sending strange amounts? | Item count from one tenant and channel within a short window exceeds a threshold, counted by arrival time | Every minute | On-call |
| 2. Incident | Did something suddenly break? | At least N different customers report a problem about the same theme within a short window | Every minute | On-call and the PM |
| 3. Slow decline | Is something slowly getting worse? | An area's severity from business numbers rises above a threshold | Daily | The PM |

Rules:

- Alarm 2 counts customers by when they wrote the feedback (`created_at`), after duplicate removal, so a source resending old items cannot trigger it. Items with an estimated time are excluded. It runs per market so a local problem is not diluted.
- Alarm 1 counts by arrival time, so it does catch resends and floods.
- After any alarm, the same subject stays quiet for a fixed period (30 minutes). Every fired alarm is stored in the `alerts` table, which also provides the quiet-period check.
- Thresholds are starting values, tuned by replaying past data. A planned improvement is to compare alarm 2 against each theme's usual rate.
- Operational alerts (consumer lag, non-empty DLQ, request-caused 5xx, stale rankings) are separate and handled through Prometheus.

## Alternatives considered

- **One generic anomaly alert.** Hides the cause and mixes audiences. Rejected.
- **Statistical anomaly detection from the start.** Needs history and tuning. Deferred.
- **No quiet period.** Repeated pages for one incident. Rejected.
- **Daily digest only.** Misses incidents while they are small. Rejected.

## Consequences

- Each alarm is easy to explain and to route to the right audience.
- Fixed thresholds can be too loud for naturally busy themes and too quiet for small tenants; tuning is ongoing work, and alarms should run in shadow mode before they notify anyone.
- The quiet period can delay a notification about a genuinely new phase of an ongoing incident; the stored history keeps the full record.
- Alarm checks run in the scheduler, so scheduler availability matters (see ADR 0005).

## Tuning on the data pack

`scripts/alarm_backtest.py` replays all 90 days through the same checks, minute by minute.
With the starting limits (source 50 requests per 5 minutes, incident 8 customers per 15 minutes,
decline 1.5x, quiet period 30 minutes) it finds exactly the known events and nothing else:

| Alarm | Fired | What it was |
|---|---|---|
| source_flood | 29 Sep 10:14 Ridgeline, 10:16 Harbour Home (support tickets) | A resend: 598 of the 612 items in that window had been sent before |
| incident | 21 Sep 14:12 and 14:42, Ridgeline payments / payment_failed, UK | A payment outage: up to 18 customers in 15 minutes (normal: at most 3) |
| decline | Ridgeline delivery DE (32 days from 18 Sep, worst 2.03x) and AT (8 days, worst 1.54x) | Late deliveries rising in Germany and Austria |

Normal traffic stays far below the limits: even at source 10, incident 5 and decline 1.3 there are
no false alarms, only extra alarms about the same events (other markets in the payment outage,
payment rates in the week after it). The limits can therefore be lowered later if the alarms
should fire earlier.

Two lessons from the data:

- A resend flood consists mostly of duplicates, which are never stored again. The source alarm
  therefore counts requests as they arrive at the API (`arrivals` table), not stored feedback.
- Many items legitimately have a written time equal to their received time, so an estimated time
  cannot be recognised afterwards. The normaliser now records it (`created_at_estimated`), and the
  incident alarm leaves those items out.

## Known limitations and next steps

| Limitation | Possible next step |
|---|---|
| Nothing is sent yet: alerts are stored, logged and listed by `GET /v1/alerts` | Send to Slack or e-mail once the alarms have run in shadow mode for a while |
| The incident alarm counts by the time customers wrote the feedback, so it cannot fire while replaying old data; `alarm_backtest.py` shows it instead | None needed for real traffic, where feedback is written minutes before it arrives |
| The decline alarm fires again every day while the decline lasts | Fire once per episode, then a daily reminder in a digest |
| Fixed limits for all tenants | Per-tenant limits, or limits relative to each source's normal volume |
