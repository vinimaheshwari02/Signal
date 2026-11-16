"""The taxonomy: areas, topics and the trigger words that recognise them, per language.

This is configuration, not logic. To add a topic or a language, edit this file only.
All tenants share it for now (see ADR 0006). Every entry is a regular expression matched against
lower-case text. The topic with the most matching entries wins; ties go to the topic listed first.
A text that matches no topic at all is labelled area "general", topic "other".
"""

# area -> topic -> language -> patterns
TAXONOMY: dict[str, dict[str, dict[str, list[str]]]] = {
    "delivery": {
        "missing_parcel": {
            "en": [r"marked as delivered", r"nothing arrived", r"never arrived", r"not received"],
            "de": [r"zugestellt markiert", r"nie angekommen"],
            "fr": [r"indiqué comme livré", r"jamais reçu"],
        },
        "delivery_slot": {
            "en": [r"delivery slot", r"time slot", r"slot was missed"],
            "de": [r"zeitfenster", r"liefertermin"],
            "fr": [r"créneau"],
        },
        "parcel_condition": {
            "en": [r"left my parcel", r"in the rain", r"soaked", r"damaged", r"crushed", r"box was"],
            "de": [r"beschädigt", r"nass"],
            "fr": [r"abîmé", r"endommagé"],
        },
        "delay": {
            "en": [r"days? late", r"where is my", r"no delivery date", r"still no delivery",
                   r"still not here", r"late parcel", r"\blate\b", r"overdue", r"in transit",
                   r"tracking"],
            "de": [r"überfällig", r"verspät", r"wann kommt", r"verteilzentrum",
                   r"in zustellung", r"sendungsverfolgung", r"tage? verspätung"],
            "fr": [r"de retard", r"suivi", r"retard"],
        },
        "delivery_options": {
            "en": [r"deliver on saturday", r"change the delivery address", r"delivery address after",
                   r"do you deliver"],
            "de": [r"liefern sie", r"samstags"],
            "fr": [r"livrez-vous", r"le samedi"],
        },
        "courier_service": {
            "en": [r"friendly", r"courier", r"driver"],
            "de": [r"kurier", r"fahrer", r"zusteller"],
            "fr": [r"livreur", r"coursier"],
        },
        "delivery_speed": {
            "en": [r"next day delivery", r"well packed", r"on time", r"as promised", r"fast delivery"],
            "de": [r"gut verpackt", r"pünktlich", r"schnelle lieferung"],
            "fr": [r"bien emballé", r"livraison rapide"],
        },
    },
    "returns": {
        "return_process": {
            "en": [r"returns were painless", r"return was (easy|quick|painless)", r"painless"],
            "de": [r"retoure ging", r"rücksendung (ging|war)"],
            "fr": [r"retour facile", r"retour (rapide|simple)"],
        },
        "exchange": {
            "en": [r"exchange", r"different size", r"swap"],
            "de": [r"umtausch", r"umtauschen", r"andere größe"],
            "fr": [r"échange", r"autre taille"],
        },
        "refund": {
            "en": [r"(still )?no refund", r"refund", r"money back"],
            "de": [r"kein geld zurück", r"erstattung", r"rückerstattung"],
            "fr": [r"pas remboursé", r"remboursé", r"remboursement"],
        },
        "return_label": {
            "en": [r"label", r"won't print", r"print"],
            "de": [r"etikett", r"drucken"],
            "fr": [r"étiquette", r"imprim"],
        },
        "dropoff": {
            "en": [r"drop-?\s?off", r"refused my return", r"wasn't in the system", r"collection point"],
            "de": [r"abgabestelle", r"paketshop"],
            "fr": [r"point relais", r"relais"],
        },
        "return_form": {
            "en": [r"returns? form", r"reason that applies"],
            "de": [r"rücksendeformular", r"retourenformular"],
            "fr": [r"formulaire de retour"],
        },
        "returns_policy": {
            "en": [r"how long do i have to return", r"pay for returns", r"free returns",
                   r"return(s)? policy", r"return window"],
            "de": [r"wie lange habe ich zeit", r"kostenlose rücksendung", r"rückgaberecht"],
            "fr": [r"combien de temps ai-je pour retourner", r"retours? gratuit"],
        },
    },
    "checkout": {
        "checkout_error": {
            "en": [r"froze", r"frozen", r"freez", r"logging me out", r"vanished",
                   r"no idea if it went through", r"checkout (error|crash)"],
            "de": [r"friert", r"abgemeldet", r"checkout.*(fehler|hängt)"],
            "fr": [r"se bloque", r"déconnecté", r"planté"],
        },
        "discount_code": {
            "en": [r"discount code", r"promo code", r"voucher", r"coupon"],
            "de": [r"rabattcode", r"gutschein", r"promo-?code"],
            "fr": [r"code promo", r"bon de réduction"],
        },
        "basket_total": {
            "en": [r"basket total", r"total changed", r"price changed"],
            "de": [r"warenkorb.*(preis|summe)", r"gesamtsumme"],
            "fr": [r"total du panier", r"prix du panier"],
        },
        "guest_checkout": {
            "en": [r"as a guest", r"guest checkout"],
            "de": [r"gastbestellung", r"als gast"],
            "fr": [r"en invité", r"commande invité"],
        },
        "saved_address": {
            "en": [r"save my address", r"saved address"],
            "de": [r"adresse.*speichern"],
            "fr": [r"enregistrer mon adresse"],
        },
        "checkout_speed": {
            "en": [r"quick checkout", r"ordered in under a minute", r"fast checkout"],
            "de": [r"bestellvorgang", r"schnell bestellt"],
            "fr": [r"commande passée en une minute", r"commande rapide"],
        },
        "checkout_data": {
            "en": [r"asks for my (phone|number|details)", r"why is that needed"],
            "de": [r"fragt nach meiner"],
            "fr": [r"demande mon (numéro|téléphone)"],
        },
    },
    "payments": {
        "double_charge": {
            "en": [r"charged twice", r"double charge", r"charged two times"],
            "de": [r"doppelt berechnet", r"doppelt belastet"],
            "fr": [r"débité deux fois", r"facturé deux fois"],
        },
        "refund_missing": {
            "en": [r"back on my card", r"refund for my"],
            "de": [r"auf meiner karte"],
            "fr": [r"sur ma carte"],
        },
        "payment_failed": {
            "en": [r"payment (failed|fails|error)", r"declined", r"spins forever",
                   r"errors out", r"can't pay", r"payment (system|page)", r"money left my account",
                   r"cards?, all"],
            "de": [r"zahlung.*(fehl|abgelehnt|ausgefallen)", r"abgelehnt", r"fehlgeschlagen",
                   r"zahlungssystem", r"zahlung schlägt"],
            "fr": [r"paiement (échoue|refusé)", r"échoue", r"refusée", r"système de paiement",
                   r"paiement.*(panne|impossible)"],
        },
        "payment_methods": {
            "en": [r"apple pay", r"pay later", r"paying with my phone", r"split a payment",
                   r"paypal", r"klarna", r"pay (by|on) invoice"],
            "de": [r"bezahlen mit dem handy", r"per rechnung", r"paypal", r"klarna", r"apple pay"],
            "fr": [r"paiement mobile", r"paiement en plusieurs fois", r"paypal", r"apple pay"],
        },
    },
    "account": {
        "two_factor": {
            "en": [r"two-?factor", r"\b2fa\b", r"verification code", r"code arrives"],
            "de": [r"zwei-?faktor", r"bestätigungscode"],
            "fr": [r"double authentification", r"code de vérification"],
        },
        "password_reset": {
            "en": [r"password reset", r"reset (my )?password", r"reset email"],
            "de": [r"zurücksetzen des passworts", r"passwort"],
            "fr": [r"réinitialisation du mot de passe", r"mot de passe"],
        },
        "login": {
            "en": [r"log ?in", r"account is locked", r"signing in", r"sign in", r"locked"],
            "de": [r"einloggen", r"konto gesperrt", r"anmeldung"],
            "fr": [r"me connecter", r"compte bloqué", r"connexion"],
        },
        "order_history": {
            "en": [r"order history"],
            "de": [r"bestellhistorie", r"bestellübersicht"],
            "fr": [r"historique de commandes?", r"historique"],
        },
        "wishlist": {
            "en": [r"wishlist", r"wish list"],
            "de": [r"wunschliste", r"merkzettel"],
            "fr": [r"liste d'envies", r"favoris"],
        },
        "account_settings": {
            "en": [r"delete my account", r"email address in settings", r"settings",
                   r"on my account", r"my account", r"profile"],
            "de": [r"lösche ich mein konto", r"einstellungen", r"mein konto", r"profil"],
            "fr": [r"supprimer mon compte", r"paramètres", r"mon compte", r"profil"],
        },
    },
    "search": {
        "search_features": {
            "en": [r"search by product code", r"product code"],
            "de": [r"produktcode", r"artikelnummer"],
            "fr": [r"code produit", r"référence"],
        },
        "availability": {
            "en": [r"out of stock", r"sold out"],
            "de": [r"nicht verfügbar", r"ausverkauft"],
            "fr": [r"rupture de stock", r"épuisé"],
        },
        "sorting": {
            "en": [r"sorting", r"\bsort"],
            "de": [r"sortier"],
            "fr": [r"\btri\b", r"trier"],
        },
        "filters": {
            "en": [r"filters?"],
            "de": [r"filter"],
            "fr": [r"filtres?"],
        },
        "relevance": {
            "en": [r"search results", r"won't find", r"misspell", r"found exactly",
                   r"shows socks", r"useless"],
            "de": [r"suche findet nichts", r"sofort gefunden", r"gesucht"],
            "fr": [r"recherche ne trouve rien", r"trouvé ce que je cherchais", r"cherchais"],
        },
    },
    "general": {
        "app_performance": {
            "en": [r"\bapp\b.{0,20}(slow|crash|freez|laggy|bug)", r"(slow|crash\w*|laggy)\b.{0,20}\bapp\b",
                   r"site is slow", r"website is slow"],
            "de": [r"\bapp\b.{0,20}(langsam|stürzt|absturz|hängt)", r"stürzt ab"],
            "fr": [r"\bappli(cation)?\b.{0,20}(lent|plante|bug)", r"plante tout le temps"],
        },
        "customer_service": {
            "en": [r"customer (service|support)", r"no one (replied|answers)"],
            "de": [r"kundenservice", r"kundendienst"],
            "fr": [r"service client"],
        },
        "pricing": {
            "en": [r"too expensive", r"overpriced", r"prices? (are|went)"],
            "de": [r"zu teuer", r"preise"],
            "fr": [r"trop cher", r"les prix"],
        },
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
