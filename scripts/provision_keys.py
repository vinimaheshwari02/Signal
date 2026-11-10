"""Create one API key per tenant + channel. Writes keys.json for tools/replay.py.

usage: python scripts/provision_keys.py [--db postgresql://signal:signal@localhost:5432/signal]
"""
import argparse
import hashlib
import json
import secrets

import psycopg

TENANTS = ["ridgeline", "harbour-home"]
CHANNELS = ["support_ticket", "app_store", "nps_survey", "in_app", "social"]

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="postgresql://signal:signal@localhost:5432/signal")
ap.add_argument("--out", default="keys.json")
a = ap.parse_args()

keys = {}
with psycopg.connect(a.db) as conn:
    for t in TENANTS:
        conn.execute("INSERT INTO tenants VALUES (%s) ON CONFLICT DO NOTHING", (t,))
        keys[t] = {}
        for c in CHANNELS:
            k = "sk_" + secrets.token_urlsafe(24)
            conn.execute("DELETE FROM api_keys WHERE tenant_id=%s AND channel=%s", (t, c))
            conn.execute("INSERT INTO api_keys (key_hash, tenant_id, channel) VALUES (%s,%s,%s)",
                         (hashlib.sha256(k.encode()).hexdigest(), t, c))
            keys[t][c] = k
json.dump(keys, open(a.out, "w"), indent=2)
print(f"wrote {a.out}")
