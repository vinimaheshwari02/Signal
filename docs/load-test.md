# Load test

## How it was run

- Tool: the data pack's own `replay.py` in burst mode, 5,000 real data-pack items, 20 clients at once:
  `python3 replay.py --keys keys.json --burst 5000 --concurrency 20`
- System: the real API code, real PostgreSQL (key lookup, idempotency keys, arrival counter), one
  uvicorn process unless stated.
- Kafka could not run in the test machine, so a stand-in publisher waited 5 ms per message, about a
  Kafka round trip with `acks=all`. The numbers therefore leave out Kafka's own limits.
- Machine: 2 CPUs, shared by PostgreSQL, the API and the load generator. Absolute numbers on a
  laptop or server will differ; the comparisons are what matter.

Every run gave the same responses: 4,948 x 202, 22 x 422 (no text), 17 x 401 (unknown tenant),
13 x 400 (cut-off JSON).

## Results

| Setup | Requests/s | Latency p50 | p95 | p99 |
|---|---|---|---|---|
| Before: `async` route calling blocking code | 125 | 157 ms | 171 ms | 187 ms |
| After: blocking work on a worker thread | 516 | 36 ms | 48 ms | 61 ms |
| After, DB pool 5 / 10 / 20 connections | 518 / 573 / 532 | 32–36 ms | 49–54 ms | 59–67 ms |
| After, 2 uvicorn processes | 672 | 26 ms | 47 ms | 60 ms |
| After, 1 process, publisher with no delay | 547 | 33 ms | 49 ms | 70 ms |

## What it shows

1. **The blocking route was the bottleneck.** The POST route was `async def` but waited for
   PostgreSQL and the publisher directly, which stops the event loop: 20 clients were served one
   after the other. Running that work on a worker thread (`run_in_threadpool`) gave 4x the
   throughput and a quarter of the latency.
2. **Now the limit is CPU, not waiting.** The pool size barely matters, and an instant publisher
   is no faster. On 2 shared CPUs, 2 processes reach about 670 requests/s; more CPUs, uvicorn
   workers or API containers raise it further, because the API keeps no state between requests.
3. **Bodies are no longer read in full before the size check.** The route reads at most one byte
   more than the 64 KiB limit; a 5 MB body is answered with 413 without being held in memory.

## Fixes made with this test

- POST route: blocking use case on a worker thread.
- POST route: body read capped at the size limit + 1 byte.
- Worker: a pause between retries (0.5 s, doubling, at most 30 s) instead of retrying in a tight
  loop while the database is down.
- `DB_POOL_SIZE` setting (default 10, was fixed at 5).

## Not covered yet

- Kafka's own throughput and the worker's processing rate (needs the Docker stack).
- Multiple API containers behind a load balancer.
- The read path under load (`GET /v1/feedback`, `GET /v1/themes`): the Redis cache in
  `deployment.md` is planned for that.
