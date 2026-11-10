# ADR 0009: Python 3.12 and FastAPI stack

Status: Accepted

## Context

Signal is built by one developer on a short timeline. The workload is I/O-bound in the API (HTTP, Kafka, PostgreSQL, Redis) and text-processing-bound in workers. The API is the product, so a versioned, documented REST interface with strict validation matters. The Python ecosystem has mature open-source libraries for language detection and sentiment, which suits rule-based enrichment (ADR 0006).

## Decision

- Python 3.12 for all three entry points (ADR 0005).
- FastAPI (ASGI) for the API: typed request and response models, automatic OpenAPI documentation, dependency injection for authentication and the tenant-scoped database session.
- A single error format carrying a `request_id`; cursor pagination for lists; a global exception handler so unexpected errors on bad input never surface as 5xx.
- Async clients for Kafka, PostgreSQL and Redis in the API; worker processes scale by adding processes up to the partition count.
- Prometheus client metrics, structured JSON logs and OpenTelemetry traces in every entry point.
- Containerised with Docker; CI runs lint, tests and the image build.

## Alternatives considered

- **Go or Java/Kotlin.** Higher raw throughput, but slower to build for one developer and a weaker fit for text-processing libraries. Not needed at this volume. Rejected.
- **Node.js/TypeScript.** Good for the API, weaker for NLP libraries. Rejected.
- **Django or Flask.** Django brings an ORM and admin that are not needed; Flask lacks built-in validation and OpenAPI. Rejected.

## Consequences

- Fast development and automatic API documentation; a single language across API, workers and scheduler.
- The Python GIL limits CPU-bound parallelism per process, so enrichment scales by running more worker processes. Enrichment CPU is the likely first bottleneck.
- Async code requires discipline: no blocking calls in request handlers.
- Because modules sit behind interfaces, a hot path could later be rewritten in another language without changing the architecture.
