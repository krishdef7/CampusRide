# Matching load test (simulated traffic)

Environment: API, Postgres and load generator in Docker (Linux containers, Docker Desktop / WSL2); host AMD Ryzen (Family 25 Model 80) (16 logical cores). PostgreSQL 16.4 (Debian 16.4-1.pgdg110+2) on x86_64-pc-linux-gnu. API: uvicorn x4 workers, uvloop + httptools, asyncpg pool 20/worker. Load generator: 4 client processes on the same machine.

Setup: 1000 drivers, 2000 riders, ~200 driver location updates/s in the background, assigned rides completed after 1-3 s (start + complete calls). `synchronous_commit=on`.

| Target rate | Requests | Achieved | Success | Matched | p50 | p95 | p99 | max | Server match p50/p95 (≤) | WS fan-out p50/p95 | Invariant violations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 200/s | 10,000 | 196.4/s | 100.00% | 100.0% | 10.9 ms | 16.8 ms | 27.5 ms | 306.0 ms | 10.0 / 25.0 ms | 5.8 / 7.9 ms | 0 |

Latency = client-observed `POST /rides` round trip: validation, insert, spatial KNN match, atomic claim and NOTIFY in one statement, then the response. Server match = Prometheus histogram of the create+match statement for matched rides (bucket upper bounds).

## Correctness invariants (checked in SQL after each run)

- 200/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 30,000, claims 10,000, rides completed 10,000

Double-booking is checked against the **true modification order**: an audit trigger on `drivers` draws a global sequence number while holding the row lock, so per-driver sequence order is exact. Every history must be linear (each transition's OLD = previous NEW) and every claim must follow a release. Wall-clock and commit timestamps are *not* used: under concurrent commits neither is a total order (both produced false positives during development; see docs/design.md). The partial unique index `rides_one_active_per_driver` independently makes a double assignment impossible to commit.
