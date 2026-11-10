"""The taxonomy: areas, topics and the trigger words that recognise them, per language.

This is configuration, not logic. To add a topic or a language, edit this file only.
All tenants share it for now (see ADR 0006). Patterns are regular expressions matched against
lower-case text. A plain string counts 1; W("...", 3) counts 3 (use it for phrases that settle the
topic on their own). The topic with the highest total wins; ties go to the topic listed first.

Each area ends with an "other" topic whose weak words (weight 0.5) only say "this is about the
area" when no specific topic matched.
"""


def W(pattern: str, weight: float) -> tuple[str, float]:
    return (pattern, weight)


# area -> topic -> language -> patterns
TAXONOMY: dict[str, dict[str, dict[str, list]]] = {
    "delivery": {
        "missing_parcel": {
            "en": [W(r"marked as delivered", 3), W(r"nothing arrived", 3), r"never arrived", r"not received"],
            "de": [W(r"zugestellt markiert", 3), r"nie angekommen"],
            "fr": [W(r"indiqué comme livré", 3), r"jamais reçu"],
        },
        "delivery_slot": {
            "en": [W(r"delivery slot", 3), r"time slot", r"slot was missed"],
            "de": [W(r"zeitfenster", 3), r"liefertermin"],
            "fr": [W(r"créneau", 3)],
        },
        "parcel_condition": {
            "en": [W(r"left my parcel", 2), W(r"in the rain", 2), W(r"soaked", 2), r"damaged", r"crushed", r"box was"],
            "de": [W(r"beschädigt", 3), r"nass"],
            "fr": [W(r"abîmé", 3), W(r"endommagé", 3)],
        },
        "delay": {
            "en": [W(r"days? late", 3), W(r"where is my", 2), W(r"no delivery date", 3), W(r"still no delivery", 2),
                   W(r"still not here", 3), W(r"late parcel", 3), r"\blate\b", r"overdue", r"in transit",
                   r"tracking"],
            "de": [W(r"überfällig", 3), W(r"verspät", 3), W(r"wann kommt", 2), W(r"verteilzentrum", 3),
                   W(r"in zustellung", 3), r"sendungsverfolgung", r"tage? verspätung"],
            "fr": [W(r"de retard", 3), W(r"suivi", 2), r"retard"],
        },
        "delivery_options": {
            "en": [W(r"deliver on saturday", 3), W(r"change the delivery address", 3), W(r"delivery address after", 2),
                   W(r"do you deliver", 2)],
            "de": [W(r"liefern sie", 3), W(r"samstags", 2)],
            "fr": [W(r"livrez-vous", 3), W(r"le samedi", 2)],
        },
        "courier_service": {
            "en": [W(r"friendly", 2), r"courier", r"driver"],
            "de": [r"kurier", r"fahrer", r"zusteller"],
            "fr": [r"livreur", r"coursier"],
        },
        "delivery_speed": {
            "en": [W(r"next day delivery", 3), W(r"well packed", 2), r"on time", r"as promised", r"fast delivery"],
            "de": [W(r"gut verpackt", 3), r"pünktlich", r"schnelle lieferung"],
            "fr": [W(r"bien emballé", 3), W(r"livraison rapide", 3)],
        },
        "other": {
            "en": [W(r"deliver", 0.5), W(r"parcel", 0.5), W(r"courier", 0.5), W(r"shipping", 0.5)],
            "de": [W(r"liefer", 0.5), W(r"paket", 0.5), W(r"versand", 0.5)],
            "fr": [W(r"livr", 0.5), W(r"colis", 0.5), W(r"expédition", 0.5)],
        },
    },
    "returns": {
        "return_process": {
            "en": [W(r"returns were painless", 3), W(r"return was (easy|quick|painless)", 3), r"painless"],
            "de": [W(r"retoure ging", 3), W(r"rücksendung (ging|war)", 3)],
            "fr": [W(r"retour facile", 3), W(r"retour (rapide|simple)", 3)],
        },
        "exchange": {
            "en": [W(r"exchange", 3), r"different size", r"swap"],
            "de": [W(r"umtausch", 3), W(r"umtauschen", 3), r"andere größe"],
            "fr": [W(r"échange", 3), r"autre taille"],
        },
        "refund": {
            "en": [W(r"(still )?no refund", 3), W(r"refund", 1), r"money back"],
            "de": [W(r"kein geld zurück", 3), r"erstattung", r"rückerstattung"],
            "fr": [W(r"pas remboursé", 3), r"remboursé", r"remboursement"],
        },
        "return_label": {
            "en": [W(r"label", 3), r"won't print", r"print"],
            "de": [W(r"etikett", 3), r"drucken"],
            "fr": [W(r"étiquette", 3), r"imprim"],
        },
        "dropoff": {
            "en": [W(r"drop-?\s?off", 3), W(r"refused my return", 2), r"wasn't in the system", r"collection point"],
            "de": [W(r"abgabestelle", 3), r"paketshop"],
            "fr": [W(r"point relais", 3), r"relais"],
        },
        "return_form": {
            "en": [W(r"returns? form", 3), W(r"reason that applies", 3)],
            "de": [W(r"rücksendeformular", 3), r"retourenformular"],
            "fr": [W(r"formulaire de retour", 3)],
        },
        "returns_policy": {
            "en": [W(r"how long do i have to return", 3), W(r"pay for returns", 3), W(r"free returns", 2),
                   r"return(s)? policy", r"return window"],
            "de": [W(r"wie lange habe ich zeit", 3), W(r"kostenlose rücksendung", 2), r"rückgaberecht"],
            "fr": [W(r"combien de temps ai-je pour retourner", 3), W(r"retours? gratuit", 2)],
        },
        "other": {
            "en": [W(r"return", 0.5), W(r"send(ing)? (it |them |this )?back", 1)],
            "de": [W(r"rücksendung", 0.5), W(r"retoure", 0.5), W(r"zurückschicken", 0.5)],
            "fr": [W(r"retour", 0.5), W(r"retourner", 0.5)],
        },
    },
    "checkout": {
        "checkout_error": {
            "en": [W(r"froze", 3), W(r"frozen", 3), W(r"freez", 3), W(r"logging me out", 3), W(r"vanished", 3),
                   W(r"no idea if it went through", 3), r"checkout (error|crash)"],
            "de": [W(r"friert", 3), W(r"abgemeldet", 3), r"checkout.*(fehler|hängt)"],
            "fr": [W(r"se bloque", 3), W(r"déconnecté", 3), r"planté"],
        },
        "discount_code": {
            "en": [W(r"discount code", 3), W(r"promo code", 3), r"voucher", r"coupon"],
            "de": [W(r"rabattcode", 3), r"gutschein", r"promo-?code"],
            "fr": [W(r"code promo", 3), r"bon de réduction"],
        },
        "basket_total": {
            "en": [W(r"basket total", 3), W(r"total changed", 3), r"price changed"],
            "de": [W(r"warenkorb.*(preis|summe)", 3), r"gesamtsumme"],
            "fr": [W(r"total du panier", 3), r"prix du panier"],
        },
        "guest_checkout": {
            "en": [W(r"as a guest", 3), r"guest checkout"],
            "de": [W(r"gastbestellung", 3), r"als gast"],
            "fr": [W(r"en invité", 3), r"commande invité"],
        },
        "saved_address": {
            "en": [W(r"save my address", 3), r"saved address"],
            "de": [W(r"adresse.*speichern", 3)],
            "fr": [W(r"enregistrer mon adresse", 3)],
        },
        "checkout_speed": {
            "en": [W(r"quick checkout", 3), W(r"ordered in under a minute", 3), r"fast checkout"],
            "de": [W(r"bestellvorgang", 3), r"schnell bestellt"],
            "fr": [W(r"commande passée en une minute", 3), r"commande rapide"],
        },
        "checkout_data": {
            "en": [W(r"asks for my (phone|number|details)", 3), r"why is that needed"],
            "de": [W(r"fragt nach meiner", 3)],
            "fr": [W(r"demande mon (numéro|téléphone)", 3)],
        },
        "other": {
            "en": [W(r"checkout", 0.5), W(r"check out", 0.5), W(r"basket", 0.5), W(r"place order", 0.5)],
            "de": [W(r"checkout", 0.5), W(r"kasse", 0.5), W(r"warenkorb", 0.5), W(r"bestellen", 0.5)],
            "fr": [W(r"panier", 0.5), W(r"commande", 0.5), W(r"commander", 0.5)],
        },
    },
    "payments": {
        "double_charge": {
            "en": [W(r"charged twice", 3), r"double charge", r"charged two times"],
            "de": [W(r"doppelt berechnet", 3), r"doppelt belastet"],
            "fr": [W(r"débité deux fois", 3), r"facturé deux fois"],
        },
        "refund_missing": {
            "en": [W(r"back on my card", 3), W(r"refund for my", 2)],
            "de": [W(r"auf meiner karte", 3)],
            "fr": [W(r"sur ma carte", 3)],
        },
        "payment_failed": {
            "en": [W(r"payment (failed|fails|error)", 3), W(r"declined", 3), W(r"spins forever", 3),
                   W(r"errors out", 3), W(r"can't pay", 3), W(r"payment (system|page)", 2), W(r"money left my account", 3),
                   W(r"cards?, all", 2)],
            "de": [W(r"zahlung.*(fehl|abgelehnt|ausgefallen)", 3), W(r"abgelehnt", 3), W(r"fehlgeschlagen", 3),
                   W(r"zahlungssystem", 3), W(r"zahlung schlägt", 3)],
            "fr": [W(r"paiement (échoue|refusé)", 3), W(r"échoue", 3), W(r"refusée", 3), W(r"système de paiement", 3),
                   W(r"paiement.*(panne|impossible)", 3)],
        },
        "payment_methods": {
            "en": [W(r"apple pay", 3), W(r"pay later", 3), W(r"paying with my phone", 3), W(r"split a payment", 3),
                   r"paypal", r"klarna", r"pay (by|on) invoice"],
            "de": [W(r"bezahlen mit dem handy", 3), W(r"per rechnung", 3), r"paypal", r"klarna", r"apple pay"],
            "fr": [W(r"paiement mobile", 3), W(r"paiement en plusieurs fois", 3), r"paypal", r"apple pay"],
        },
        "other": {
            "en": [W(r"payment", 0.5), W(r"\bcard\b", 0.5), W(r"charged", 0.5), W(r"\bpay\b", 0.5)],
            "de": [W(r"zahlung", 0.5), W(r"bezahl", 0.5), W(r"karte", 0.5)],
            "fr": [W(r"paiement", 0.5), W(r"carte", 0.5), W(r"payer", 0.5)],
        },
    },
    "account": {
        "two_factor": {
            "en": [W(r"two-?factor", 3), r"\b2fa\b", r"verification code", r"code arrives"],
            "de": [W(r"zwei-?faktor", 3), r"bestätigungscode"],
            "fr": [W(r"double authentification", 3), r"code de vérification"],
        },
        "password_reset": {
            "en": [W(r"password reset", 3), W(r"reset (my )?password", 3), r"reset email"],
            "de": [W(r"zurücksetzen des passworts", 3), W(r"passwort", 2)],
            "fr": [W(r"réinitialisation du mot de passe", 3), W(r"mot de passe", 2)],
        },
        "login": {
            "en": [W(r"log ?in", 2), W(r"account is locked", 3), W(r"signing in", 3), r"sign in", r"locked"],
            "de": [W(r"einloggen", 3), W(r"konto gesperrt", 3), W(r"anmeldung", 3)],
            "fr": [W(r"me connecter", 3), W(r"compte bloqué", 3), W(r"connexion", 3)],
        },
        "order_history": {
            "en": [W(r"order history", 3)],
            "de": [W(r"bestellhistorie", 3), W(r"bestellübersicht", 3)],
            "fr": [W(r"historique de commandes?", 3), W(r"historique", 2)],
        },
        "wishlist": {
            "en": [W(r"wishlist", 3), r"wish list"],
            "de": [W(r"wunschliste", 3), r"merkzettel"],
            "fr": [W(r"liste d'envies", 3), r"favoris"],
        },
        "account_settings": {
            "en": [W(r"delete my account", 3), W(r"email address in settings", 3), W(r"settings", 2),
                   W(r"on my account", 3), r"my account", r"profile"],
            "de": [W(r"lösche ich mein konto", 3), W(r"einstellungen", 2), r"mein konto", r"profil"],
            "fr": [W(r"supprimer mon compte", 3), W(r"paramètres", 2), r"mon compte", r"profil"],
        },
        "other": {
            "en": [W(r"account", 0.5), W(r"password", 0.5)],
            "de": [W(r"konto", 0.5), W(r"passwort", 0.5)],
            "fr": [W(r"compte", 0.5), W(r"mot de passe", 0.5)],
        },
    },
    "search": {
        "search_features": {
            "en": [W(r"search by product code", 3), r"product code"],
            "de": [W(r"produktcode", 3), r"artikelnummer"],
            "fr": [W(r"code produit", 3), r"référence"],
        },
        "availability": {
            "en": [W(r"out of stock", 3), r"sold out"],
            "de": [W(r"nicht verfügbar", 3), r"ausverkauft"],
            "fr": [W(r"rupture de stock", 3), r"épuisé"],
        },
        "sorting": {
            "en": [W(r"sorting", 3), W(r"\bsort", 2)],
            "de": [W(r"sortier", 3)],
            "fr": [W(r"\btri\b", 3), r"trier"],
        },
        "filters": {
            "en": [W(r"filters?", 3)],
            "de": [W(r"filter", 3)],
            "fr": [W(r"filtres?", 3)],
        },
        "relevance": {
            "en": [W(r"search results", 3), W(r"won't find", 3), W(r"misspell", 3), W(r"found exactly", 3),
                   r"shows socks", r"useless"],
            "de": [W(r"suche findet nichts", 3), W(r"sofort gefunden", 3), r"gesucht"],
            "fr": [W(r"recherche ne trouve rien", 3), W(r"trouvé ce que je cherchais", 3), r"cherchais"],
        },
        "other": {
            "en": [W(r"search", 0.5), W(r"browse", 0.5)],
            "de": [W(r"suche", 0.5), W(r"suchen", 0.5)],
            "fr": [W(r"recherche", 0.5), W(r"chercher", 0.5)],
        },
    },
    "general": {
        "app_performance": {
            "en": [W(r"\bapp\b.{0,20}(slow|crash|freez|laggy|bug)", 3), W(r"(slow|crash\w*|laggy)\b.{0,20}\bapp\b", 3),
                   r"site is slow", r"website is slow"],
            "de": [W(r"\bapp\b.{0,20}(langsam|stürzt|absturz|hängt)", 3), r"stürzt ab"],
            "fr": [W(r"\bappli(cation)?\b.{0,20}(lent|plante|bug)", 3), r"plante tout le temps"],
        },
        "customer_service": {
            "en": [W(r"customer (service|support)", 3), r"no one (replied|answers)"],
            "de": [W(r"kundenservice", 3), r"kundendienst"],
            "fr": [W(r"service client", 3)],
        },
        "pricing": {
            "en": [W(r"too expensive", 3), r"overpriced", W(r"prices? (are|went)", 2)],
            "de": [W(r"zu teuer", 3), r"preise"],
            "fr": [W(r"trop cher", 3), r"les prix"],
        },
        "other": {"en": [], "de": [], "fr": []},
    },
}

# Words that say how the customer feels. Regular expressions, matched on lower-case text.
POSITIVE: dict[str, list[str]] = {
    "en": [r"\blove", r"\bgreat\b", r"\beasy\b", r"\beasier\b", r"\bfast\b", r"\bquick", r"painless", r"seamless",
           r"friendly", r"convenient", r"perfect", r"excellent", r"thanks", r"thank you", r"\bnice\b", r"\bhappy\b",
           r"found exactly", r"well packed", r"as promised", r"confident", r"\bgood\b", r"amazing", r"brilliant"],
    "de": [r"\bsuper\b", r"\btop\b", r"praktisch", r"\bschnell", r"\beinfach\b", r"problemlos", r"pünktlich",
           r"\bgut\b", r"\btoll\b", r"\bprima\b", r"sofort gefunden", r"\bdanke\b", r"zufrieden", r"bequem", r"perfekt"],
    "fr": [r"rapide", r"\bfacile", r"\bsimple\b", r"pratique", r"sans souci", r"trouvé ce que je cherchais",
           r"bien emballé", r"\bmerci\b", r"\bsuper\b", r"parfait", r"génial", r"excellent"],
}
NEGATIVE: dict[str, list[str]] = {
    "en": [r"\bnot\b", r"\bnever\b", r"can't", r"cannot", r"won't", r"doesn't", r"didn't", r"couldn't", r"isn't",
           r"hasn't", r"wasn't", r"\bfail", r"declined", r"\blate\b", r"broken", r"useless", r"froze", r"frozen",
           r"\bwrong\b", r"still no", r"no idea", r"spins forever", r"locked", r"charged twice", r"soaked", r"missing",
           r"nothing arrived", r"refused", r"expired", r"invalid", r"\bempty\b", r"gave up", r"annoying",
           r"terrible", r"worst", r"\bdown\b", r"\bstuck\b", r"errors? out", r"why do i have to", r"that's new",
           r"still not", r"no refund", r"nothing works", r"all declined", r"disappointed", r"\bno error message\b",
           r"vanished", r"\bleft my parcel\b", r"misspell", r"logging me out", r"reset every time",
           r"keeps? resetting", r"out of stock", r"\bmissed\b", r"nobody told", r"tried (two|three|\d+) times",
           r"\brude\b", r"threw", r"damaged", r"crash", r"too (expensive|high|slow)", r"overpriced", r"charged (two|2) times",
           r"\bslow\b", r"\bwaste\b", r"unhappy", r"hasn't (arrived|turned up|come)", r"turned up", r"no reply",
           r"never (answer|repl)", r"\bbug"],
    "de": [r"\bnicht\b", r"\bnie\b", r"\bkein", r"zurückgesetzt", r"\bverpasst", r"beschädigt", r"zu teuer", r"zu hoch", r"unfreundlich", r"funktioniert nicht",
           r"stürzt", r"\blangsam", r"verspät", r"überfällig", r"ärgerlich", r"gesperrt", r"abgelehnt",
           r"fehlgeschlagen", r"doppelt", r"friert", r"hängt", r"defekt", r"kaputt", r"schon wieder", r"ständig",
           r"immer noch", r"findet nichts", r"lässt sich nicht", r"kommt nie", r"fehler", r"ausgefallen",
           r"wann kommt endlich", r"abgemeldet", r"seit \d+ tagen", r"schlägt .{0,20}fehl", r"\bimmer\b.{0,15}abgemeldet"],
    "fr": [r"\bne\b[^.?!]{0,30}\b(pas|jamais|rien|plus)\b", r"\bn'\w+[^.?!]{0,30}\bpas\b", r"jamais", r"impossible",
           r"refusée?\b", r"bloqué", r"\bbloque", r"échoue", r"retard", r"déconnecté", r"débité deux fois",
           r"pas remboursé", r"toujours pas", r"en panne", r"tout le temps", r"à chaque fois", r"problème",
           r"abîmé", r"endommagé", r"trop cher", r"impoli", r"ne fonctionne pas", r"\blent\b", r"n'arrive pas"],
}

# Words that mark a request for something new, and the start of a question.
SUGGESTION = [r"(could|would|can) you (please )?(add|offer|support|include|provide|make|allow)", r"please add",
              r"it would be (nice|great|good)", r"\bi wish\b", r"pourriez-vous (ajouter|proposer|intégrer)",
              r"(könnten|könnt) (sie|ihr) .{0,30}(hinzufügen|anbieten|einbauen)", r"wäre schön", r"wünsche mir"]
QUESTION_START = [r"^(how|can i|can you|could i|do you|does|is there|are there|why|what|when|which|where)\b",
                  r"^(wie|kann ich|können|gibt es|liefern sie|warum|wann|welche|was)\b",
                  r"^(comment|puis-je|peut-on|combien|acceptez-vous|livrez-vous|pourquoi|quand|est-ce)\b"]

# Words that tell the languages apart when the source does not say which one it is.
STOPWORDS: dict[str, list[str]] = {
    "en": ["the", "is", "my", "i", "to", "and", "it", "not", "can", "do", "you", "for", "with", "was", "have", "of",
           "a", "on", "me", "why", "how"],
    "de": ["der", "die", "das", "ich", "nicht", "und", "ist", "kann", "mein", "meine", "mir", "wie", "zu", "bei", "ein",
           "eine", "auch", "sie", "mit", "für", "nie", "wurde", "habe", "noch"],
    "fr": ["le", "la", "les", "je", "ne", "pas", "de", "est", "mon", "ma", "des", "pour", "vous", "ai", "un", "une",
           "et", "que", "en", "du", "mes", "puis-je", "à"],
}
