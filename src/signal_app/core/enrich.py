"""Rule-based enrichment: language, sentiment, kind, area and topic for one piece of text.

No machine learning and no outside calls (ADR 0006): the same text always gets the same labels,
and every label can be explained by the words that triggered it. The words live in taxonomy.py.
"""
import re
from dataclasses import dataclass

from .taxonomy import NEGATIVE, POSITIVE, QUESTION_START, STOPWORDS, SUGGESTION, TAXONOMY

LANGUAGES = ("en", "de", "fr")
OTHER_CAP = 0.9  # the weak words of an "other" topic never beat one real trigger


@dataclass(frozen=True)
class Enrichment:
    language: str
    sentiment: str  # negative / neutral / positive
    kind: str       # problem / praise / question / suggestion / other
    area: str
    topic: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("`", "'").lower()).strip()


def _compile(patterns) -> list[tuple[re.Pattern, float]]:
    return [(re.compile(p if isinstance(p, str) else p[0]), 1.0 if isinstance(p, str) else p[1]) for p in patterns]


_TOPICS = [(area, topic, {lang: _compile(ps) for lang, ps in langs.items()})
           for area, topics in TAXONOMY.items() for topic, langs in topics.items()]
_POS = {lang: _compile(ps) for lang, ps in POSITIVE.items()}
_NEG = {lang: _compile(ps) for lang, ps in NEGATIVE.items()}
_SUGGEST = _compile(SUGGESTION)
_QUESTION = _compile(QUESTION_START)


def detect_language(text: str) -> str:
    """The language whose common words appear most; English if nothing decides."""
    t = _norm(text)
    words = re.findall(r"[\w'-]+", t)
    scores = {lang: sum(1 for w in words if w in set(sw)) for lang, sw in STOPWORDS.items()}
    scores["de"] += 2 * len(re.findall(r"[äöüß]", t))
    scores["fr"] += len(re.findall(r"[éèêàçùœâîô]", t))
    # Short texts may have no common words at all: the language's own sentiment and topic words count too.
    for lang in LANGUAGES:
        scores[lang] += (sum(1 for p, _ in _POS[lang] if p.search(t)) + sum(1 for p, _ in _NEG[lang] if p.search(t))
                         + sum(1 for _, _, per in _TOPICS for p, _ in per.get(lang, []) if p.search(t)))
    best = max(LANGUAGES, key=lambda lang: (scores[lang], lang == "en"))
    return best if scores[best] > 0 else "en"


def _hits(patterns: list[tuple[re.Pattern, float]], text: str) -> float:
    return sum(w for p, w in patterns if p.search(text))


def text_sentiment(text: str, language: str) -> str:
    """negative / neutral / positive from the words alone."""
    t = _norm(text)
    pos = _hits(_POS[language], t)
    neg = _hits(_NEG[language], t)
    if neg > 0 and neg >= pos:
        return "negative"
    return "positive" if pos > 0 else "neutral"


def classify(text: str, language: str) -> tuple[str, str]:
    """(area, topic). The topic with the highest trigger total wins; the first listed wins a tie.
    Nothing matching in the text's language means we try every language; still nothing means
    ("general", "other")."""
    t = _norm(text)

    def best(langs) -> tuple[float, str, str]:
        top = (0.0, "general", "other")
        for area, topic, per_lang in _TOPICS:
            score = sum(_hits(per_lang.get(lang, []), t) for lang in langs)
            if topic == "other":
                score = min(score, OTHER_CAP)
            if score > top[0]:
                top = (score, area, topic)
        return top

    score, area, topic = best([language])
    if score < 0.5:
        score, area, topic = best(LANGUAGES)
    return (area, topic) if score >= 0.5 else ("general", "other")


def _kind(text: str, sentiment: str) -> str:
    t = _norm(text)
    if sentiment == "negative":
        return "problem"
    if _hits(_SUGGEST, t):
        return "suggestion"
    if "?" in t or _hits(_QUESTION, t):
        return "question"
    return "praise" if sentiment == "positive" else "other"


def enrich(text: str, language: str | None = None, sentiment_hint: str | None = None) -> Enrichment:
    """Label one text. `language` and `sentiment_hint` come from the source when it knows them
    (a locale, a star rating, an NPS score, a mood). The rating only counts when the words are neutral."""
    lang = language if language in LANGUAGES else detect_language(text)
    from_text = text_sentiment(text, lang)
    # Clear words decide. A rating, score or mood only settles texts whose words are neutral (a short or
    # cut-off text): in the data, ratings written as words ("ten", "five") often contradict the text.
    sentiment = from_text if from_text != "neutral" else (sentiment_hint or "neutral")
    area, topic = classify(text, lang)
    return Enrichment(lang, sentiment, _kind(text, sentiment), area, topic)
