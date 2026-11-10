"""Turn keys.json (from provision_keys.py) into requests/http-client.private.env.json for IntelliJ.

usage: python scripts/make_http_env.py [--tenant ridgeline]
"""
import argparse
import json

ap = argparse.ArgumentParser()
ap.add_argument("--tenant", default="ridgeline")
a = ap.parse_args()
keys = json.load(open("keys.json"))[a.tenant]
json.dump({"local": keys}, open("requests/http-client.private.env.json", "w"), indent=2)
print("wrote requests/http-client.private.env.json for", a.tenant)
