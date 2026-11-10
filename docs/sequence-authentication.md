# Sequence: authentication and tenant scoping

How an API key identifies a tenant and how that tenant is enforced in the database. Related: [ADR 0004](adr/0004-tenant-model-and-row-level-security.md).

## Request authentication

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as API
    participant R as Redis
    participant P as PostgreSQL (role signal_api)

    C->>A: Request with X-Api-Key
    A->>A: Hash the presented key
    A->>P: Look up key hash in api_keys (not revoked)
    alt no matching key
        P-->>A: none
        A-->>C: 401 with request_id
    else key found
        P-->>A: tenant_id, channel
        opt write endpoint
            A->>A: Key channel must equal URL channel
            Note right of A: Mismatch gives 403
        end
        A->>R: Increment rate-limit counter for tenant
        alt over limit
            R-->>A: exceeded
            A-->>C: 429 with Retry-After
        else allowed
            R-->>A: ok
            A->>P: BEGIN
            A->>P: SET LOCAL app.tenant_id = tenant_id
            A->>P: Run query or write
            Note over P: Row-level security policy compares tenant_id to the setting
            P-->>A: Only rows of this tenant
            A->>P: COMMIT
            A-->>C: Response
        end
    end
```

## Notes

- Keys are stored only as hashes, scoped to one tenant and one channel, and can be revoked without deleting the row.
- The tenant always comes from the key, never from a header, query parameter or payload field.
- `SET LOCAL` is transaction-scoped, so the setting cannot leak to another request on a pooled connection. If the setting is missing, the policy returns no rows.
- The API database role has row-level security enforced. Workers and the scheduler use a separate internal role that bypasses it, and take the tenant from the Kafka envelope or iterate tenants themselves.
- The key lookup itself happens before the tenant is known, so it uses a narrowly scoped lookup that only reads `api_keys`.
- `/health` is unauthenticated; `/metrics` is reachable on the internal network only.
- Read endpoints never return customer references or personal data.
