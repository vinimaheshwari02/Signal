# ADR 0011: Prometheus and Grafana for monitoring

Status: Accepted

## Context

Signal runs three processes (api, worker, scheduler) plus Kafka and PostgreSQL. Without metrics the
only way to know whether it works is to read logs or call the API by hand. Questions an on-call
person needs answered quickly:

- Are all processes running?
- Are requests failing, and is it our fault (5xx) or bad input (4xx)?
- Is the API fast enough?
- Is the worker keeping up with Kafka, or is a backlog growing?
- Did the scheduler recompute the themes recently?

ADR 0008 already separates these operational alerts from the business alarms, and ADR 0009 named
Prometheus client metrics. This ADR records how they are built.

## Decision

- Each process exposes its own numbers in the Prometheus text format with `prometheus-client`:
  the API on `GET /metrics`, the worker and scheduler on a small server on `METRICS_PORT` (9100).
- Prometheus collects them every 15 seconds (pull model) and evaluates the alert rules in
  `monitoring/alerts.yml`.
- Grafana shows one provisioned dashboard, "Signal overview", loaded from a JSON file in the
  repository, so it is versioned and reviewed like code.
- Metrics follow the RED method for the API (rate, errors, duration) plus lag for the worker and
  last-success time for the scheduler.
- Labels use a small fixed set of values: route templates instead of raw paths, known channels
  only (others become `unknown`), so a caller cannot create unlimited time series.
- Metrics code lives in `adapters/metrics.py` and the entry points; `core/` stays free of it
  (ADR 0010).
- Alert rules have unit tests (`promtool test rules`) that run in CI.

## Alternatives considered

- **Logs only.** Free, but answering "how many 5xx in the last 5 minutes" means searching text.
  No alerting. Rejected.
- **A hosted service (Datadog, New Relic, Grafana Cloud).** Less to run, but costs money, needs an
  account and an agent, and does not run offline on a laptop for the demo. A good choice in a
  company that already uses one.
- **OpenTelemetry metrics with a collector.** One standard for metrics, logs and traces, but more
  moving parts. Prometheus metrics can be exported through OpenTelemetry later without changing
  the dashboards. Deferred.
- **Push (StatsD).** The processes would send numbers out. Pull lets Prometheus also notice when a
  process stops answering (`up == 0`), which push cannot. Rejected.

## Consequences

- `docker compose up` gives a working dashboard and alert page with no extra setup.
- Two more containers to run; Prometheus keeps 15 days of data in a volume.
- Alerts are visible but not sent until Alertmanager is added.
- Metrics are per process. Several API processes in one container would need multiprocess mode;
  scaled workers need service discovery (Kubernetes) to be scraped one by one.
- The API's `/metrics` shares the public port and must be blocked at the ingress in production.
