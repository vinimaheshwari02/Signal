# ADR 0002: Idempotency key and publish-first-then-save

Status: Accepted

## Context

Senders retry on timeouts, some resend historical items, and some send no stable identifier at all. With at-least-once delivery (ADR 0001) duplicates would inflate theme counts and trigger false alarms. Equally, losing an accepted item is unacceptable.

## Decision

Every submission gets a deterministic idempotency key, computed as a SHA-256 hash over the first available of:

1. `tenant + channel + source_id`, when the payload carries the source's own identifier;
2. otherwise the `Idempotency-Key` request header (scoped to tenant and channel);
3. otherwise a hash of the canonicalised payload (stable key ordering and whitespace).

Ingest flow:

1. Look up `(tenant_id, idempotency_key)`. If it exists, return `200` with the original `feedback_id`.
2. Otherwise derive `feedback_id` from the key, so the same submission always gets the same ID.
3. Publish to Kafka and wait for `acks=all`.
4. Only then save the idempotency key and return `202`.

Publish comes before save on purpose. A crash between steps 3 and 4 can leave a duplicate message in Kafka, but never a lost item. Because `feedback_id` is derived from the key and the worker write is an upsert on `(tenant_id, feedback_id)`, the duplicate collapses downstream. Idempotency rows expire after the retention window of the raw log.

## Alternatives considered

- **Trust the sender's header only.** Simple, but many senders do not send it or send unstable values. Rejected as the sole mechanism.
- **Save the key first, then publish.** A crash or Kafka failure after the save would make retries return `200` for an item that was never published: a lost item. Rejected.
- **Exactly-once semantics (transactions across Kafka and PostgreSQL).** Complex and still not end-to-end across the HTTP boundary. Rejected in favour of at-least-once plus idempotent steps.
- **Random server-generated IDs.** Cannot detect resends. Rejected.

## Consequences

- Retries and resends from buggy senders are harmless, and duplicates return the original `feedback_id`.
- Rare duplicate Kafka messages are possible and must be tolerated: every step (normalise, enrich, save, publish downstream) is safe to repeat.
- The payload-hash fallback treats two genuinely distinct but byte-identical payloads as one; this is accepted and documented.
- Canonicalisation rules are part of the contract; changing them changes keys, so they must be versioned carefully.
- A source that resends old items produces `200` responses, which feeds the "source misbehaving" alarm rather than theme counts.
