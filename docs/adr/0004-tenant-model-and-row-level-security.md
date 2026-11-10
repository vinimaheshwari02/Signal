# ADR 0004: Tenant model with shared tables and row-level security

Status: Accepted

## Context

Signal is a shared platform. A tenant is a retailer or brand. Each tenant must only ever see its own data, and onboarding a new tenant must be configuration, not code or schema changes. A forgotten `WHERE tenant_id = ...` in a query is the most likely way to leak data across tenants.

## Decision

- All tenants share the same tables. Every table carries `tenant_id`, and queries filter on it.
- PostgreSQL row-level security (RLS) is enabled with one policy per table, enforced for the API database role.
- Three database roles:

| Component | Role | RLS | Source of tenant |
|---|---|---|---|
| API service (queries, deletion, idempotency check) | `signal_api` | On | The API key |
| Workers | `signal_internal` | Bypassed | Kafka message envelope set by the API, never the payload |
| Scheduler | `signal_internal` | Bypassed | Iterates over tenants itself |

- A shared request helper runs `SET LOCAL app.tenant_id` once per request, inside the transaction, using the tenant resolved from the API key. Policies compare `tenant_id` to that setting.
- For workers, which bypass RLS, a unit test asserts that saved rows always carry the envelope's `tenant_id`.
- API keys are stored hashed, bound to one tenant and one channel.

## Alternatives considered

- **Tenant filter in application code only.** Cheapest, but one missed filter leaks data. Rejected.
- **Schema per tenant.** Needs the same per-request setting (the search path), plus copied tables and per-tenant migrations, and makes cross-tenant operations harder. Rejected.
- **Database per tenant.** Strongest isolation, highest operational cost. Reserved for a tenant that needs contractual isolation.

## Consequences

- The database guarantees isolation for every user-facing query, even if a developer forgets the filter.
- Cost: one setting per API request and one policy per table. Tests must cover each policy and the fail-safe case (no setting means no rows).
- Workers and scheduler rely on code and tests for correctness of `tenant_id`, which is a residual risk (see the threat model).
- Connection pooling must be compatible with `SET LOCAL` (transaction-scoped settings).
- This is a one-way door: moving to schema- or database-per-tenant later is a data migration. Review time should go here.
