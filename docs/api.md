# API documentation

Base URL locally: `http://localhost:8000`. The live OpenAPI page is at `/docs`; ready-made
requests are in `requests/feedback.http`.

## Authentication

Every request carries `X-Api-Key`. A key belongs to one tenant and one channel; the tenant is
always taken from the key, never from the body. Create keys with `scripts/provision_keys.py`.

## Errors

Every error has the same shape and its own status code. Bad input never produces a 5xx.

```json
{"error": "invalid API key"}
```

| Status | Meaning |
|---|---|
| 400 | The body is not valid JSON |
| 401 | Missing or invalid API key |
| 403 | The key belongs to another channel |
| 404 | Unknown channel |
| 413 | Body larger than 64 KiB |
| 422 | Valid JSON with no usable text, or invalid query parameters |
| 503 | Kafka or the database is unavailable: retry |

## POST /v1/sources/{channel}/feedback

Send one feedback item. `channel` is `support_ticket`, `app_store`, `nps_survey`, `in_app` or
`social`; the body is that source's own JSON shape (examples in `requests/feedback.http`).
Optional header `Idempotency-Key`, used when the item has no id of its own.

| Status | Body | Meaning |
|---|---|---|
| 202 | `{"feedback_id": "fb_…", "status": "accepted"}` | Published to Kafka; the worker stores it shortly |
| 200 | `{"feedback_id": "fb_…", "status": "duplicate"}` | Seen before; nothing new is stored |

## GET /v1/feedback

The tenant's labelled items, newest first.

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | 50 | 1 to 200 |
| `before` | – | Only items written before this time (ISO); pass the last item's `created_at` for the next page |
| `area` | – | Only items with this area, e.g. `delivery` |
| `topic` | – | Only items with this topic, e.g. `delay` |
| `channel` | – | Only items from this channel, e.g. `support_ticket` |
| `market` | – | Only items from this market, e.g. `UK` |
| `sentiment` | – | Only items with this sentiment: `negative`, `neutral` or `positive` |
| `kind` | – | Only items of this kind, e.g. `problem` |
| `language` | – | Only items in this language, e.g. `de` |

The filters are exact matches and are combined with AND. They are applied before `limit`, so
`limit=10&market=UK` returns up to 10 UK items. An unknown value returns no items (not an
error); a value longer than 50 characters is a 422.

The feedback behind a theme: the theme's `area` and `topic`.

```
GET /v1/feedback?area=delivery&topic=delay&limit=20
```

```json
{"items": [{"feedback_id": "fb_…", "channel": "support_ticket", "market": "UK", "language": "en",
            "text": "My parcel never arrived, call me on [phone]",
            "created_at": "2026-07-21T04:51:28+00:00", "received_at": "2026-11-16T20:18:15+00:00",
            "sentiment": "negative", "kind": "problem", "area": "delivery", "topic": "missing_parcel"}]}
```

## GET /v1/themes

The tenant's themes, highest impact first (ADR 0007).

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | 20 | 1 to 100 |
| `as_of` | – | Without it: the latest ranking from the scheduler. With it (a date or time): the ranking for the week before that moment, computed on the spot |
| `area` | – | Only themes of this area, e.g. `delivery` |
| `topic` | – | Only themes of this topic, e.g. `delay`. With `area` it names exactly one theme |
| `market` | – | Only themes with customers in this market (a key of `customers_by_market`), e.g. `DE` |

The filters work with and without `as_of` and are applied before `limit`, so
`limit=5&area=delivery` returns up to 5 delivery themes. `market` chooses themes, it does not
recompute them: a kept theme's `score`, customers and evidence still cover all its markets.
If nothing matches, `items` is empty and `as_of` / `computed_at` still show the ranking's dates.

```
GET /v1/themes?area=delivery&market=DE&limit=5
GET /v1/themes?area=delivery&topic=delay                     # one theme: how is it doing?
GET /v1/themes?area=delivery&topic=delay&as_of=2026-09-22    # the same theme a month earlier
```

`?area=delivery&topic=delay` on themes and on `GET /v1/feedback` pair up: the first shows the
theme's score and evidence, the second the messages behind it.

```json
{"as_of": "2026-10-19T00:00:00+00:00", "computed_at": "2026-11-16T20:20:00+00:00",
 "items": [{"theme_id": "ridgeline|delivery|delay", "area": "delivery", "topic": "delay",
            "score": 640.0, "problem_customers": 468, "last_week_customers": 376, "trend": "rising",
            "customers_by_market": {"DE": 210, "UK": 150},
            "evidence": [{"market": "DE", "metric": "deliveries_late / deliveries_due",
                          "current": 0.1915, "normal": 0.1221, "times_worse": 1.57,
                          "extra_affected_orders": 732, "estimated_value_gbp": 63489.02}]}]}
```
The `customers_by_market` values above are illustrative; the other numbers are from the data pack.

## GET /v1/alerts

The tenant's alarms, newest first (ADR 0008). `limit` 1 to 200, default 50.

```json
{"items": [{"alarm": "source_flood", "subject": "ridgeline|support_ticket",
            "fired_at": "2026-09-29T10:14:00+00:00",
            "details": {"channel": "support_ticket", "requests": 92, "window_minutes": 5, "limit": 50}}]}
```

`alarm` is `source_flood`, `incident` or `decline`.

## GET /health

`{"status": "ok"}`, no key needed.
