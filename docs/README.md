# Architecture documentation

| # | Required item | Document |
|---|---|---|
| 1 | System context diagram | [architecture.md](architecture.md#1-system-context) |
| 2 | Container diagram | [architecture.md](architecture.md#2-containers) |
| 3 | Backend module diagram | [architecture.md](architecture.md#3-backend-modules) |
| 4 | Entity-relationship diagram | [architecture.md](architecture.md#4-entity-relationship-diagram) |
| 5 | Submission sequence (order submission in the template) | [sequence-ingestion.md](sequence-ingestion.md) |
| 6 | Processing sequence (order execution in the template) | [sequence-processing.md](sequence-processing.md) |
| 7 | Authentication sequence | [sequence-authentication.md](sequence-authentication.md) |
| 8 | Deployment diagram | [deployment.md](deployment.md) |
| 9 | Threat model | [threat-model.md](threat-model.md) |
| 10 | API documentation | [api.md](api.md), plus the live OpenAPI page at `/docs` |
| 11 | Architecture Decision Records (10) | [adr/](adr/) |

Also here: [load-test.md](load-test.md) (method and numbers) and [demo.md](demo.md) (the 3-minute demo).

The template speaks of orders; in Signal the thing submitted and processed is a piece of feedback.
