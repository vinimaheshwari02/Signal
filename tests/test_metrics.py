"""The Prometheus metrics: what each process counts. Prometheus itself is not needed here.

Metrics are global per process and other tests also bump them, so every test compares
"before" and "after" instead of expecting an exact total.
"""
from datetime import timedelta
from unittest.mock import create_autospec

import pytest
from confluent_kafka import Consumer, Message, TopicPartition
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from signal_app.adapters.http.app import create_app
from signal_app.adapters.kafka import handle_one, update_lag
from signal_app.core.alarms import Alert
from signal_app.core.ingest import IngestFeedback
from signal_app.core.query import ListFeedback
from signal_app.core.themes import ProblemItem
from signal_app.core.theme_jobs import RecomputeThemes
from signal_app.entrypoints.scheduler import check_alarms_now, run_once

from .fakes import (NOW, FixedClock, InMemoryApiKeyDirectory, InMemoryFeedbackRepository,
                    InMemoryKeyStore, InMemoryPublisher, InMemoryThemeInputs, InMemoryThemeStore)

URL = "/v1/sources/support_ticket/feedback"
BODY = {"ticket": {"id": "M-1", "created": 1700000000000, "description": "Parcel never arrived",
                   "requester": {"customer_ref": "C1", "locale": "en-GB"}}}
H = {"X-Api-Key": "sk_metrics"}


def value(name: str, **labels) -> float:
    """The current value of one metric series; 0 if it has never been touched."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def api():
    keys = InMemoryApiKeyDirectory({"sk_metrics": ("ridgeline", "support_ticket")})
    publisher = InMemoryPublisher()
    ingest = IngestFeedback(publisher, InMemoryKeyStore(), keys, FixedClock(), "salt", 1024)
    return TestClient(create_app(ingest, ListFeedback(InMemoryFeedbackRepository(), keys))), publisher


# --- API ---------------------------------------------------------------------------------------

def test_a_request_is_counted_by_route_template_and_status(api):
    client, _ = api
    before = value("signal_http_requests_total", method="POST", route="/v1/sources/{channel}/feedback",
                   status="202")
    assert client.post(URL, json={**BODY, "ticket": {**BODY["ticket"], "id": "M-2"}}, headers=H).status_code == 202
    after = value("signal_http_requests_total", method="POST", route="/v1/sources/{channel}/feedback",
                  status="202")
    assert after == before + 1


def test_the_time_of_each_request_goes_into_the_histogram(api):
    client, _ = api
    before = value("signal_http_request_duration_seconds_count", method="GET", route="/health")
    client.get("/health")
    assert value("signal_http_request_duration_seconds_count", method="GET", route="/health") == before + 1


def test_feedback_is_counted_per_channel_and_result(api):
    client, _ = api
    body = {**BODY, "ticket": {**BODY["ticket"], "id": "M-3"}}
    accepted = value("signal_feedback_received_total", channel="support_ticket", status="202")
    duplicate = value("signal_feedback_received_total", channel="support_ticket", status="200")
    client.post(URL, json=body, headers=H)
    client.post(URL, json=body, headers=H)  # the same item again
    assert value("signal_feedback_received_total", channel="support_ticket", status="202") == accepted + 1
    assert value("signal_feedback_received_total", channel="support_ticket", status="200") == duplicate + 1


def test_a_made_up_channel_does_not_create_a_new_label(api):
    client, _ = api
    before = value("signal_feedback_received_total", channel="unknown", status="404")
    client.post("/v1/sources/anything-at-all/feedback", json=BODY, headers=H)
    assert value("signal_feedback_received_total", channel="unknown", status="404") == before + 1
    assert value("signal_feedback_received_total", channel="anything-at-all", status="404") == 0


def test_an_unknown_path_shares_one_label(api):
    client, _ = api
    before = value("signal_http_requests_total", method="GET", route="unmatched", status="404")
    client.get("/no/such/page/123")
    assert value("signal_http_requests_total", method="GET", route="unmatched", status="404") == before + 1


def test_a_kafka_outage_shows_up_as_503(api):
    client, publisher = api
    publisher.fail = True
    before = value("signal_feedback_received_total", channel="support_ticket", status="503")
    assert client.post(URL, json={**BODY, "ticket": {**BODY["ticket"], "id": "M-4"}}, headers=H).status_code == 503
    assert value("signal_feedback_received_total", channel="support_ticket", status="503") == before + 1


def test_metrics_endpoint_returns_prometheus_text_and_is_not_counted_itself(api):
    client, _ = api
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "signal_http_requests_total" in r.text
    assert 'route="/metrics"' not in r.text
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]  # not in the public API docs


# --- Worker ------------------------------------------------------------------------------------

def kafka_message():
    message = create_autospec(Message, instance=True)
    message.topic.return_value, message.partition.return_value, message.offset.return_value = "feedback.raw", 0, 7
    message.value.return_value = b"{}"
    return message


def test_worker_counts_saved_skipped_and_retried_messages():
    consumer = create_autospec(Consumer, instance=True)
    saved, skipped, retry = (value("signal_worker_messages_total", result=r) for r in ("saved", "skipped", "retry"))

    def unreadable(_):
        raise KeyError("text")

    def database_down(_):
        raise ConnectionError("db down")

    handle_one(consumer, kafka_message(), lambda _: None)
    handle_one(consumer, kafka_message(), unreadable)
    handle_one(consumer, kafka_message(), database_down)
    assert value("signal_worker_messages_total", result="saved") == saved + 1
    assert value("signal_worker_messages_total", result="skipped") == skipped + 1
    assert value("signal_worker_messages_total", result="retry") == retry + 1


def test_lag_is_the_end_of_the_log_minus_where_the_worker_is():
    consumer = create_autospec(Consumer, instance=True)
    consumer.assignment.return_value = [TopicPartition("feedback.raw", 0), TopicPartition("feedback.raw", 1)]
    consumer.committed.return_value = [TopicPartition("feedback.raw", 0, 90), TopicPartition("feedback.raw", 1, 40)]
    # partition 0: read up to 95 in this run; partition 1: nothing read yet (-1001), so use the commit
    consumer.position.return_value = [TopicPartition("feedback.raw", 0, 95), TopicPartition("feedback.raw", 1, -1001)]
    consumer.get_watermark_offsets.side_effect = [(0, 100), (0, 50)]
    update_lag(consumer)
    assert value("signal_worker_lag_messages", partition="0") == 5
    assert value("signal_worker_lag_messages", partition="1") == 10


# --- Scheduler ---------------------------------------------------------------------------------

def test_a_theme_run_records_success_time_and_size(monkeypatch):
    monkeypatch.setattr("signal_app.shared.config.AS_OF", "")
    items = [ProblemItem(tenant="t", area="delivery", topic="delay", market="UK", customer_ref="c1",
                         created_at=NOW - timedelta(days=1))]
    store = InMemoryThemeStore()
    recompute = RecomputeThemes(inputs=InMemoryThemeInputs(items), store=store, clock=FixedClock())
    ok_before = value("signal_scheduler_task_runs_total", task="themes", result="ok")
    run_once(recompute, FixedClock())
    assert value("signal_scheduler_task_runs_total", task="themes", result="ok") == ok_before + 1
    assert value("signal_themes_ranked") == 1
    assert value("signal_scheduler_last_success_timestamp_seconds", task="themes") > 0

    failed_before = value("signal_scheduler_task_runs_total", task="themes", result="failed")
    store.fail = True
    run_once(recompute, FixedClock())
    assert value("signal_scheduler_task_runs_total", task="themes", result="failed") == failed_before + 1


def test_fired_alarms_are_counted_by_kind():
    class TwoAlarms:
        def run_frequent(self, now):
            return [Alert(tenant="t", alarm="incident", subject="t|delivery|delay|UK", fired_at=now, details={}),
                    Alert(tenant="t", alarm="source_flood", subject="t|in_app", fired_at=now, details={})]

    incident = value("signal_alerts_fired_total", alarm="incident")
    check_alarms_now(TwoAlarms(), NOW)
    assert value("signal_alerts_fired_total", alarm="incident") == incident + 1
