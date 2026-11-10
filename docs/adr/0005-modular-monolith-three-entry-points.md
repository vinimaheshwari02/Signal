# ADR 0005: Modular monolith with three entry points

Status: Accepted

## Context

Signal is built by a very small team on a short timeline, deployed locally with containers. It still has clearly different runtime profiles: a latency-sensitive HTTP API, throughput-oriented stream processing, and timed jobs (theme recompute, alarm checks, daily business data load). Independent scaling matters mainly for workers, which are CPU-bound during enrichment.

## Decision

One codebase, organised into modules, deployed from one image with three entry points:

- **API**: ingest, query and privacy modules (FastAPI).
- **Worker**: normalise then enrich, consuming from Kafka and writing to PostgreSQL.
- **Scheduler**: themes, alerts and business modules on timers.

Modules (ingest, normalise, enrich, themes, business, alerts, query, privacy) communicate through function interfaces and shared building blocks (storage, messaging, cache, taxonomy config, masking and hashing, metrics). They never read each other's tables directly. Boundaries are enforced by review and tests, for example import-linting.

## Alternatives considered

- **Microservices.** Independent deploys and scaling, but network boundaries, versioned contracts, distributed tracing and many pipelines for no current organisational need. Rejected.
- **Single process doing everything.** Simplest, but a burst of CPU-bound enrichment would starve the API and break latency targets. Rejected.
- **Serverless functions.** Poor fit for long-lived Kafka consumers and connection pooling. Rejected.

## Consequences

- Simple deploys, debugging and local development; one dependency set and one CI pipeline.
- Workers scale independently of the API, up to one per Kafka partition.
- Less independent scaling and fault isolation than microservices; a bad release affects all entry points unless rolled back.
- Because modules talk through interfaces, any module (the enrichers first) can later be extracted into its own service. This is a two-way door as long as module boundaries hold.
- The scheduler must be a single active instance or use a lock so timed jobs do not run twice.
