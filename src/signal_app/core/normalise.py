"""Turn a source's own payload shape into Signal's common shape.

One function per channel, registered in NORMALISERS. A normaliser never crashes on odd input:
it either returns the common shape (fixing what it can) or raises Rejected with a reason, which
the API shows as a 422. Items with no usable text are rejected (and so counted by the 422s).

Common shape (a dict):
    source_id       the source's own id, or None
    text            cleaned text with emails, phone numbers and order numbers masked
    created_at      when the customer wrote it (ISO, UTC); falls back to received_at
    created_at_estimated  True when created_at is that fallback, not the source's own time
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


# ---------- reading a time ----------
# Sources write times in four ways. Each small function below reads one of them.

def _from_epoch_ms(value: int | float) -> datetime:
    """1784609488000 -> milliseconds since 1970 (support tickets)."""
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _from_local_time(match: re.Match, market: str | None) -> datetime:
    """"21/07/2026 02:52" -> day/month/year in the local time of the market (NPS surveys).
    No known market means we read it as UTC."""
    day, month, year, hour, minute = map(int, match.groups())
    local_zone = ZoneInfo(MARKET_TZ.get(market, "UTC"))
    return datetime(year, month, day, hour, minute, tzinfo=local_zone)


def _from_iso(text: str) -> datetime:
    """"2026-07-21T05:53:50Z" or "2026-07-21T03:11:49.000+02:00" (app store, in-app)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _from_email_date(text: str) -> datetime:
    """"Tue, 21 Jul 2026 01:52:52 +0000" (social)."""
    return parsedate_to_datetime(text)


def _read_time(value, market: str | None) -> datetime | None:
    """Pick the reader that fits the value. None for something that is not a time at all."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch_ms(value)
    if not isinstance(value, str):
        return None
    local = LOCAL_TIME.match(value)
    if local:
        return _from_local_time(local, market)
    text = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return _from_iso(text)
    return _from_email_date(text)


def _parse_time(value, received_at: datetime, market: str | None = None) -> datetime | None:
    """Any of the four forms -> a UTC time. None if it cannot be read ("yesterday",
    "31/02/2026 25:61") or is implausible (before 2000, or more than a day in the future)."""
    try:
        moment = _read_time(value, market)
        if moment is None:
            return None
        if moment.tzinfo is None:  # no time zone written: take it as UTC
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError, IndexError):
        return None
    if moment < MIN_TS or moment > received_at + MAX_FUTURE:
        return None
    return moment


# ---------- reading numbers, ids and text ----------

def _number(value) -> float | None:
    """A number, a numeric string, or a number word ("five") -> number. None otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    word = value.strip().lower()
    if word in NUMBER_WORDS:
        return float(NUMBER_WORDS[word])
    try:
        return float(word)
    except ValueError:
        return None


def _hint_from_scale(value, low: float, high: float) -> str | None:
    """A rating or score as a feeling: up to `low` is negative, from `high` is positive,
    in between is neutral. None if the value is not a number."""
    number = _number(value)
    if number is None:
        return None
    if number <= low:
        return "negative"
    if number >= high:
        return "positive"
    return "neutral"


def _str_or_none(value) -> str | None:
    """An id as text. None for a missing or empty id, or something that is not an id."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    if text == "":
        return None
    return text


def _hash_ref(tenant: str, ref, salt: str) -> str | None:
    """The customer reference as a salted hash, so the real one is never stored."""
    text = _str_or_none(ref)
    if text is None:
        return None
    return hash_customer(tenant, text, salt)


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
ORDER_NO = re.compile(r"(?i)\b(order|bestellung|bestellnummer|commande)(\s*(?:no\.?|nr\.?|number|#|:))?\s*[A-Z]{0,3}-?\d{5,}")


def _mask_phone(match: re.Match) -> str:
    """Only something with 9 or more digits is a phone number; shorter runs are left alone."""
    found = match.group()
    digits = 0
    for character in found:
        if character.isdigit():
            digits += 1
    if digits >= 9:
        return "[phone]"
    return found


def _mask_order(match: re.Match) -> str:
    """Keep the word ("order") and hide the number."""
    return match.group(1) + " [order]"


def mask_pii(text: str) -> str:
    """Hide emails, phone numbers and order numbers before the text goes anywhere else."""
    text = EMAIL.sub("[email]", text)
    text = ORDER_NO.sub(_mask_order, text)
    text = PHONE.sub(_mask_phone, text)
    return text


def _text(*candidates) -> str:
    """The first candidate that is real text, cleaned: control characters and runs of spaces
    become one space, and personal data is masked. Raises Rejected if none is usable."""
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        cleaned = re.sub(r"[\x00-\x1f\x7f\s]+", " ", candidate).strip()
        if cleaned:
            return mask_pii(cleaned)
    raise Rejected("no text to analyse")


# ---------- reading the payload's shape ----------

def _dict(value) -> dict:
    """The value if it is a JSON object, otherwise an empty one, so .get() is always safe."""
    if isinstance(value, dict):
        return value
    return {}


def _require_object(payload, what: str) -> dict:
    if not isinstance(payload, dict):
        raise Rejected(f"expected a JSON object for {what}")
    return payload


def _market_and_language(locale) -> tuple[str | None, str | None]:
    """"en-GB" -> ("UK", "en"). (None, None) without a locale; an unknown locale has no market."""
    if not isinstance(locale, str) or locale == "":
        return None, None
    market = LOCALE_TO_MARKET.get(locale)
    language = locale.split("-")[0]
    return market, language


def _created(value, received_at: datetime, market: str | None = None) -> tuple[datetime, bool]:
    """(when the customer wrote it, whether that time is estimated). A missing or unusable time
    ("yesterday", far future) falls back to when we received it, and is marked as estimated, so
    the incident alarm can leave it out (ADR 0008)."""
    moment = _parse_time(value, received_at, market)
    if moment is None:
        return received_at, True
    return moment, False


def _result(*, source_id, text, created_at, created_at_estimated, customer_ref, market, language,
            sentiment_hint) -> dict:
    """The common shape every normaliser returns (see the top of this file)."""
    return {"source_id": source_id, "text": text, "created_at": created_at.isoformat(),
            "created_at_estimated": created_at_estimated, "customer_ref": customer_ref, "market": market, "language": language,
            "sentiment_hint": sentiment_hint}


# ---------- one normaliser per channel ----------
# Each one does the same four things: check the shape, find the text, work out market / time /
# customer, and return the common shape.

def support_ticket(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    ticket = payload.get("ticket") if isinstance(payload, dict) else None
    if not isinstance(ticket, dict):
        raise Rejected("expected an object with a 'ticket' field")
    text = _text(ticket.get("description"), ticket.get("subject"))
    requester = _dict(ticket.get("requester"))
    market, language = _market_and_language(requester.get("locale"))
    created, estimated = _created(ticket.get("created"), received_at, market)
    return _result(source_id=_str_or_none(ticket.get("id")), text=text, created_at=created, created_at_estimated=estimated,
                   customer_ref=_hash_ref(tenant, requester.get("customer_ref"), salt),
                   market=market, language=language,
                   sentiment_hint=None)  # a ticket has no rating


def app_store(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    review = _require_object(payload, "an app store review")
    # The title is the start of the body, so it is only a fallback when the body is missing.
    text = _text(review.get("body"), review.get("title"))
    territory = review.get("territory")
    market = None
    if isinstance(territory, str):
        market = TERRITORY_TO_MARKET.get(territory.upper())
    created, estimated = _created(review.get("reviewed_at"), received_at, market)
    return _result(source_id=_str_or_none(review.get("review_id")), text=text, created_at=created, created_at_estimated=estimated,
                   customer_ref=_hash_ref(tenant, review.get("author"), salt),
                   market=market, language=None,  # not given: enrichment detects it
                   # Rating 1-5, sometimes the word "five": 1-2 negative, 3 neutral, 4-5 positive.
                   sentiment_hint=_hint_from_scale(review.get("rating"), 2, 4))


def nps_survey(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    response = _require_object(payload, "an NPS response")
    text = _text(response.get("comment"))
    market = response.get("market")
    if not isinstance(market, str) or market not in MARKETS:
        market = None
    # "dd/mm/yyyy hh:mm" in the market's local time.
    created, estimated = _created(response.get("submitted"), received_at, market)
    return _result(source_id=_str_or_none(response.get("response_id")), text=text, created_at=created, created_at_estimated=estimated,
                   customer_ref=_hash_ref(tenant, response.get("customer_id"), salt),
                   market=market, language=None,
                   # Score 0-10 (sometimes "ten"): 0-6 detractor, 7-8 passive, 9-10 promoter.
                   sentiment_hint=_hint_from_scale(response.get("score"), 6, 9))


MOODS = {"angry": "negative", "frustrated": "negative", "neutral": "neutral", "happy": "positive"}


def in_app(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    event = _require_object(payload, "an in-app message")
    inner = event.get("payload")
    if not isinstance(inner, dict):  # sometimes a plain string such as "oops"
        raise Rejected("expected an object in 'payload'")
    text = _text(inner.get("message"))
    user = _dict(event.get("user"))
    market, language = _market_and_language(user.get("locale"))
    created, estimated = _created(event.get("ts"), received_at, market)
    mood = inner.get("mood")
    hint = None
    if isinstance(mood, str):
        hint = MOODS.get(mood.lower())
    # There is no id in this source: the idempotency key falls back to the header or payload hash.
    return _result(source_id=None, text=text, created_at=created, created_at_estimated=estimated,
                   customer_ref=_hash_ref(tenant, user.get("id"), salt),
                   market=market, language=language, sentiment_hint=hint)


def social(tenant: str, payload: dict, received_at: datetime, salt: str) -> dict:
    post = _require_object(payload, "a social post")
    text = _text(post.get("text"))
    language = None
    if isinstance(post.get("lang"), str) and post["lang"].lower() in {"en", "de", "fr"}:
        language = post["lang"].lower()
    created, estimated = _created(post.get("created_at"), received_at)  # no market: UTC
    return _result(source_id=_str_or_none(post.get("post_id")), text=text, created_at=created, created_at_estimated=estimated,
                   customer_ref=_hash_ref(tenant, post.get("author_handle"), salt),
                   market=None,  # a post does not say which market it is from
                   language=language, sentiment_hint=None)


NORMALISERS: dict[str, Callable] = {
    "support_ticket": support_ticket,
    "app_store": app_store,
    "nps_survey": nps_survey,
    "in_app": in_app,
    "social": social,
}
