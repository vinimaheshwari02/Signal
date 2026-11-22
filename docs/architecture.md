# Architecture overview

The four structural diagrams, as built in November 2026. Behaviour is in the sequence documents;
decisions are in `adr/`. The original design had more parts (Redis, Prometheus, retry and
dead-letter topics); what differs is listed under "As built" in the sequence documents.

## 1. System context

Who uses Signal and what flows in and out.

```mermaid
flowchart LR
    SRC[Source systems<br/>support tickets, app store, NPS,<br/>in-app, social]
    BIZ[Business data<br/>daily orders, payments, deliveries]
    PM[Product managers]
    OPS[Support and on-call leads]
    S((Signal<br/>feedback intelligence))

    SRC -->|POST feedback, API key per tenant and channel| S
    BIZ -->|CSV, loaded by a script| S
    PM -->|GET themes, feedback| S
    OPS -->|GET alerts| S
```

Two tenants (Ridgeline, Harbour Home) share one system. Signal sends nothing out yet: alarms are
stored and listed, not delivered.

## 2. Containers

The running parts and how they talk. One codebase and one image run as three processes (ADR 0005).

```mermaid
flowchart LR
    SRC[Sources] -->|POST /v1/sources/channel/feedback| API
    USR[Product teams] -->|GET feedback, themes, alerts| API
    API[api<br/>FastAPI] -->|publish, acks=all| K[(Kafka / Redpanda<br/>topic feedback.raw)]
    K -->|consume| W[worker]
    API -->|keys, idempotency, arrivals, reads under RLS| PG[(PostgreSQL)]
    W -->|insert labelled feedback| PG
    SCH[scheduler] -->|themes every 5 min, alarms every minute| PG
```

| Container | Responsibility | Database role |
|---|---|---|
| `api` | Authenticate, normalise, mask PII, publish; serve reads | `signal_api` (restricted, row-level security) |
| `worker` | Enrich each message and save it once | `signal` (owner) |
| `scheduler` | Rank themes, check alarms | `signal` (owner) |
| `redpanda` | Durable log between API and worker | – |
| `postgres` | System of record | – |

## 3. Backend modules

Hexagonal structure inside the monolith (ADR 0010). Dependencies point inward: `core/` imports
nothing from `adapters/` or any framework, and `tests/test_architecture.py` enforces it.

```mermaid
flowchart TB
    subgraph entry[entrypoints: build and wire]
        EA[api.py]
        EW[worker.py]
        ES[scheduler.py]
    end
    subgraph core[core: business logic, no framework imports]
        ING[ingest.py<br/>IngestFeedback]
        NOR[normalise.py<br/>one mapper per channel]
        PRO[process.py<br/>ProcessFeedback]
        ENR[enrich.py + taxonomy.py]
        THM[themes.py + theme_jobs.py]
        ALM[alarms.py + alarm_jobs.py]
        AUT[auth.py, query.py, ids.py]
        PRT[ports.py<br/>interfaces]
    end
    subgraph adapters[adapters: technology]
        HTTP[http/app.py]
        KAF[kafka.py]
        PGA[postgres.py]
        CLK[clock.py]
    end
    EA --> ING
    EA --> THM
    EA --> ALM
    EW --> PRO
    ES --> THM
    ES --> ALM
    ING --> NOR
    PRO --> ENR
    ING --> PRT
    PRO --> PRT
    THM --> PRT
    ALM --> PRT
    HTTP -.->|calls use cases| ING
    KAF -.->|implements| PRT
    PGA -.->|implements| PRT
    CLK -.->|implements| PRT
```

## 4. Entity-relationship diagram

Eight tables in three migrations. `feedback`, `themes`, `alerts` and `business_daily` have a
row-level security policy on `tenant_id`.

```mermaid
erDiagram
    tenants ||--o{ api_keys : "has"
    tenants ||--o{ feedback : "owns"
    tenants ||..o{ idempotency_keys : "tenant_id"
    tenants ||..o{ themes : "tenant_id"
    tenants ||..o{ alerts : "tenant_id"
    tenants ||..o{ arrivals : "tenant_id"
    tenants ||..o{ business_daily : "tenant_id"

    tenants { text tenant_id PK }
    api_keys { text key_hash PK
               text tenant_id FK
               text channel }
    idempotency_keys { text key PK
                       text tenant_id
                       text feedback_id }
    feedback { text feedback_id PK
               text tenant_id FK
               text channel
               text source_id
               text customer_ref
               text market
               text language
               text text
               timestamptz created_at
               boolean created_at_estimated
               timestamptz received_at
               text sentiment
               text kind
               text area
               text topic }
    business_daily { text tenant_id PK
                     text market PK
                     date day PK
                     int orders
                     numeric revenue_gbp
                     int payment_attempts
                     int payment_failures
                     int deliveries_due
                     int deliveries_late
                     int returns_requested }
    themes { text tenant_id PK
             text theme_id PK
             float score
             int problem_customers
             int last_week_customers
             text trend
             jsonb evidence
             timestamptz as_of }
    arrivals { text tenant_id PK
               text channel PK
               timestamptz minute PK
               int requests }
    alerts { bigint alert_id PK
             text tenant_id
             text alarm
             text subject
             timestamptz fired_at
             jsonb details }
```

Solid lines are foreign keys; dotted lines are a `tenant_id` column without a foreign key.
`feedback_id` is derived from the idempotency key, so saving the same item twice leaves one row.
