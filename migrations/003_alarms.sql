-- Signal: alarms (ADR 0008).
-- On a fresh database this runs automatically after 002_themes.sql. On an existing one, run it once:
--   docker compose exec -T postgres psql -U signal -d signal < migrations/003_alarms.sql

-- True when the customer's time was missing or unusable and received_at was used instead.
-- The incident alarm leaves these items out.
ALTER TABLE feedback ADD COLUMN created_at_estimated boolean NOT NULL DEFAULT false;

-- Requests per tenant, channel and minute, counted by the API as they arrive, duplicates included
-- (a source resending old items is what the source alarm looks for). Counts only, no customer data.
CREATE TABLE arrivals (
  tenant_id text NOT NULL,
  channel   text NOT NULL,
  minute    timestamptz NOT NULL,
  requests  integer NOT NULL,
  PRIMARY KEY (tenant_id, channel, minute)
);
GRANT SELECT, INSERT, UPDATE ON arrivals TO signal_api;

-- Every alarm that fired. The quiet period reads the latest one per subject.
CREATE TABLE alerts (
  alert_id  bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  alarm     text NOT NULL,          -- source_flood / incident / decline
  subject   text NOT NULL,          -- what it is about, e.g. ridgeline|support_ticket
  fired_at  timestamptz NOT NULL,
  details   jsonb NOT NULL
);
CREATE INDEX alerts_latest ON alerts (alarm, subject, fired_at DESC);
CREATE INDEX alerts_by_tenant ON alerts (tenant_id, fired_at DESC);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON alerts
  USING (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT ON alerts TO signal_api;
