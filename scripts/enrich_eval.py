"""Measure the enrichers against the 500 labelled items.

usage: python scripts/enrich_eval.py path/to/feedback_all.jsonl path/to/labelled_sample.jsonl [--show 15]
Prints accuracy for language, sentiment and area, once with everything the source tells us
(locale, rating, mood) and once from the text alone, plus a few wrong examples.
"""
import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_app.core.enrich import enrich  # noqa: E402
from signal_app.core.normalise import NORMALISERS  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("feedback")
parser.add_argument("labelled")
parser.add_argument("--show", type=int, default=10, help="wrong examples to print per label")
args = parser.parse_args()

with open(args.feedback, encoding="utf-8") as feedback_file:
    lines = feedback_file.read().split("\n")
labelled = []
with open(args.labelled, encoding="utf-8") as labelled_file:
    for line in labelled_file:
        labelled.append(json.loads(line))

LABELS = ("language", "sentiment", "area")
# Two runs: with what the source tells us (locale, rating, mood), and from the text alone.
MODES = {"with source hints": True, "text only": False}

correct = {}      # mode -> label -> how many were right
by_channel = {}   # mode -> channel -> label -> how many were right
wrong = {}        # mode -> label -> examples (expected, got, text)
for mode in MODES:
    correct[mode] = collections.Counter()
    by_channel[mode] = collections.defaultdict(collections.Counter)
    wrong[mode] = collections.defaultdict(list)
totals = collections.Counter()  # channel -> labelled items

for labelled_item in labelled:
    # A labelled item points at a line of the big file; "line" counts from 1.
    row = json.loads(lines[labelled_item["line"] - 1], strict=False)
    channel = row["channel"]
    received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
    normalise = NORMALISERS[channel]
    item = normalise(tenant=row["tenant"], payload=row["payload"], received_at=received, salt="salt")
    expected = {"language": labelled_item["language"], "sentiment": labelled_item["sentiment"],
                "area": labelled_item["product_area"]}
    totals[channel] += 1

    for mode, use_hints in MODES.items():
        language_hint = None
        sentiment_hint = None
        if use_hints:
            language_hint = item["language"]
            sentiment_hint = item["sentiment_hint"]
        labels = enrich(text=item["text"], language=language_hint, sentiment_hint=sentiment_hint)
        got = {"language": labels.language, "sentiment": labels.sentiment, "area": labels.area}
        for label in LABELS:
            if got[label] == expected[label]:
                correct[mode][label] += 1
                by_channel[mode][channel][label] += 1
            else:
                wrong[mode][label].append((expected[label], got[label], item["text"][:90]))

total = len(labelled)
for mode in MODES:
    print(f"\n== {mode}  ({total} items)")
    for label in LABELS:
        print(f"  {label:10} {correct[mode][label] / total:6.1%}  ({correct[mode][label]}/{total})")

    channel_parts = []
    for channel in sorted(totals):
        percentages = []
        for label in LABELS:
            percentages.append(f"{by_channel[mode][channel][label] / totals[channel]:.0%}")
        channel_parts.append(f"{channel}: " + "/".join(percentages))
    print("  by channel:", "   ".join(channel_parts))
    print("  (columns per channel: language/sentiment/area)")

    for label in LABELS:
        for expected_value, got_value, text in wrong[mode][label][: args.show]:
            print(f"  wrong {label}: expected {expected_value}, got {got_value}: {text}")
