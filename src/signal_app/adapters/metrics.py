"""Prometheus metrics for the three processes (api, worker, scheduler).

Each process keeps its own numbers in memory. Prometheus asks for them every 15 seconds:
- the API answers on its own port at GET /metrics
- the worker and the scheduler start a tiny metrics server on METRICS_PORT (9100)

Three kinds of metric are used:
- Counter:   only goes up (requests served, messages processed). Prometheus turns it into a rate.
- Histogram: counts values into buckets (how long requests take), so we can ask for p50 / p99.
- Gauge:     a value that goes up and down (messages still waiting in Kafka).

The scheduler's label is called `task`, not `job`: Prometheus adds its own `job` label (api,
worker, scheduler) to everything it collects, and the two would clash.

Labels keep a small, fixed set of values (route templates, not raw paths; known channels only),
because every label combination becomes a separate time series in Prometheus.
"""
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from ..core.normalise import NORMALISERS

# --- API -------------------------------------------------------------------------------------
HTTP_REQUESTS = Counter(
    "signal_http_requests_total", "HTTP requests answered by the API",
    ["method", "route", "status"])
HTTP_DURATION = Histogram(
    "signal_http_request_duration_seconds", "Time to answer one HTTP request",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
FEEDBACK_RECEIVED = Counter(
    "signal_feedback_received_total", "Feedback items posted to the ingest endpoint, by result",
    ["channel", "status"])

# --- Worker ----------------------------------------------------------------------------------
WORKER_MESSAGES = Counter(
    "signal_worker_messages_total", "Kafka messages handled by the worker",
    ["result"])  # saved | skipped (unreadable) | retry (database problem)
WORKER_DURATION = Histogram(
    "signal_worker_processing_seconds", "Time to label and save one message",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1))
WORKER_LAG = Gauge(
    "signal_worker_lag_messages", "Messages in Kafka not yet processed by this worker",
    ["partition"])

# --- Scheduler -------------------------------------------------------------------------------
JOB_RUNS = Counter(
    "signal_scheduler_task_runs_total", "Scheduler task runs",
    ["task", "result"])  # task: themes | alarms | declines; result: ok | failed
JOB_DURATION = Histogram(
    "signal_scheduler_task_duration_seconds", "Time one scheduler task takes", ["task"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60))
JOB_LAST_SUCCESS = Gauge(
    "signal_scheduler_last_success_timestamp_seconds", "When the task last finished without error",
    ["task"])
ALERTS_FIRED = Counter(
    "signal_alerts_fired_total", "Business alarms fired (ADR 0008)", ["alarm"])
THEMES_RANKED = Gauge(
    "signal_themes_ranked", "Themes in the latest ranking, all tenants together")


def channel_label(channel: str) -> str:
    """The channel comes from the URL, so anyone can send any value. Unknown ones share one label."""
    if channel in NORMALISERS:
        return channel
    return "unknown"


def serve_metrics(port: int) -> None:
    """For the worker and the scheduler: answer GET /metrics on `port` in a background thread."""
    start_http_server(port)
