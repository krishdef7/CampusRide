# Matching load test (simulated traffic)

Environment: API, Postgres and load generator in Docker (Linux containers, Docker Desktop / WSL2); host AMD Ryzen (Family 25 Model 80) (16 logical cores). PostgreSQL 16.4 (Debian 16.4-1.pgdg110+2) on x86_64-pc-linux-gnu. API: uvicorn x4 workers, uvloop + httptools, asyncpg pool 20/worker. Load generator: 4 client processes on the same machine.

Setup: 1000 drivers, 2000 riders, ~200 driver location updates/s in the background, assigned rides completed after 1-3 s (start + complete calls). `synchronous_commit=on`.

| Target rate | Requests | Achieved | Success | Matched | p50 | p95 | p99 | max | Server match p50/p95 (≤) | WS fan-out p50/p95 | Invariant violations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100/s | 3,000 | 101.6/s | 100.00% | 100.0% | 9.7 ms | 14.3 ms | 25.3 ms | 184.1 ms | 10.0 / 25.0 ms | 6.0 / 7.2 ms | 0 |
| 200/s | 3,000 | 192.7/s | 100.00% | 100.0% | 10.4 ms | 14.5 ms | 18.4 ms | 49.9 ms | 10.0 / 25.0 ms | 5.8 / 14.0 ms | 0 |
| 300/s | 3,000 | 295.9/s | 100.00% | 100.0% | 11.0 ms | 16.2 ms | 20.6 ms | 35.7 ms | 10.0 / 25.0 ms | 5.5 / 8.1 ms | 0 |
| 400/s | 3,000 | 387.5/s | 100.00% | 100.0% | 11.9 ms | 19.1 ms | 26.9 ms | 61.7 ms | 10.0 / 25.0 ms | 5.7 / 9.4 ms | 0 |
| 500/s | 3,000 | 462.2/s | 100.00% | 99.0% | 13.5 ms | 26.2 ms | 39.3 ms | 76.6 ms | 10.0 / 25.0 ms | 6.3 / 13.6 ms | 0 |
| 600/s | 3,000 | 586.5/s | 100.00% | 83.0% | 22.0 ms | 64.4 ms | 77.9 ms | 111.5 ms | 25.0 / 25.0 ms | 7.2 / 34.3 ms | 0 |

Latency = client-observed `POST /rides` round trip: validation, insert, spatial KNN match, atomic claim and NOTIFY in one statement, then the response. Server match = Prometheus histogram of the create+match statement for matched rides (bucket upper bounds).

## Correctness invariants (checked in SQL after each run)

- 100/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 9,000, claims 3,000, rides completed 3,000
- 200/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 9,000, claims 3,000, rides completed 3,000
- 300/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 9,000, claims 3,000, rides completed 3,000
- 400/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 9,000, claims 3,000, rides completed 3,000
- 500/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 8,942, claims 3,000, rides completed 2,971
- 600/s: claims without prior release = **0**, non linear driver histories = **0**, drivers with multiple active rides = **0**, capacity violations = **0**, vehicle type violations = **0**, driver ride state mismatches = **0**; transitions audited 7,980, claims 3,000, rides completed 2,490

Double-booking is checked against the **true modification order**: an audit trigger on `drivers` draws a global sequence number while holding the row lock, so per-driver sequence order is exact. Every history must be linear (each transition's OLD = previous NEW) and every claim must follow a release. Wall-clock and commit timestamps are *not* used: under concurrent commits neither is a total order (both produced false positives during development; see docs/design.md). The partial unique index `rides_one_active_per_driver` independently makes a double assignment impossible to commit.
