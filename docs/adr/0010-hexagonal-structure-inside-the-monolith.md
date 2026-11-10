# ADR 0010: Hexagonal structure inside the monolith

Status: Accepted (refines ADR 0005)

## Context

ADR 0005 keeps one codebase with several entry points. Inside it, the first slice put business rules (checks, idempotency, publish-then-remember) directly in HTTP routes next to Kafka and PostgreSQL calls. Those rules could only be tested with a running broker and database, and every new entry point risked copying them.

## Decision

Structure the code as ports and adapters:

- `core/`: models, errors, pure functions and use cases (`IngestFeedback`, `ListFeedback`). It depends only on the standard library and on small `Protocol` interfaces in `core/ports.py`. A test fails if core imports a web framework or a database or broker driver.
- `adapters/`: implementations of the ports (FastAPI routes, Kafka, PostgreSQL). They translate between the outside world and core, including mapping core errors to HTTP statuses.
- `entrypoints/`: the only place where adapters are chosen and wired into use cases (`api`, `worker`).

This changes structure only. Behaviour, deployment (one image, several entry points) and ADR 0005 stay as they are.

## Alternatives considered

- **Keep logic in routes.** Least code, but business rules need infrastructure to be tested and get duplicated per entry point. Rejected.
- **Separate services per layer or port.** Stronger isolation, but network contracts and operations cost for no current need (same reasoning as ADR 0005). Rejected.

## Consequences

- Use cases are tested quickly with in-memory fakes; adapters stay thin.
- Swapping or adding an adapter (another queue, another store) does not touch the rules.
- More files and a little indirection for a small codebase.
- The boundary relies on discipline plus the architecture test; it is not enforced by the language.
