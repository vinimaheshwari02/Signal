"""Scheduler: the periodic jobs. Run a single instance.

Every minute:     alarms 1 and 2 (source flood, incident) for the minutes just before now.
Every 5 minutes:  recompute every tenant's themes (ADR 0007).
Once a day:       alarm 3 (slow decline), for the same week the themes use.
A failing job is logged and the others keep running.
"""
import logging
import time
from datetime import datetime

from ..adapters import metrics
from ..adapters.clock import SystemClock
from ..adapters.postgres import PostgresAlertStore, PostgresArrivalCounter, PostgresThemeInputs, PostgresThemeStore
from ..core.alarm_jobs import CheckAlarms
from ..core.theme_jobs import RecomputeThemes, as_of_from_setting
from ..shared import config

log = logging.getLogger("signal.scheduler")


def record_job(task: str, started: float, ok: bool) -> None:
    """Count one task run for Prometheus. A stale last-success time means the task keeps failing."""
    metrics.JOB_DURATION.labels(task).observe(time.perf_counter() - started)
    metrics.JOB_RUNS.labels(task, "ok" if ok else "failed").inc()
    if ok:
        metrics.JOB_LAST_SUCCESS.labels(task).set_to_current_time()


def record_alerts(fired) -> None:
    for alert in fired:
        metrics.ALERTS_FIRED.labels(alert.alarm).inc()


def run_once(recompute: RecomputeThemes, clock: SystemClock) -> None:
    """One theme recompute. A failure is logged and the last good ranking stays in place."""
    as_of = as_of_from_setting(config.AS_OF, clock.now())
    started = time.perf_counter()
    try:
        ranked = recompute.run(as_of)
    except Exception:
        log.exception("theme run failed; keeping the last good ranking")
        record_job("themes", started, ok=False)
        return
    record_job("themes", started, ok=True)
    metrics.THEMES_RANKED.set(len(ranked.themes))
    log.info("ranked %d themes as of %s", len(ranked.themes), as_of.isoformat())


def check_alarms_now(alarms: CheckAlarms, now: datetime) -> None:
    started = time.perf_counter()
    try:
        fired = alarms.run_frequent(now)
    except Exception:
        log.exception("alarm check failed")
        record_job("alarms", started, ok=False)
        return
    record_job("alarms", started, ok=True)
    record_alerts(fired)
    for alert in fired:
        log.warning("ALARM %s %s %s", alert.alarm, alert.subject, alert.details)


def check_declines(alarms: CheckAlarms, as_of: datetime) -> None:
    started = time.perf_counter()
    try:
        fired = alarms.run_daily(as_of)
    except Exception:
        log.exception("daily decline check failed")
        record_job("declines", started, ok=False)
        return
    record_job("declines", started, ok=True)
    record_alerts(fired)
    log.info("decline check as of %s: %d alarms", as_of.isoformat(), len(fired))
    for alert in fired:
        log.warning("ALARM %s %s %s", alert.alarm, alert.subject, alert.details)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    metrics.serve_metrics(config.METRICS_PORT)  # Prometheus reads scheduler:9100/metrics
    clock = SystemClock()
    # The owner role: it reads every tenant's data and writes themes and alerts.
    inputs = PostgresThemeInputs(config.WORKER_DATABASE_URL)
    recompute = RecomputeThemes(inputs=inputs, store=PostgresThemeStore(config.WORKER_DATABASE_URL),
                                clock=clock)
    alarms = CheckAlarms(inputs=inputs, arrivals=PostgresArrivalCounter(config.WORKER_DATABASE_URL),
                         store=PostgresAlertStore(config.WORKER_DATABASE_URL), clock=clock)
    log.info("scheduler started: alarms every %ds, themes every %ds",
             config.ALARM_INTERVAL_SECONDS, config.THEME_INTERVAL_SECONDS)

    last_themes = None      # when the themes were last recomputed
    last_decline_day = None  # the as_of date the decline check last ran for
    while True:
        now = clock.now()
        check_alarms_now(alarms, now)  # real time: these alarms are about what happens now
        if last_themes is None or (now - last_themes).total_seconds() >= config.THEME_INTERVAL_SECONDS:
            run_once(recompute, clock)
            last_themes = now
        as_of = as_of_from_setting(config.AS_OF, now)
        if as_of.date() != last_decline_day:
            check_declines(alarms, as_of)
            last_decline_day = as_of.date()
        time.sleep(config.ALARM_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
