import pytest

from signal_app.core.enrich import classify, detect_language, enrich, text_sentiment


@pytest.mark.parametrize("text,lang", [
    ("Where is my order? It is late again.", "en"),
    ("Das Paket ist nicht angekommen", "de"),
    ("Sehr schneller Bestellvorgang, top.", "de"),      # no common words: found through the German word lists
    ("Je ne reçois jamais l'e-mail", "fr"),
    ("Livraison rapide et colis bien emballé.", "fr"),
    ("", "en"),                                          # nothing to go on: English
])
def test_language_detection(text, lang):
    assert detect_language(text) == lang


def test_source_language_wins_over_detection():
    assert enrich("Where is my order?", language="de").language == "de"
    assert enrich("Where is my order?", language="xx").language == "en"  # unknown value is ignored


@pytest.mark.parametrize("text,lang,sentiment", [
    ("Courier was friendly and on time, thanks.", "en", "positive"),
    ("Parcel marked as delivered but nothing arrived.", "en", "negative"),
    ("Do you deliver on Saturdays?", "en", "neutral"),
    ("Retoure ging schnell und einfach.", "de", "positive"),
    ("Ich kann mich nicht einloggen, Konto gesperrt.", "de", "negative"),
    ("Livrez-vous le samedi ?", "fr", "neutral"),
    ("L'étiquette de retour ne s'imprime pas.", "fr", "negative"),
])
def test_text_sentiment(text, lang, sentiment):
    assert text_sentiment(text, lang) == sentiment


@pytest.mark.parametrize("text,area,topic", [
    ("Parcel marked as delivered but nothing arrived.", "delivery", "missing_parcel"),
    ("My rain jacket is 14 days late and tracking hasn't updated.", "delivery", "delay"),
    ("Courier left my parcel in the rain, the box was soaked.", "delivery", "parcel_condition"),
    ("Can I exchange for a different size instead of a refund?", "returns", "exchange"),
    ("Returned my tent 9 days ago and still no refund.", "returns", "refund"),
    ("Refund for my lamp still not back on my card after 12 days.", "payments", "refund_missing"),
    ("I was charged twice for the same order of a rug.", "payments", "double_charge"),
    ("Couldn't apply my discount code at checkout, it just says invalid every time.", "checkout", "discount_code"),
    ("Checkout keeps logging me out before I can pay. Tried three times.", "checkout", "checkout_error"),
    ("Can I have two delivery addresses on my account?", "account", "account_settings"),
    ("Two-factor code arrives after it has already expired.", "account", "two_factor"),
    ("Sorting by price doesn't actually sort by price.", "search", "sorting"),
    ("Mein Rabattcode wird an der Kasse nicht akzeptiert.", "checkout", "discount_code"),
    ("Das Retourenetikett lässt sich nicht drucken.", "returns", "return_label"),
    ("Mon code promo est refusé à chaque fois.", "checkout", "discount_code"),
])
def test_area_and_topic(text, area, topic):
    lang = detect_language(text)
    assert classify(text, lang) == (area, topic)


def test_text_in_another_language_still_finds_its_topic():
    # French text told to be German: nothing matches German words, so every language is tried.
    assert classify("Le paiement échoue sans message d'erreur", "de") == ("payments", "payment_failed")


def test_unrecognised_text_goes_to_general_other():
    assert classify("hello there", "en") == ("general", "other")
    assert classify("", "en") == ("general", "other")


def test_weak_area_words_give_the_areas_other_topic():
    assert classify("something about my parcel", "en") == ("delivery", "other")


@pytest.mark.parametrize("text,kind", [
    ("Parcel marked as delivered but nothing arrived.", "problem"),
    ("Do you deliver on Saturdays?", "question"),
    ("Could you add a filter for brand?", "suggestion"),
    ("Courier was friendly and on time, thanks.", "praise"),
    ("Why do I have to pay for returns now? That's new.", "problem"),   # a question that is a complaint
    ("Checkout asks for my phone number, why is that needed?", "question"),
])
def test_kind(text, kind):
    assert enrich(text).kind == kind


def test_rating_only_settles_neutral_words():
    assert enrich("Third time asking where my order is", sentiment_hint="negative").sentiment == "negative"  # cut off
    assert enrich("Do you deliver on Saturdays?", sentiment_hint="positive").sentiment == "positive"
    # clear words beat a contradicting rating (ratings written as words contradict the text in the data)
    assert enrich("Mir wurde die Bestellung doppelt berechnet.", sentiment_hint="positive").sentiment == "negative"
    assert enrich("Great, so easy!", sentiment_hint="negative").sentiment == "positive"


def test_same_text_always_gets_the_same_labels():
    assert enrich("Where is my parcel?") == enrich("Where is my parcel?")
