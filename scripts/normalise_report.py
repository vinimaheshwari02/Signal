"""Run every line of feedback_all.jsonl through the normalisers (no API, Kafka or database).

usage: python scripts/normalise_report.py path/to/feedback_all.jsonl
Shows, per channel, how many items were accepted or rejected, and why.
"""
import collections
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_app.core.errors import Rejected  # noqa: E402
from signal_app.core.normalise import NORMALISERS  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "data/feedback_all.jsonl"
accepted = collections.Counter()                           # channel -> items accepted
rejected = collections.defaultdict(collections.Counter)    # channel -> reason -> items rejected
odd_time = collections.Counter()                           # channel -> items with a surprising time
broken = 0                                                 # lines that are not valid JSON

with open(path, encoding="utf-8") as data_file:
    for line in data_file:
        try:
            row = json.loads(line, strict=False)  # same leniency as the API
        except ValueError:
            broken += 1  # a cut-off line: the API answers 400 for these
            continue
        channel = row["channel"]
        received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
        normalise = NORMALISERS[channel]
        try:
            item = normalise(tenant=row["tenant"], payload=row["payload"], received_at=received, salt="salt")
        except Rejected as rejection:
            rejected[channel][rejection.reason] += 1
            continue
        accepted[channel] += 1
        # In this data the customer's time is close to when we received it, so a big gap means a
        # bad parse.
        created = datetime.fromisoformat(item["created_at"])
        gap_seconds = abs((created - received).total_seconds())
        if gap_seconds > 3600:
            odd_time[channel] += 1

for channel in NORMALISERS:
    print(f"{channel:15} accepted {accepted[channel]:6}   time more than 1h from received_at {odd_time[channel]:4}")
    for reason, count in rejected[channel].most_common():
        print(f"{'':15} rejected {count:5}  {reason}")
print(f"lines that are not valid JSON (API answers 400): {broken}")
