# ADR 0001: Kafka (Redpanda locally) as the durable ingest log

Status: Accepted

## Context

Signal accepts feedback from several channels. Senders retry, resend old items and sometimes send bursts far above normal volume. Two requirements drive the choice of broker:

- No accepted item may ever be lost. The API only answers `202` once the item is durably stored.
- Processing is async. Several independent consumers (normalise/enrich workers now, a search indexer later) must be able to read the same stream, and recent data must be replayable when a normaliser or enricher improves.

Raw payloads are not stored in PostgreSQL (data minimisation). The ingest log therefore is the only copy of the raw input and must keep it for a bounded retention window.

## Decision

Use Apache Kafka as the durable ingest log, with Redpanda as the Kafka-compatible broker for local development.

- The API publishes to `feedback.ingested` with `acks=all` and waits for confirmation before returning `202`.
- Topics are keyed by `feedback_id` so load spreads evenly across partitions.
- Raw payloads are retained for a fixed window (7 days) and act as the replay source.
- Workers form a consumer group; parallelism is capped by the partition count.
- Failures go to a retry topic with exponential backoff and jitter. After the maximum attempts a message moves to `feedback.dlq`, so a poison message never blocks its partition.
- Delivery is at-least-once; every downstream step is idempotent (see ADR 0002).

## Alternatives considered

- **RabbitMQ.** Simpler operationally and has built-in retry/dead-letter exchanges, but messages are consumed and removed. There is no replay, and adding a second independent consumer means duplicating queues. Rejected because replay and multiple consumers are core needs.
- **Redis Streams.** Light and already in the stack, but weaker durability guarantees and a smaller ecosystem for consumer groups and retention. Rejected for a "never lose" requirement.
- **Write directly to PostgreSQL and poll.** Fewer moving parts, but couples ingest latency to database write capacity during a burst and stores raw personal data. Rejected.
- **Synchronous processing in the request.** Slow responses cause sender timeouts and retries, which increases load. Rejected.

## Consequences

- Positive: bursts are absorbed by the log; consumers catch up at their own pace; recent data can be reprocessed by replaying the topic; new consumers (for example a search indexer) can be added without touching the producer.
- Negative: retry and DLQ handling must be built by hand; Kafka is another stateful component to run and monitor (consumer lag, DLQ size become key metrics).
- Kafka and PostgreSQL are the single points of failure locally; production would run both with replicas across availability zones.
- If Kafka is unavailable the API fails closed: it returns `503` with `Retry-After` and never `202`.
- Reprocessing is limited to the retention window.
