# Sequence: processing

How a worker turns a raw message into a labelled feedback item, and how themes and alarms are derived from it. Related: [ADR 0006](adr/0006-rule-based-enrichment.md), [ADR 0007](adr/0007-theme-key-and-impact-score.md), [ADR 0008](adr/0008-three-alarms-with-quiet-period.md).

## Per-item processing

```mermaid
sequenceDiagram
    autonumber
    participant K as Kafka (feedback.ingested)
    participant W as Worker
    participant P as PostgreSQL
    participant KE as Kafka (feedback.enriched)
    participant KR as Kafka (retry topic)
    participant D as Kafka (feedback.dlq)

    K->>W: Deliver message (tenant_id from envelope)
    W->>W: Normalise with the channel mapper and messy-data rules
    W->>W: Hash customer reference
    W->>W: Enrich: language, sentiment, kind, area, topic
    alt processing succeeds
        W->>P: Upsert feedback item on (tenant_id, feedback_id)
        P-->>W: ok
        W->>KE: Publish enriched event
        W->>K: Commit offset
    else transient or item failure
        W->>KR: Publish to retry topic with backoff and jitter
        W->>K: Commit offset
        KR->>W: Redeliver after delay
        Note over W,D: After the maximum number of tries the message goes to feedback.dlq
        W->>D: Publish to dead-letter topic
    end
```

## Periodic jobs

```mermaid
sequenceDiagram
    autonumber
    participant SC as Scheduler
    participant P as PostgreSQL
    participant R as Redis
    participant PR as Prometheus
    participant OC as On-call and PMs

    loop every few minutes
        SC->>P: Read problem customers and business rates per tenant
        SC->>SC: Compute severity, score, evidence, trend
        SC->>P: Upsert themes
        SC->>R: Invalidate cached rankings
    end
    loop every minute
        SC->>P: Count items for source and incident alarms
        SC->>P: Check alerts table for quiet period
        opt threshold crossed and not in quiet period
            SC->>P: Store alert
            SC->>PR: Expose alert metric
            PR->>OC: Notify
        end
    end
    loop daily
        SC->>P: Load daily business numbers
        SC->>P: Check area severity for slow decline
    end
```

## Notes

- Delivery is at-least-once. The offset is committed only after the write succeeds, and the write is an upsert, so a crash mid-item just means the item is processed again without a duplicate.
- The tenant for a worker write comes from the message envelope set by the API, never from the payload. Workers use the internal database role, which bypasses row-level security, so a test checks that stored rows carry the envelope tenant.
- A single failing enricher does not fail the item: the other labels are saved, the failure is marked, and it is retried.
- A message that exhausts its retries lands in the dead-letter topic so it cannot block its partition; a non-empty DLQ raises an operational alert.
- If a theme run fails, the last good rankings stay in place and a stale-rankings alert fires when they get too old.
- After any alarm, the same subject stays quiet for a fixed period.
