# ADR 0003: PostgreSQL first, Elasticsearch later for search

Status: Accepted

## Context

Signal needs a system of record with unique keys, joins between feedback, themes and daily business numbers, aggregation, transactions and row-level security. It also needs text search over feedback with filters and pagination. Volume per tenant is modest; the design is driven by bursts, not by steady load. The team is small, so each additional system has a real operational cost.

## Decision

- PostgreSQL is the single source of truth.
- Search starts as PostgreSQL full-text search: a generated `search_vector` column with a GIN index, queried through `websearch_to_tsquery` and ranked by `ts_rank`. Tenant and other filters apply as usual. The `simple` configuration works for any language; per-row language stemming using the enriched `language` column comes next.
- Elasticsearch or OpenSearch is added later as a read copy, never as a replacement. A separate Kafka consumer group indexes enriched events into it, which avoids a dual write. The copy can be dropped and rebuilt from Kafka or PostgreSQL. Customer deletion and the tenant filter must apply there too.

Trigger to add it: product managers need typo-tolerant or cross-language search, or PostgreSQL search becomes too slow.

## Alternatives considered

- **Elasticsearch from day one.** Better relevance and fuzzy matching, but one more cluster to run, secure and keep consistent, for a need not yet proven. Rejected for now.
- **Elasticsearch as the primary store.** Weak transactions, no joins, and unsuitable for uniqueness guarantees. Rejected.
- **DynamoDB or MongoDB.** Horizontal write scaling is not needed at this volume; joins and aggregation are. Rejected.

## Consequences

- One fewer system to operate; transactional consistency between feedback and themes; row-level security available (ADR 0004).
- Search quality is basic at first: no typo tolerance, no cross-language matching.
- PostgreSQL has no horizontal write scaling. This is a one-way door worth revisiting only if writes exceed one primary's limit.
- Connection pools across API and workers must stay under PostgreSQL's limit; add a pooler if workers scale out.
- The later search copy is additive, so introducing it does not change the write path or the source of truth.
