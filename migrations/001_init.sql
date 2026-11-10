-- Signal: first slice (ingest -> feedback). Runs once on a fresh database.

CREATE TABLE tenants (
  tenant_id text PRIMARY KEY
);

-- One key per tenant + channel. Only the hash is stored.
CREATE TABLE api_keys (
  key_hash   text PRIMARY KEY,
  tenant_id  text NOT NULL REFERENCES tenants,
  channel    text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, channel)
);

-- Remembers keys we have already accepted, so repeats get 200 instead of 202.
CREATE TABLE idempotency_keys (
  key         text PRIMARY KEY,
  tenant_id   text NOT NULL,
  feedback_id text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
  feedback_id  text PRIMARY KEY,
  tenant_id    text NOT NULL REFERENCES tenants,
  channel      text NOT NULL,
  source_id    text,
  customer_ref text,                -- salted hash, never the raw id
  market       text,
  language     text,
  text         text NOT NULL,
  created_at   timestamptz NOT NULL, -- when the customer wrote it
  received_at  timestamptz NOT NULL, -- when Signal got it
  sentiment    text,                 -- filled by enrichment (later)
  area         text,
  topic        text,
  kind         text
);
CREATE INDEX feedback_tenant_created ON feedback (tenant_id, created_at DESC);

-- Tenant isolation for the API role (workers use the owner role and bypass it).
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON feedback
  USING (tenant_id = current_setting('app.tenant_id', true));

CREATE ROLE signal_api LOGIN PASSWORD 'signal_api';
GRANT SELECT ON api_keys, feedback TO signal_api;
GRANT SELECT, INSERT ON idempotency_keys TO signal_api;
-- The owner role "signal" is a superuser in the dev container, so it bypasses RLS.
