"""Scheduler: the periodic jobs. Run a single instance.

Every minute:     alarms 1 and 2 (source flood, incident) for the minutes just before now.
Every 5 minutes:  recompute every tenant's themes (ADR 0007).
Once a day:       alarm 3 (slow decline), for the same week the themes use.
A failing job is logged and the others keep running.
"""
import logging
import time
from datetime import datetime

from ..adapters.clock import SystemClock
from ..adapters.postgres import PostgresAlertStore, PostgresArrivalCounter, PostgresThemeInputs, PostgresThemeStore
from ..core.alarm_jobs import CheckAlarms
from ..core.theme_jobs import RecomputeThemes, as_of_from_setting
from ..shared import config

log = logging.getLogger("signal.scheduler")


def run_once(recompute: RecomputeThemes, clock: SystemClock) -> None:
    """One theme recompute. A failure is logged and the last good ranking stays in place."""
    as_of = as_of_from_setting(config.AS_OF, clock.now())
    try:
        ranked = recompute.run(as_of)
    except Exception:
        log.exception("theme run failed; keeping the last good ranking")
        return
    log.info("ranked %d themes as of %s", len(ranked.themes), as_of.isoformat())


def check_alarms_now(alarms: CheckAlarms, now: datetime) -> None:
    try:
        fired = alarms.run_frequent(now)
    except Exception:
        log.exception("alarm check failed")
        return
    for alert in fired:
        log.warning("ALARM %s %s %s", alert.alarm, alert.subject, alert.details)


def check_declines(alarms: CheckAlarms, as_of: datetime) -> None:
    try:
        fired = alarms.run_daily(as_of)
    except Exception:
        log.exception("daily decline check failed")
        return
    log.info("decline check as of %s: %d alarms", as_of.isoformat(), len(fired))
    for alert in fired:
        log.warning("ALARM %s %s %s", alert.alarm, alert.subject, alert.details)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
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
