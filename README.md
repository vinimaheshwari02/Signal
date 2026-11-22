# Signal

Feedback: An Analyzer for feedback

Signal collects customer feedback from several channels for several retailers (tenants), cleans it
into one shape, groups it into themes, ranks them by impact and raises alarms.

Design docs: [`docs/`](docs/) (ADRs, sequence diagrams, deployment, threat model).

## Run it locally

```bash
docker compose up --build -d          # redpanda (+ topic), postgres, api, worker, scheduler
uv run python scripts/provision_keys.py   # writes keys.json (git-ignored)
uv run python scripts/load_business_daily.py path/to/business_daily.csv   # for the impact score
```

A database created before themes and alarms existed needs the newer migrations once, in order:
`docker compose exec -T postgres psql -U signal -d signal < migrations/002_themes.sql`, then the
same with `003_alarms.sql`.

Send one ticket:

```bash
KEY=$(python3 -c "import json;print(json.load(open('keys.json'))['ridgeline']['support_ticket'])")
curl -i -X POST localhost:8000/v1/sources/support_ticket/feedback \
  -H "X-Api-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"ticket":{"id":"ZD-1","created":1784597786000,"description":"My parcel never arrived","requester":{"customer_ref":"C1","locale":"en-GB"}}}'
# 202 first time, 200 if you send it again
curl -H "X-Api-Key: $KEY" localhost:8000/v1/feedback
```

Ranked themes (the scheduler refreshes them every 5 minutes, for the week before `AS_OF`,
which is 2026-10-19 in `docker-compose.yml` because the data pack ends on 2026-10-18):

```bash
curl -H "X-Api-Key: $KEY" localhost:8000/v1/themes
curl -H "X-Api-Key: $KEY" "localhost:8000/v1/themes?as_of=2026-09-22"   # look back at another week
```

Alarms (source flood, incident, slow decline; ADR 0008), stored and listed, not sent:

```bash
curl -H "X-Api-Key: $KEY" localhost:8000/v1/alerts
docker compose logs scheduler | grep ALARM
python scripts/alarm_backtest.py path/to/feedback_all.jsonl path/to/business_daily.csv   # 90 days, no Docker
```

Replay the data pack with its own `replay.py` (it is not part of this repository):
`python path/to/replay.py --keys keys.json --channel support_ticket --limit 200`.

## Tests

```bash
uv sync && uv run pytest
```

## Testing

See [TESTING.md](TESTING.md). Architecture documents: [docs/README.md](docs/README.md).

## Status

All 5 channels (support_ticket, app_store, nps_survey, in_app, social) -> API -> Kafka -> worker (normalise + rule-based enrichment: language, sentiment, kind, area, topic) -> PostgreSQL -> `GET /v1/feedback`.
Themes and impact score (ADR 0007): scheduler -> `themes` table -> `GET /v1/themes`.
Alarms (ADR 0008): scheduler -> `alerts` table -> `GET /v1/alerts`, tuned with `scripts/alarm_backtest.py`.
Load test: `docs/load-test.md` (about 520 requests/s per API process on 2 shared CPUs).
Next: sending alarms (Slack/e-mail), dead-letter topic, Redis cache for the read path, rate limiting.
