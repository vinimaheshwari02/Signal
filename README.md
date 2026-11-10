# Signal

Feedback: An Analyzer for feedback

Signal collects customer feedback from several channels for several retailers (tenants), cleans it
into one shape, and (soon) groups it into themes and ranks them by impact.

Design docs: [`docs/`](docs/) (ADRs, sequence diagrams, deployment, threat model).

## Run it locally

```bash
docker compose up --build -d          # redpanda, postgres, api, worker
uv run python scripts/provision_keys.py   # writes keys.json (git-ignored)
```

Send one ticket:

```bash
KEY=$(python3 -c "import json;print(json.load(open('keys.json'))['ridgeline']['support_ticket'])")
curl -i -X POST localhost:8000/v1/sources/support_ticket/feedback \
  -H "X-Api-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"ticket":{"id":"ZD-1","created":1784597786000,"description":"My parcel never arrived","requester":{"customer_ref":"C1","locale":"en-GB"}}}'
# 202 first time, 200 if you send it again
curl -H "X-Api-Key: $KEY" localhost:8000/v1/feedback
```

Replay the data pack: `python tools/replay.py --keys keys.json --channel support_ticket --limit 200`.

## Tests

```bash
uv sync && uv run pytest
```

## Testing

See [TESTING.md](TESTING.md).

## Status

All 5 channels (support_ticket, app_store, nps_survey, in_app, social) -> API -> Kafka -> worker (normalise + rule-based enrichment: language, sentiment, kind, area, topic) -> PostgreSQL -> `GET /v1/feedback`.
Next: themes and impact score, alarms, business_daily, load test.
