"""Rule-based enrichment: language, sentiment, kind, area and topic for one piece of text.

No machine learning and no outside calls (ADR 0006): the same text always gets the same labels,
and every label can be explained by the words that triggered it. The words live in taxonomy.py.

Read it from the bottom: enrich() calls the functions above it in this order:
detect_language -> text_sentiment -> classify -> find_kind.
"""
import re
from dataclasses import dataclass

from .taxonomy import NEGATIVE, POSITIVE, QUESTION_START, STOPWORDS, SUGGESTION, TAXONOMY

LANGUAGES = ("en", "de", "fr")


@dataclass(frozen=True)
class Enrichment:
    language: str
    sentiment: str  # negative / neutral / positive
    kind: str       # problem / praise / question / suggestion / other
    area: str
    topic: str


# ---------- preparing the word lists (runs once, when the program starts) ----------

def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """["never arrived", ...] -> [compiled pattern, ...] so matching is fast."""
    compiled = []
    for pattern in patterns:
        compiled.append(re.compile(pattern))
    return compiled


def compile_per_language(per_language: dict[str, list]) -> dict[str, list]:
    """{"en": [...], "de": [...]} -> the same, with every list compiled."""
    result = {}
    for language, patterns in per_language.items():
        result[language] = compile_patterns(patterns)
    return result


def build_topics() -> list[tuple[str, str, dict]]:
    """The nested TAXONOMY as a flat list: [(area, topic, {language: compiled patterns}), ...].
    The order is the order in taxonomy.py; it decides ties."""
    topics = []
    for area, topics_of_area in TAXONOMY.items():
        for topic, per_language in topics_of_area.items():
            topics.append((area, topic, compile_per_language(per_language)))
    return topics


TOPICS = build_topics()
POSITIVE_PATTERNS = compile_per_language(POSITIVE)
NEGATIVE_PATTERNS = compile_per_language(NEGATIVE)
SUGGESTION_PATTERNS = compile_patterns(SUGGESTION)
QUESTION_PATTERNS = compile_patterns(QUESTION_START)


# ---------- two small helpers used everywhere ----------

def clean(text: str) -> str:
    """Lower case, straight apostrophes, single spaces: the form the patterns are written for."""
    text = text.replace("’", "'").replace("`", "'").lower()
    return re.sub(r"\s+", " ", text).strip()


def count_matches(patterns: list[re.Pattern], text: str) -> int:
    """How many of the patterns are found in the text. Each pattern counts once."""
    count = 0
    for pattern in patterns:
        if pattern.search(text):
            count += 1
    return count


# ---------- step 1: language ----------

def count_common_words(text: str, language: str) -> int:
    """How many words of the text are everyday words of this language ("the", "der", "le")."""
    common = set(STOPWORDS[language])
    count = 0
    for word in re.findall(r"[\w'-]+", text):
        if word in common:
            count += 1
    return count


def count_own_patterns(text: str, language: str) -> int:
    """Short texts may have no everyday words at all, so the language's own sentiment and topic
    words count too."""
    count = count_matches(POSITIVE_PATTERNS[language], text) + count_matches(NEGATIVE_PATTERNS[language], text)
    for _, _, per_language in TOPICS:
        count += count_matches(per_language.get(language, []), text)
    return count


def detect_language(text: str) -> str:
    """The language with the most signs in the text. English if nothing decides or on a tie."""
    t = clean(text)
    points = {}
    for language in LANGUAGES:
        points[language] = count_common_words(t, language) + count_own_patterns(t, language)
    best = "en"
    for language in ("de", "fr"):
        if points[language] > points[best]:  # must be strictly more: a tie keeps the earlier one
            best = language
    return best


# ---------- step 2: sentiment ----------

def text_sentiment(text: str, language: str) -> str:
    """negative / neutral / positive from the words alone. Negative wins a tie."""
    t = clean(text)
    positive = count_matches(POSITIVE_PATTERNS[language], t)
    negative = count_matches(NEGATIVE_PATTERNS[language], t)
    if negative > 0 and negative >= positive:
        return "negative"
    if positive > 0:
        return "positive"
    return "neutral"


# ---------- step 3: area and topic ----------

def best_topic(text: str, languages) -> tuple[int, str, str]:
    """(matches, area, topic) of the topic with the most matching patterns, looking only at the
    given languages. The first listed topic wins a tie. No match at all: (0, "general", "other")."""
    best = (0, "general", "other")
    for area, topic, per_language in TOPICS:
        matches = 0
        for language in languages:
            matches += count_matches(per_language.get(language, []), text)
        if matches > best[0]:
            best = (matches, area, topic)
    return best


def classify(text: str, language: str) -> tuple[str, str]:
    """(area, topic). First try the text's own language; if nothing matches, try every language;
    if still nothing, ("general", "other")."""
    t = clean(text)
    matches, area, topic = best_topic(t, [language])
    if matches == 0:
        matches, area, topic = best_topic(t, LANGUAGES)
    return (area, topic)


# ---------- step 4: kind ----------

def find_kind(text: str, sentiment: str) -> str:
    """The first rule that fits wins: problem, suggestion, question, praise, other."""
    t = clean(text)
    if sentiment == "negative":
        return "problem"
    if count_matches(SUGGESTION_PATTERNS, t) > 0:
        return "suggestion"
    if "?" in t or count_matches(QUESTION_PATTERNS, t) > 0:
        return "question"
    if sentiment == "positive":
        return "praise"
    return "other"


# ---------- the entry point ----------

def enrich(text: str, language: str | None = None, sentiment_hint: str | None = None) -> Enrichment:
    """Label one text. `language` and `sentiment_hint` come from the source when it knows them
    (a locale, a star rating, an NPS score, a mood)."""
    # 1. Language: trust the source if it names one we support, otherwise work it out.
    if language not in LANGUAGES:
        language = detect_language(text)

    # 2. Sentiment: clear words decide. A rating, score or mood only settles texts whose words are
    #    neutral: in the data, ratings written as words ("ten", "five") often contradict the text.
    sentiment = text_sentiment(text, language)
    if sentiment == "neutral" and sentiment_hint:
        sentiment = sentiment_hint

    # 3. Area and topic.
    area, topic = classify(text, language)

    # 4. Kind, which depends on the sentiment.
    kind = find_kind(text, sentiment)

    return Enrichment(language, sentiment, kind, area, topic)
