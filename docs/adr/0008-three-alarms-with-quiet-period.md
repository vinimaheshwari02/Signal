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
