# The 3-minute demo

Spend the three minutes on decisions and evidence, not on code. Everything below runs from the
Signal folder and IntelliJ (`requests/feedback.http`, environment `local`).

## Prepare (before recording, about 15 minutes)

```bash
colima start --cpu 2 --memory 4
docker compose up --build -d
docker compose exec -T postgres psql -U signal -d signal < migrations/002_themes.sql   # existing DB only
docker compose exec -T postgres psql -U signal -d signal < migrations/003_alarms.sql   # existing DB only
uv run python scripts/provision_keys.py && uv run python scripts/make_http_env.py
uv run python scripts/load_business_daily.py "<data pack>/data/business_daily.csv"
python3 "<data pack>/tools/replay.py" --keys keys.json --file "<data pack>/data/feedback_all.jsonl" --rate 200
docker compose restart scheduler          # rank themes and check alarms straight away
python scripts/alarm_backtest.py "<data pack>/data/feedback_all.jsonl" "<data pack>/data/business_daily.csv" > backtest.txt
```

The demo's POST uses ticket `ZD-1`; if you have sent it before, change the `id` and the
`Idempotency-Key` in `requests/feedback.http` so the first send really returns 202.

Then check once: `GET /v1/themes` shows `ridgeline|delivery|delay` first, and `GET /v1/alerts` is
not empty. Take screenshots of both and of `backtest.txt` in case the live run misbehaves.

## The script

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Title slide | Two retailers get feedback from five channels in five shapes. Signal answers one question: which problem should we fix first? |
| 0:20–0:50 | Architecture slide | The API checks the key, cleans the item and puts it on Kafka, then answers 202. A worker labels it; a scheduler ranks themes and checks alarms. Three decisions: Kafka as a durable log, publish first then remember the key, and row-level security so a tenant can only see its own rows. |
| 0:50–1:25 | IntelliJ: POST support_ticket → 202, same request → 200, then `GET /v1/feedback` | The second send is a duplicate, so it is not stored twice. The stored item is labelled (delivery, missing parcel, problem, negative) and the phone number is masked. |
| 1:25–2:10 | `GET /v1/themes`, then `?as_of=2026-09-22` | Delivery delay leads: 468 customers, rising, and late deliveries in Germany are 1.57 times normal, about 730 extra late orders. One month earlier, a payment outage is second. Customers times business severity, so loud but harmless themes do not win. |
| 2:10–2:35 | `GET /v1/alerts`, then the backtest output | The replay I just ran was itself a flood, so the source alarm fired. The backtest over 90 days finds exactly the resend on 29 September and the payment outage on 21 September, and nothing else. |
| 2:35–3:00 | Results slide | 218 tests, 516 requests a second per process after fixing a blocking route. CI on every push; Prometheus and Grafana for monitoring. Not built yet: dead-letter topic, rate limiting, sending alarms. Those are next. |

Record it in one take after a dry run.
