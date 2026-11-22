"""Use cases for themes: the scheduler's recompute, and the API's ranking for one tenant."""
from datetime import datetime, timezone

from .auth import authenticate
from .ports import ApiKeyDirectory, Clock, ThemeInputs, ThemeStore
from .themes import RankedThemes, Theme, input_window, rank_themes


def as_of_from_setting(setting: str, now: datetime) -> datetime:
    """The AS_OF setting: empty means now; "2026-10-19" means the start of that day (UTC)."""
    if setting.strip() == "":
        return now
    moment = datetime.fromisoformat(setting.strip())
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


class RecomputeThemes:
    """Rank every tenant's themes and replace the stored ranking (run by the scheduler)."""

    def __init__(self, inputs: ThemeInputs, store: ThemeStore, clock: Clock):
        self.inputs = inputs
        self.store = store
        self.clock = clock

    def run(self, as_of: datetime) -> RankedThemes:
        item_start, item_end, day_start, day_end = input_window(as_of)
        items = self.inputs.problem_items(item_start, item_end)
        business_days = self.inputs.business_days(day_start, day_end)
        ranked = rank_themes(items, business_days, as_of, computed_at=self.clock.now())
        self.store.replace_all(ranked)
        return ranked


def keep_matching_themes(themes: list[Theme], area: str | None, market: str | None) -> list[Theme]:
    """Only the themes of `area` (if given) that have customers in `market` (if given).

    A theme kept for a market keeps all its numbers: the score, customers and evidence still
    cover every market. The filter chooses themes, it does not recompute them for one market."""
    kept = []
    for theme in themes:
        if area is not None and theme.area != area:
            continue
        if market is not None and market not in theme.customers_by_market:
            continue
        kept.append(theme)
    return kept


class ListThemes:
    """One tenant's ranking for GET /v1/themes: the stored one, or computed on the spot for
    another date (?as_of=...), for example to look back at an incident.

    Optional filters: `area` keeps only themes of that area, `market` keeps only themes that have
    customers in that market. They are applied before `limit`. The numbers of a kept theme are
    not recomputed for one market (see keep_matching_themes)."""

    def __init__(self, store: ThemeStore, inputs: ThemeInputs, keys: ApiKeyDirectory, clock: Clock):
        self.store = store
        self.inputs = inputs
        self.keys = keys
        self.clock = clock

    def run(self, api_key: str | None, limit: int, as_of: datetime | None = None,
            area: str | None = None, market: str | None = None) -> RankedThemes | None:
        tenant, _channel = authenticate(self.keys, api_key)
        if as_of is None:
            # The database filters, so that `limit` counts only matching themes.
            return self.store.latest(tenant, limit, area=area, market=market)

        item_start, item_end, day_start, day_end = input_window(as_of)
        items = self.inputs.problem_items(item_start, item_end, tenant=tenant)
        business_days = self.inputs.business_days(day_start, day_end, tenant=tenant)
        ranked = rank_themes(items, business_days, as_of, computed_at=self.clock.now())
        matching = keep_matching_themes(ranked.themes, area=area, market=market)
        return RankedThemes(as_of=ranked.as_of, computed_at=ranked.computed_at,
                            themes=matching[:limit])
