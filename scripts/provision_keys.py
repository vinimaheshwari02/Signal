"""Create one API key per tenant + channel and write them to keys.json.

usage: python scripts/provision_keys.py [--db postgresql://signal:signal@localhost:5432/signal]

keys.json is what the data pack's replay.py reads (--keys keys.json). Running this again
replaces the old keys. Only the hash of each key is stored in the database.
"""
import argparse
import json
import secrets
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_app.core.ids import hash_api_key  # noqa: E402  (the same hash the API uses)

TENANTS = ["ridgeline", "harbour-home"]
CHANNELS = ["support_ticket", "app_store", "nps_survey", "in_app", "social"]

parser = argparse.ArgumentParser()
parser.add_argument("--db", default="postgresql://signal:signal@localhost:5432/signal")
parser.add_argument("--out", default="keys.json")
args = parser.parse_args()

keys = {}
with psycopg.connect(args.db) as conn:
    for tenant in TENANTS:
        conn.execute("INSERT INTO tenants VALUES (%s) ON CONFLICT DO NOTHING", (tenant,))
        keys[tenant] = {}
        for channel in CHANNELS:
            api_key = "sk_" + secrets.token_urlsafe(24)
            conn.execute("DELETE FROM api_keys WHERE tenant_id=%s AND channel=%s", (tenant, channel))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,%s)",
                         (hash_api_key(api_key), tenant, channel))
            keys[tenant][channel] = api_key

with open(args.out, "w") as out_file:
    json.dump(keys, out_file, indent=2)
print(f"wrote {args.out}")
