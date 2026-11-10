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
ok, rejected, fell_back = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter()
broken = 0
for line in open(path, encoding="utf-8"):
    try:
        row = json.loads(line, strict=False)  # same leniency as the API
    except ValueError:
        broken += 1  # a cut-off line: the API answers 400 for these
        continue
    channel, payload = row["channel"], row["payload"]
    received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
    try:
        item = NORMALISERS[channel](row["tenant"], payload, received, "salt")
    except Rejected as e:
        rejected[channel][e.reason] += 1
        continue
    ok[channel] += 1
    # In this data the customer's time is close to when we received it, so a big gap means a bad parse.
    if abs((datetime.fromisoformat(item["created_at"]) - received).total_seconds()) > 3600:
        fell_back[channel] += 1

for channel in NORMALISERS:
    print(f"{channel:15} accepted {ok[channel]:6}   time more than 1h from received_at {fell_back[channel]:4}")
    for reason, n in rejected[channel].most_common():
        print(f"{'':15} rejected {n:5}  {reason}")
print(f"lines that are not valid JSON (API answers 400): {broken}")
