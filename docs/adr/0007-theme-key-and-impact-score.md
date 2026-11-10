# ADR 0007: Theme key and impact score

Status: Accepted

## Context

Product managers need a ranked list of problems. Counting mentions alone points at loud but cheap complaints. Business numbers (late deliveries, payment failures, returns, orders) show which areas are actually getting worse, but they exist per area and per day, not per topic, and some tenants may not provide them. Themes must be stable between recomputations so trends and alerts can refer to them.

## Decision

**Theme key.** A theme is identified by `tenant | area | topic` (for example `t1|delivery|delay`). The same key produces the same `theme_id` on every recomputation. Feedback links to a theme logically by those three fields rather than by foreign key, so reclassifying an item moves it automatically.

**Impact score.**

```
score = problem customers x severity
```

- Problem customers: unique customers with kind `problem` in the last 7 days, per market (anonymous items count one each).
- Severity: for areas with a linked business rate, the rate over the last 7 days divided by that tenant, market and area's normal (average over the previous 4 weeks). Values below 1 are clamped to 1, so good numbers never shrink a problem. Areas with no linked rate, unknown markets, and tenants with no business numbers use severity 1.
- Score is computed per market and summed across markets.
- Evidence is shown next to the score: current and normal rate, how many times worse, extra affected orders, and their estimated value. Money is evidence, not the score.

Linked rates by area: delivery (late over due), payments (failures over attempts), returns (requested over orders), checkout (orders compared with normal, lower is worse). Search, account and general have none.

**Trend.** Problem customers this week against last week: more than +20% is rising, below -20% is falling, otherwise stable.

**Recompute.** The scheduler recomputes all themes in full on a fixed short interval. The last good ranking is kept if a run fails.

## Alternatives considered

- **Customer count only.** Simple, but ignores business impact. Rejected.
- **Money at risk as the score.** Needs per-topic business data that does not exist, and an estimate that is too rough to rank by. Rejected as the score; kept as evidence.
- **Embedding or keyword clusters as themes.** Unstable and hard to explain. Rejected (see ADR 0006).
- **Incremental counters.** Faster, but risk of drift. Full recompute is chosen until it takes too long.

## Consequences

- Every area can rank, since customers drive the base score.
- Real problems are boosted by hard evidence; resent or repeated feedback is not, because it does not move business numbers.
- The score is explainable as "customers x how many times worse than normal".
- All topics in an area share the area's severity; customer counts separate them.
- Severity updates daily, because business numbers are daily; sudden incidents are caught earlier by the alarms (ADR 0008).
- Taxonomy changes rename or split themes, so they need care.
