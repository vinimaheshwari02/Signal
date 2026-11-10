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

ap = argparse.ArgumentParser()
ap.add_argument("feedback")
ap.add_argument("labelled")
ap.add_argument("--show", type=int, default=10, help="wrong examples to print per label")
a = ap.parse_args()

lines = open(a.feedback, encoding="utf-8").read().split("\n")
labelled = [json.loads(line) for line in open(a.labelled, encoding="utf-8")]

LABELS = ("language", "sentiment", "area")
MODES = {"with source hints": True, "text only": False}
correct = {m: collections.Counter() for m in MODES}
by_channel = {m: collections.defaultdict(collections.Counter) for m in MODES}
totals = collections.Counter()
wrong = {m: collections.defaultdict(list) for m in MODES}

for x in labelled:
    row = json.loads(lines[x["line"] - 1], strict=False)
    received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
    item = NORMALISERS[row["channel"]](row["tenant"], row["payload"], received, "salt")
    truth = {"language": x["language"], "sentiment": x["sentiment"], "area": x["product_area"]}
    totals[row["channel"]] += 1
    for mode, use_hints in MODES.items():
        e = enrich(item["text"], item["language"] if use_hints else None, item["sentiment_hint"] if use_hints else None)
        got = {"language": e.language, "sentiment": e.sentiment, "area": e.area}
        for label in LABELS:
            ok = got[label] == truth[label]
            correct[mode][label] += ok
            by_channel[mode][row["channel"]][label] += ok
            if not ok:
                wrong[mode][label].append((truth[label], got[label], item["text"][:90]))

n = len(labelled)
for mode in MODES:
    print(f"\n== {mode}  ({n} items)")
    for label in LABELS:
        print(f"  {label:10} {correct[mode][label] / n:6.1%}  ({correct[mode][label]}/{n})")
    print("  by channel:", "   ".join(
        f"{ch}: " + "/".join(f"{by_channel[mode][ch][l] / totals[ch]:.0%}" for l in LABELS) for ch in sorted(totals)))
    print("  (columns per channel: language/sentiment/area)")
    for label in LABELS:
        for truth, got, text in wrong[mode][label][: a.show]:
            print(f"  wrong {label}: expected {truth}, got {got}: {text}")
