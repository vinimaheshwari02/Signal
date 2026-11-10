"""Turn a source's own payload shape into Signal's common shape.

One function per channel, registered in NORMALISERS. A normaliser never crashes on odd input:
it either returns the common shape (fixing what it can) or raises Rejected with a reason, which
the API shows as a 422. Items with no usable text are rejected (and so counted by the 422s).

Common shape (a dict):
    source_id       the source's own id, or None
    text            cleaned text with emails, phone numbers and order numbers masked
    created_at      when the customer wrote it (ISO, UTC); falls back to received_at
    customer_ref    salted hash of the customer/author reference, or None
    market          UK / IE / DE / AT / FR, or None
    language        'en' / 'de' / 'fr' if the source says so, else None (enrichment detects it)
    sentiment_hint  'negative' / 'neutral' / 'positive' from a rating, score or mood, or None
"""
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from zoneinfo import ZoneInfo

from .errors import Rejected
from .ids import hash_customer

MARKETS = {"UK", "IE", "DE", "AT", "FR"}
LOCALE_TO_MARKET = {"en-GB": "UK", "en-IE": "IE", "de-DE": "DE", "de-AT": "AT", "fr-FR": "FR"}
TERRITORY_TO_MARKET = {"GB": "UK", "UK": "UK", "IE": "IE", "DE": "DE", "AT": "AT", "FR": "FR"}
MARKET_TZ = {"UK": "Europe/London", "IE": "Europe/Dublin", "DE": "Europe/Berlin",
             "AT": "Europe/Vienna", "FR": "Europe/Paris"}
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}

MIN_TS = datetime(2000, 1, 1, tzinfo=timezone.utc)
MAX_FUTURE = timedelta(days=1)  # clocks differ a little; anything further ahead is nonsense
LOCAL_TIME = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})[ T](\d{1,2}):(\d{2})\s*$")  # dd/mm/yyyy hh:mm


# ---------- small helpers ----------

def _parse_time(value, received_at: datetime, market: str | None = None) -> datetime | None:
    """Epoch milliseconds, ISO text, dd/mm/yyyy hh:mm (local time of the market) or an email-style
    date -> aware UTC datetime. None if unusable or implausible."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        elif isinstance(value, str):
            m = LOCAL_TIME.match(value)
            if m:
                d, mo, y, h, mi = map(int, m.groups())
                tz = ZoneInfo(MARKET_TZ.get(market, "UTC"))
                dt = datetime(y, mo, d, h, mi, tzinfo=tz).astimezone(timezone.utc)
            elif re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
                dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = parsedate_to_datetime(value.strip())  # e.g. "Tue, 21 Jul 2026 01:52:52 +0000"
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
        else:
            return None
        dt = dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError, IndexError):
        return None
    return dt if MIN_TS <= dt <= received_at + MAX_FUTURE else None


def _number(value) -> float | None:
    """A number, a numeric string, or a number word ('five') -> number. None otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in NUMBER_WORDS:
            return float(NUMBER_WORDS[v])
        try:
            return float(v)
        except ValueError:
            return None
    return None


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
ORDER_NO = re.compile(r"(?i)\b(order|bestellung|bestellnummer|commande)(\s*(?:no\.?|nr\.?|number|#|:))?\s*[A-Z]{0,3}-?\d{5,}")


def _mask_phone(m: re.Match) -> str:
    return "[phone]" if sum(c.isdigit() for c in m.group()) >= 9 else m.group()


def mask_pii(text: str) -> str:
    """Hide emails, phone numbers and order numbers before the text goes anywhere else."""
    text = EMAIL.sub("[email]", text)
    text = ORDER_NO.sub(lambda m: m.group(1) + " [order]", text)
    return PHONE.sub(_mask_phone, text)


def _text(*candidates) -> str:
    """First candidate that is real text, cleaned: control characters and runs of spaces become
    one space, PII masked. Raises Rejected if none is usable."""
    for c in candidates:
        if isinstance(c, str):
            cleaned = re.sub(r"[\x00-\x1f\x7f\s]+", " ", c).strip()
            if cleaned:
                return mask_pii(cleaned)
    raise Rejected("no text to analyse")


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _str_or_none(value) -> str | None:
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value) else None


def _hash_ref(tenant: str, ref, salt: str) -> str | None:
    s = _str_or_none(ref)
    return hash_customer(tenant, s, salt) if s else None


def _hint_from_scale(value, low: float, high: float) -> str | None:
    """value <= low -> negative, >= high -> positive, in between neutral."""
    n = _number(value)
    if n is None:
        return None
    return "negative" if n <= low else "positive" if n >= high else "neutral"


def _require_object(payload, what: str) -> dict:
    if not isinstance(payload, dict):
        raise Rejected(f"expected a JSON object for {what}")
    return payload


def _result(source_id, text, created_at, customer_ref, market, language, hint) -> dict:
    return {"source_id": source_id, "text": text, "created_at": created_at.isoformat(),
            "customer_ref": customer_ref, "market": market, "language": language,
            "sentiment_hint": hint}


# ---------- one normaliser per channel ----------

def support_ticket(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    ticket = payload.get("ticket") if isinstance(payload, dict) else None
    if not isinstance(ticket, dict):
        raise Rejected("expected an object with a 'ticket' field")
    text = _text(ticket.get("description"), ticket.get("subject"))
    requester = _dict(ticket.get("requester"))
    locale = requester.get("locale") if isinstance(requester.get("locale"), str) else None
    market = LOCALE_TO_MARKET.get(locale) if locale else None
    # A missing or implausible date ("yesterday", far future) falls back to when we received it.
    created = _parse_time(ticket.get("created"), received_at, market) or received_at
    return _result(_str_or_none(ticket.get("id")), text, created,
                   _hash_ref(tenant, requester.get("customer_ref"), salt), market,
                   locale.split("-")[0] if locale else None, None)


def app_store(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    p = _require_object(payload, "an app store review")
    # The title is the start of the body, so it is only a fallback when the body is missing.
    text = _text(p.get("body"), p.get("title"))
    territory = p.get("territory")
    market = TERRITORY_TO_MARKET.get(territory.upper()) if isinstance(territory, str) else None
    created = _parse_time(p.get("reviewed_at"), received_at, market) or received_at
    # Rating 1-5, sometimes the word "five": 1-2 negative, 3 neutral, 4-5 positive.
    return _result(_str_or_none(p.get("review_id")), text, created,
                   _hash_ref(tenant, p.get("author"), salt), market, None,
                   _hint_from_scale(p.get("rating"), 2, 4))


def nps_survey(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    p = _require_object(payload, "an NPS response")
    text = _text(p.get("comment"))
    market = p.get("market") if p.get("market") in MARKETS else None
    # "dd/mm/yyyy hh:mm" in the market's local time.
    created = _parse_time(p.get("submitted"), received_at, market) or received_at
    # Score 0-10 (sometimes "ten"): 0-6 detractor, 7-8 passive, 9-10 promoter.
    return _result(_str_or_none(p.get("response_id")), text, created,
                   _hash_ref(tenant, p.get("customer_id"), salt), market, None,
                   _hint_from_scale(p.get("score"), 6, 9))


MOODS = {"angry": "negative", "frustrated": "negative", "neutral": "neutral", "happy": "positive"}


def in_app(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    p = _require_object(payload, "an in-app message")
    inner = p.get("payload")
    if not isinstance(inner, dict):  # sometimes a plain string such as "oops"
        raise Rejected("expected an object in 'payload'")
    text = _text(inner.get("message"))
    user = _dict(p.get("user"))
    locale = user.get("locale") if isinstance(user.get("locale"), str) else None
    market = LOCALE_TO_MARKET.get(locale) if locale else None
    created = _parse_time(p.get("ts"), received_at, market) or received_at
    mood = inner.get("mood")
    # There is no id in this source: the idempotency key falls back to the header or payload hash.
    return _result(None, text, created, _hash_ref(tenant, user.get("id"), salt), market,
                   locale.split("-")[0] if locale else None,
                   MOODS.get(mood.lower()) if isinstance(mood, str) else None)


def social(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    p = _require_object(payload, "a social post")
    text = _text(p.get("text"))
    lang = p.get("lang").lower() if isinstance(p.get("lang"), str) else None
    created = _parse_time(p.get("created_at"), received_at) or received_at  # no market: UTC
    return _result(_str_or_none(p.get("post_id")), text, created,
                   _hash_ref(tenant, p.get("author_handle"), salt), None,
                   lang if lang in {"en", "de", "fr"} else None, None)


NORMALISERS: dict[str, Callable] = {
    "support_ticket": support_ticket,
    "app_store": app_store,
    "nps_survey": nps_survey,
    "in_app": in_app,
    "social": social,
}
