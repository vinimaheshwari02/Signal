-- Signal: business numbers and ranked themes (ADR 0007).
-- On a fresh database this runs automatically after 001_init.sql. On an existing one, run it once:
--   docker compose exec -T postgres psql -U signal -d signal < migrations/002_themes.sql

-- One row per day x tenant x market, loaded from business_daily.csv.
CREATE TABLE business_daily (
  tenant_id         text NOT NULL,
  market            text NOT NULL,
  day               date NOT NULL,
  orders            integer NOT NULL,
  revenue_gbp       numeric(12, 2) NOT NULL,
  payment_attempts  integer NOT NULL,
  payment_failures  integer NOT NULL,
  deliveries_due    integer NOT NULL,
  deliveries_late   integer NOT NULL,
  returns_requested integer NOT NULL,
  search_sessions   integer NOT NULL,
  PRIMARY KEY (tenant_id, market, day)
);

-- The latest ranking, replaced in full by every scheduler run.
CREATE TABLE themes (
  tenant_id           text NOT NULL,
  theme_id            text NOT NULL,          -- tenant|area|topic, stable between runs
  area                text NOT NULL,
  topic               text NOT NULL,
  score               double precision NOT NULL,
  problem_customers   integer NOT NULL,
  last_week_customers integer NOT NULL,
  trend               text NOT NULL,          -- rising / falling / stable
  customers_by_market jsonb NOT NULL,
  evidence            jsonb NOT NULL,
  as_of               timestamptz NOT NULL,   -- the moment the 7-day window ends
  computed_at         timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, theme_id)
);

-- The scheduler reads the problems of the last two weeks for every tenant.
CREATE INDEX feedback_problems_by_time ON feedback (created_at) WHERE kind = 'problem';

-- Same tenant isolation as feedback: the API role only sees the tenant set on its transaction.
ALTER TABLE business_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_daily FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_daily
  USING (tenant_id = current_setting('app.tenant_id', true));

ALTER TABLE themes ENABLE ROW LEVEL SECURITY;
ALTER TABLE themes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON themes
  USING (tenant_id = current_setting('app.tenant_id', true));

GRANT SELECT ON business_daily, themes TO signal_api;
