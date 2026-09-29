# Engineering log: how the matching numbers were found

The final load-test numbers came out of a sequence of wrong measurements, one real bottleneck
and two false alarms. Each step below is reproducible with the scripts in `loadtest/`.

## 1. The load generator was the bottleneck, not the server

The first sweep (httpx, single process, Windows host, uvicorn on Windows) flatlined at **~55 req/s at every
target rate**, with multi-second latencies. The client's schedule lag was small, so requests left on time
and spent the time waiting for responses. Probes showed:

* `GET /healthz` topped out at ~600 req/s whether the server ran **1 or 4** workers, so the ceiling was the
  client (httpx on one event loop) and/or uvicorn's multi-worker mode on Windows.
* A DB round trip from the host is only 0.5 ms, so the network wasn't it.

**Fix:** measure the system as it would be deployed. API (uvloop + httptools, 4 workers), Postgres and a
multi-process aiohttp load generator all run as Linux containers (`loadtest/run_in_docker.sh`).

## 2. Two commits per ride → one statement

Profiling `create_ride` in-process: INSERT ≈ 3.2 ms, match ≈ 5.4 ms, lookup ≈ 0.7 ms. The INSERT and
the match transaction each paid a **WAL fsync** (`synchronous_commit=on`), plus separate BEGIN, NOTIFY
and COMMIT round trips.

**Fix:** `CREATE_AND_CLAIM_SQL` inserts the ride *already assigned* and claims the driver in **one
statement**: one round trip, one commit. Sequential `POST /rides` went from **11.6 → 7.3 ms p50**.

## 3. The real bottleneck: `NOTIFY` serializes commits

In containers, throughput still capped at **~86 req/s** (p50 425 ms at a 100 req/s target), with the
server-side match histogram in the hundreds of ms. `pg_stat_activity` under load:

```
 state  | wait_event_type | wait_event | count
 active | Lock            | object     |    78      <- at COMMIT
 active | IO              | WALSync    |     1
```

PostgreSQL takes a **database-wide lock when a transaction that issued `NOTIFY` commits, and holds it
through the WAL flush**, so notifications stay in commit order. Every ride write included a
`pg_notify`, so every ride commit queued behind one lock. Throughput ≈ 1 / fsync time, no matter how
many workers.

**Fix:** publish events *after* commit through a per-worker `NotifyPublisher` that coalesces events for
~5 ms and sends each batch as one NOTIFY (a JSON array, chunked under 8 kB). Ride commits run in parallel
again (group commit). Result: **~86 → ~590 req/s**, p50 ≈ 11 ms up to 400 req/s, and WebSocket fan-out
p50 ≈ 6 ms including the batching window. Trade-off: an event can be lost if a worker dies between commit
and flush. WebSocket clients get a fresh state snapshot on (re)connect, so they can't stay stale.

## 4. The invariant checker was wrong twice (and the system was right)

The load test checks that no driver is ever double-booked. Two versions of that check produced
**false positives**:

1. **Wall-clock timestamps.** "Previous ride's `completed_at` > next ride's `assigned_at`" flagged a
   handful of rides per run. `now()` is the *transaction start* time, so switching to `clock_timestamp()`
   helped, but inversions remained. A statement's timestamp isn't its commit order.
2. **Commit timestamps** (`track_commit_timestamp` plus an audit trigger on driver status). This still
   flagged ~1–8 per 10,000. The audit rows looked impossible: a transaction whose `now()` came *after*
   another's commit, yet whose xid came *before* it.

Ruling things out, one experiment each:
* Heap/index corruption? `amcheck` (`bt_index_check`, `verify_heapam`) was clean, with exactly one tuple per driver.
* Clock skew between backends? 4,800 samples across 12 backends: max backwards step 0.025 ms. No skew.
* Non-monotonic xids? 1,800 concurrent transactions: xid order always matched first-write time.

**Resolution:** the trigger now draws a **global sequence number while holding the driver's row lock**.
Updates to one row are serialized by that lock, so per-driver sequence order is the *true modification
order*. Checked that way, **all 30,000 transitions of a 10k-request run form linear histories** (every
transition's OLD equals the previous NEW), with **zero claims without a release**. Commit timestamps are
captured before the commit record is flushed. Under concurrent group commit, visibility order can differ
from timestamp order, so they aren't a total order and can't audit races.

Changes kept from the investigation as defence in depth: a compare-and-set predicate on the claim
(`... AND d.status = 'available'`, re-evaluated by Postgres on the latest row version), and guarded
driver transitions (`WHERE current_ride_id = <this ride>`). Neither was shown to fix a real bug.
They're cheap, and they make the invariant hold by construction rather than by reasoning about lock order.

## 5. Query-level benchmark

`loadtest/bench_matching_query.py` isolates the matching SQL (one connection, rolled-back transactions)
across fleet sizes and densities. See `loadtest/reports/matching_query_bench.md`. The main result: on a dense
campus, KNN top-K over the partial GiST index stays ~1 ms from 1k to 100k drivers, while
"sort everything in the radius" grows linearly. When the radius filter is very selective (drivers spread
over a city), plain radius-sort is as fast or faster, and the planner picks a bitmap scan for both.
