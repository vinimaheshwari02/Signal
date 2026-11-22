"""Use cases for alarms: the scheduler's checks, and the API's list for one tenant."""
from datetime import datetime

from .alarms import (INCIDENT_WINDOW, QUIET_PERIOD, SOURCE_WINDOW, Alert, after_quiet_period,
                     check_declines, check_incidents, check_sources)
from .auth import authenticate
from .ports import AlertStore, ApiKeyDirectory, ArrivalCounter, Clock, ThemeInputs
from .themes import input_window


class CheckAlarms:
    def __init__(self, inputs: ThemeInputs, arrivals: ArrivalCounter, store: AlertStore, clock: Clock):
        self.inputs = inputs
        self.arrivals = arrivals
        self.store = store
        self.clock = clock

    def run_frequent(self, now: datetime) -> list[Alert]:
        """Alarms 1 and 2, every minute, for the minutes just before `now`."""
        candidates = check_sources(self.arrivals.counts(now - SOURCE_WINDOW, now), now)
        candidates += check_incidents(self.inputs.problem_items(now - INCIDENT_WINDOW, now), now)
        return self._fire(candidates, now)

    def run_daily(self, as_of: datetime) -> list[Alert]:
        """Alarm 3, once a day, for the week before as_of (the same week the themes use)."""
        _item_start, _item_end, day_start, day_end = input_window(as_of)
        now = self.clock.now()
        candidates = check_declines(self.inputs.business_days(day_start, day_end), as_of, now)
        return self._fire(candidates, now)

    def _fire(self, candidates: list[Alert], now: datetime) -> list[Alert]:
        if not candidates:
            return []
        fired = after_quiet_period(candidates, self.store.last_fired(now - QUIET_PERIOD), now)
        self.store.save(fired)
        return fired


class ListAlerts:
    def __init__(self, store: AlertStore, keys: ApiKeyDirectory):
        self.store = store
        self.keys = keys

    def run(self, api_key: str | None, limit: int) -> list[Alert]:
        tenant, _channel = authenticate(self.keys, api_key)
        return self.store.latest(tenant, limit)
