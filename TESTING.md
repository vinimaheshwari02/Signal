# How to test Signal

Five levels, from fastest to most realistic. Each one proves something different.

## 1. Unit tests (no Docker, ~1 second)

```bash
uv sync
uv run pytest
```

138 tests (8 integration tests are skipped unless level 4 is set up). They cover:
- `test_normalise_channels.py` – each of the 5 channels' messy-data rules (time formats, word-number
  ratings, PII masking, missing text -> rejected).
- `test_enrich.py` – language, sentiment, kind, area and topic for en/de/fr.
- `test_process.py` – all 5 channels through API -> worker using in-memory fakes.
- `test_http.py`, `test_ingest_usecase.py`, `test_ids.py` – status codes, idempotency, ids.
- `test_architecture.py` – fails if `core/` imports FastAPI, Kafka or psycopg.

## 2. Check the rules against the real data pack (no Docker)

```bash
python scripts/normalise_report.py path/to/feedback_all.jsonl
python scripts/enrich_eval.py path/to/feedback_all.jsonl path/to/labelled_sample.jsonl --show 10
```

- `normalise_report.py`: per channel, how many records are accepted/rejected, and whether the
  timestamps look sane. Cut-off lines in the pack are counted as "would get 400".
- `enrich_eval.py`: accuracy against `labelled_sample.jsonl` for language, sentiment and area.
  Be careful: the rules were tuned on this data, so ~100% overstates how it will do on new text.
  `--show 10` prints examples that disagree with the labels.

## 3. Full stack by hand

```bash
docker compose up --build -d
python scripts/provision_keys.py          # writes keys.json (a key per tenant + channel)
```

Pick a key, e.g. `KEY=$(python3 -c "import json;print(json.load(open('keys.json'))['ridgeline']['nps_survey'])")`
and post one example per channel (the path's channel must match the key's channel):

```bash
# support_ticket
curl -i -X POST localhost:8000/v1/sources/support_ticket/feedback -H "X-Api-Key: $KEY" \
  -H 'Content-Type: application/json' \
  -d '{"ticket":{"id":"ZD-1","created":1784609488000,"description":"Parcel never arrived","requester":{"customer_ref":"C1","locale":"en-GB"},"brand":"ridgeline"}}'
# app_store
-d '{"review_id":"rv_1","rating":3,"title":"Kann ich per Rechnung bezahlen?","body":"Kann ich auch per Rechnung bezahlen?","reviewed_at":"2026-07-21T05:53:50Z","territory":"DE","app":"ridgeline"}'
# nps_survey
-d '{"response_id":"nps-1","score":10,"comment":"Free returns made me confident to order.","submitted":"21/07/2026 02:52","customer_id":"C1","market":"UK","account":"ridgeline"}'
# in_app
-d '{"event":"feedback_submitted","ts":"2026-07-21T03:11:49.000+02:00","user":{"id":"C1","locale":"fr-FR"},"app":"ridgeline","payload":{"screen":"orders/returns","message":"Retour envoyé il y a 4 jours, toujours pas remboursé.","mood":"angry"}}'
# social
-d '{"post_id":"1790000000000087109","text":"Parcel marked as delivered but nothing arrived.","created_at":"Tue, 21 Jul 2026 01:52:52 +0000","lang":"en","author_handle":"@jan1134"}'
```
(Use the same `curl` as above with the matching `/v1/sources/<channel>/feedback` path and key.)

Expected:
| What you do | Result |
|---|---|
| First post | `202` |
| Same post again | `200` (duplicate) |
| Wrong/missing key | `401` |
| Key for another channel | `403` |
| Body that is not JSON / cut off | `400` |
| Valid JSON with no text | `422` |
| Kafka stopped (`docker compose stop redpanda`) | `503` |

Then read it back (a few seconds later – the worker is asynchronous):

```bash
curl -H "X-Api-Key: $KEY" localhost:8000/v1/feedback
```
Each item should have `sentiment`, `kind`, `area`, `topic`, `language`, with the email, phone
number and order number masked (`[email]`, `[phone]`, `[order]`) and `created_at` in UTC.
Ridgeline's key must never return Harbour Home's rows. Worker logs: `docker compose logs -f worker`.

## 4. Integration tests against real PostgreSQL

With the compose Postgres running (check `docker-compose.yml` for the ports and passwords):

```bash
TEST_OWNER_URL=postgresql://signal:signal@localhost:5432/signal \
TEST_API_URL=postgresql://signal_api:<password>@localhost:5432/signal \
uv run pytest tests/integration
```
Proves: POST -> worker -> GET, duplicates, nothing saved when publishing fails, tenant isolation by
row-level security, the API role cannot write feedback, repeated saves are harmless.

## 5. Replay the data pack against the running stack

```bash
python tools/replay.py --keys keys.json --channel nps_survey --limit 200 --dry-run   # look first
python tools/replay.py --keys keys.json --channel nps_survey --limit 200
python tools/replay.py --keys keys.json --limit 5000 --no-idempotency-key            # compare dedupe
```
Expect mostly `202`, a few `400` (cut-off lines), `422` (no text) and `401` (the unknown tenant `acme`).
In my run of the first 6000 lines against a real Postgres: 5938 x 202, 25 x 422, 17 x 400, 20 x 401,
and every accepted line was stored with area/kind/sentiment. Check in SQL:

```sql
select area, count(*) from feedback group by 1 order by 2 desc;
select kind, count(*) from feedback group by 1;
```

## Not tested yet
Kafka/Redpanda and Docker were not available where I built this, so levels 3 and 5 against the real
stack are for you to run first. Report anything odd.
