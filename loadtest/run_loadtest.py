"""Open-loop load test of ride creation + inline matching, with correctness invariants checked afterwards.

What it does
1. Resets a dedicated database (`campusride_load`), seeds N drivers around campus and M riders.
2. Fires ride requests on an open-loop Poisson schedule, split across several client *processes* so the
   load generator isn't the bottleneck. Arrivals don't wait for responses, so slow responses can't hide
   (no coordinated omission).
3. Meanwhile, drivers stream location updates, and a "fleet" completes assigned rides after 1-3 s
   (start + complete), recycling drivers the way a real shift would.
4. A WebSocket client on /ws/live measures commit -> NOTIFY -> WebSocket fan-out latency.
5. Afterwards, SQL checks the invariants: no driver ever held two overlapping rides, no capacity or
   vehicle-type violation, consistent driver/ride state.

Reference setup (everything in Linux containers, as it would be deployed):
    loadtest/run_in_docker.sh --requests 10000 --rate 300
Or against any running API:
    python loadtest/run_loadtest.py --base-url http://127.0.0.1:8000 --requests 10000 --rate 300
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import random
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import aiohttp
import asyncpg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusride import campus  # noqa: E402
from campusride.db import apply_schema, reset_operational_data  # noqa: E402

REPORTS = ROOT / "loadtest" / "reports"
BASE_DSN = os.getenv("DATABASE_URL", "postgresql://campusride:campusride@localhost:5433/campusride")


def load_dsn() -> str:
    return os.getenv("LOAD_DATABASE_URL") or re.sub(r"/[^/]+$", "/campusride_load", BASE_DSN)


async def ensure_db(dsn: str) -> None:
    admin = await asyncpg.connect(re.sub(r"/[^/]+$", "/postgres", dsn))
    name = dsn.rsplit("/", 1)[1]
    if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
        await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    conn = await asyncpg.connect(dsn)
    await apply_schema(conn)
    await conn.close()


# Load-test-only instrumentation: every driver status change, with its transaction id, so the invariant
# check can use *commit order* (pg_xact_commit_timestamp) instead of statement wall-clock stamps.
AUDIT_SQL = """
DROP TABLE IF EXISTS driver_audit;
DROP SEQUENCE IF EXISTS driver_audit_seq;
CREATE SEQUENCE driver_audit_seq;
CREATE TABLE driver_audit (seq bigint DEFAULT nextval('driver_audit_seq'), at timestamptz, xid bigint, driver_id bigint, old_status text, new_status text,
                           old_ride bigint, new_ride bigint, txn_start timestamptz, stmt_start timestamptz, pid int);
CREATE OR REPLACE FUNCTION audit_driver() RETURNS trigger AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO driver_audit (at, xid, driver_id, old_status, new_status, old_ride, new_ride, txn_start, stmt_start, pid)
    VALUES (clock_timestamp(), txid_current(), NEW.id, OLD.status, NEW.status,
                                     OLD.current_ride_id, NEW.current_ride_id, now(), statement_timestamp(), pg_backend_pid());
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER t_audit AFTER UPDATE ON drivers FOR EACH ROW EXECUTE FUNCTION audit_driver();
"""


async def prepare_db(dsn: str, n_drivers: int, n_riders: int, seed: int) -> None:
    await ensure_db(dsn)
    conn = await asyncpg.connect(dsn)
    await reset_operational_data(conn)
    rng = random.Random(seed)
    places = list(campus.PLACES.values())
    drivers = []
    for i in range(n_drivers):
        p = rng.choice(places)
        vt = rng.choices(["e_rickshaw", "auto", "cab"], weights=[60, 25, 15])[0]
        # ~250 m jitter around a landmark
        drivers.append((f"d{i}", vt, campus.CAPACITY[vt], p.lat + rng.gauss(0, 0.0022), p.lon + rng.gauss(0, 0.0025)))
    await conn.executemany(
        "INSERT INTO drivers (name, vehicle_type, capacity, status, location, last_seen) "
        "VALUES ($1, $2, $3, 'available', ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography, now() + interval '6 hours')",
        drivers,
    )
    await conn.executemany("INSERT INTO riders (name) VALUES ($1)", [(f"r{i}",) for i in range(n_riders)])
    await conn.execute(AUDIT_SQL)  # after seeding, so only load-test transitions are audited
    await conn.execute("VACUUM ANALYZE")
    await conn.close()


async def wait_ready(base: str, deadline_s: float = 90) -> None:
    t0 = time.time()
    async with aiohttp.ClientSession() as s:
        while time.time() - t0 < deadline_s:
            try:
                async with s.get(f"{base}/readyz") as r:
                    if r.status == 200:
                        return
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"API at {base} did not become ready")


# ------------------------------------------------------------------ client process


def client_process(base: str, n_requests: int, rate: float, n_riders: int, n_drivers: int, seed: int,
                   loc_rate: float) -> list[dict]:
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass
    return asyncio.run(_client(base, n_requests, rate, n_riders, n_drivers, seed, loc_rate))


async def _client(base, n_requests, rate, n_riders, n_drivers, seed, loc_rate) -> list[dict]:
    rng = random.Random(seed)
    places = list(campus.PLACES)
    weights = [3 if campus.PLACES[p].kind == "hostel" else 2 if campus.PLACES[p].zone == "acad" else 1 for p in places]
    results: list[dict] = []
    background: set[asyncio.Task] = set()
    stop = asyncio.Event()
    conn = aiohttp.TCPConnector(limit=512, limit_per_host=512)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(base, connector=conn, timeout=timeout) as http:

        async def finish(ride_id: int, driver_id: int, delay: float):
            await asyncio.sleep(delay)
            try:
                async with http.post(f"/drivers/{driver_id}/rides/{ride_id}/start") as r:
                    await r.read()
                async with http.post(f"/drivers/{driver_id}/rides/{ride_id}/complete") as r:
                    await r.read()
            except (aiohttp.ClientError, TimeoutError):
                pass

        async def create(scheduled_at: float):
            pickup = rng.choices(places, weights)[0]
            dropoff = rng.choice([p for p in places if p != pickup])
            pax = rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
            vt = rng.choices([None, "e_rickshaw", "auto", "cab"], weights=[85, 5, 5, 5])[0]
            if vt and campus.CAPACITY[vt] < pax:
                vt = "cab"
            body = {"rider_id": rng.randint(1, n_riders), "pickup_place_id": pickup, "dropoff_place_id": dropoff,
                    "passengers": pax, "vehicle_type": vt}
            t_send = time.perf_counter()
            try:
                async with http.post("/rides", json=body) as r:
                    data = await r.json() if r.status == 201 else {}
                    code = r.status
                dt = (time.perf_counter() - t_send) * 1000
                ok = code == 201
                results.append({"ms": dt, "ok": ok, "status": data.get("status"), "code": code,
                                "lag_ms": (t_send - scheduled_at) * 1000, "t": t_send})
                if ok and data.get("status") == "assigned":
                    t = asyncio.create_task(finish(data["id"], data["driver_id"], rng.uniform(1, 3)))
                    background.add(t)
                    t.add_done_callback(background.discard)
            except (aiohttp.ClientError, TimeoutError) as e:
                results.append({"ms": (time.perf_counter() - t_send) * 1000, "ok": False, "status": None,
                                "code": type(e).__name__, "lag_ms": (t_send - scheduled_at) * 1000, "t": t_send})

        async def locations():
            p = campus.PLACES
            per_tick = max(1, round(loc_rate / 10))
            while loc_rate > 0 and not stop.is_set():
                t0 = time.perf_counter()

                async def one():
                    pl = p[rng.choice(places)]
                    try:
                        async with http.put(f"/drivers/{rng.randint(1, n_drivers)}/location",
                                            json={"lat": pl.lat + rng.gauss(0, 0.002), "lon": pl.lon + rng.gauss(0, 0.002)}) as r:
                            await r.read()
                    except (aiohttp.ClientError, TimeoutError):
                        pass
                await asyncio.gather(*(one() for _ in range(per_tick)))
                await asyncio.sleep(max(0, 0.1 - (time.perf_counter() - t0)))

        loc_task = asyncio.create_task(locations())
        tasks = []
        next_t = time.perf_counter()
        for _ in range(n_requests):
            next_t += rng.expovariate(rate)
            delay = next_t - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(create(next_t)))
        await asyncio.gather(*tasks)
        await asyncio.gather(*list(background), return_exceptions=True)  # let completions finish
        stop.set()
        await loc_task
    return results


# ------------------------------------------------------------------ orchestration


async def ws_listener(url: str, lat: list[float], stop: asyncio.Event) -> None:
    async with aiohttp.ClientSession() as s, s.ws_connect(url, max_msg_size=2**25) as ws:
        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
            except TimeoutError:
                continue
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            m = json.loads(msg.data)
            if m.get("type") == "ride_event" and "ts" in m:
                lat.append((time.time() - m["ts"]) * 1000)


async def scrape(base: str) -> str:
    async with aiohttp.ClientSession() as s, s.get(f"{base}/metrics") as r:
        return await r.text()


def histogram(metrics_text: str, name: str, label: str) -> dict[float, float]:
    out = {}
    for line in metrics_text.splitlines():
        if line.startswith(f"{name}_bucket") and label in line:
            le = re.search(r'le="([^"]+)"', line).group(1)
            out[float("inf") if le == "+Inf" else float(le)] = float(line.rsplit(" ", 1)[1])
    return out


def histogram_delta_quantiles(before: dict, after: dict) -> dict:
    """Quantiles (bucket upper bounds, i.e. conservative) of the observations made *during* the run."""
    buckets = sorted((b, after.get(b, 0) - before.get(b, 0)) for b in after)
    if not buckets or buckets[-1][1] == 0:
        return {}
    total = buckets[-1][1]
    out = {"count": int(total)}
    for q in (0.5, 0.95, 0.99):
        out[f"p{int(q * 100)}_le_ms"] = next(b * 1000 for b, c in buckets if c >= q * total)
    return out


async def run_once(base: str, args, rate: float, seed: int) -> dict:
    stop = asyncio.Event()
    ws_lat: list[float] = []
    ws_task = asyncio.create_task(ws_listener(base.replace("http", "ws", 1) + "/ws/live", ws_lat, stop))
    await asyncio.sleep(0.5)
    before = histogram(await scrape(base), "match_duration_seconds", 'outcome="matched"')

    loop = asyncio.get_running_loop()
    procs = args.client_procs
    per = [args.requests // procs + (1 if i < args.requests % procs else 0) for i in range(procs)]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(procs) as pool:
        chunks = await asyncio.gather(*[
            loop.run_in_executor(pool, client_process, base, per[i], rate / procs, args.riders, args.drivers,
                                 seed * 100 + i, args.location_rate / procs)
            for i in range(procs)
        ])
    wall = time.perf_counter() - t0
    await asyncio.sleep(1.0)
    stop.set()
    await asyncio.gather(ws_task, return_exceptions=True)
    after = histogram(await scrape(base), "match_duration_seconds", 'outcome="matched"')

    results = [r for c in chunks for r in c]
    first = min(r["t"] for r in results) if results else 0
    send_span = (max(r["t"] for r in results) - first) if results else 1
    ms = np.array([r["ms"] for r in results if r["ok"]])
    lag = np.array([r["lag_ms"] for r in results])
    statuses = [r["status"] for r in results if r["ok"]]
    errors = [r["code"] for r in results if not r["ok"]]
    wl = np.array(ws_lat) if ws_lat else np.array([np.nan])
    return {
        "target_rate_rps": rate, "requests": len(results), "client_processes": procs, "wall_s": round(wall, 2),
        "achieved_throughput_rps": round(len(results) / max(send_span, 1e-9), 1),
        "success_rate": round(len(ms) / max(1, len(results)), 5),
        "errors": {str(k): errors.count(k) for k in set(errors)},
        "matched_rate": round(statuses.count("assigned") / max(1, len(statuses)), 4),
        "latency_ms": {q: round(float(np.percentile(ms, p)), 1) for q, p in
                       (("p50", 50), ("p90", 90), ("p95", 95), ("p99", 99), ("max", 100))} | {"mean": round(float(ms.mean()), 1)},
        "client_schedule_lag_ms_p99": round(float(np.percentile(lag, 99)), 1),
        "ws_fanout_ms": {"events": len(ws_lat), "p50": round(float(np.nanpercentile(wl, 50)), 1),
                         "p95": round(float(np.nanpercentile(wl, 95)), 1)},
        "server_match_histogram": histogram_delta_quantiles(before, after),
    }


async def invariants(dsn: str) -> dict:
    conn = await asyncpg.connect(dsn)
    try:
        q = {
            "drivers_with_multiple_active_rides": """
                SELECT count(*) FROM (SELECT driver_id FROM rides WHERE status IN ('assigned','in_progress')
                GROUP BY driver_id HAVING count(*) > 1) x""",
            "capacity_violations": """
                SELECT count(*) FROM rides r JOIN drivers d ON d.id = r.driver_id WHERE r.passengers > d.capacity""",
            "vehicle_type_violations": """
                SELECT count(*) FROM rides r JOIN drivers d ON d.id = r.driver_id
                WHERE r.vehicle_type IS NOT NULL AND r.vehicle_type <> d.vehicle_type""",
            "driver_ride_state_mismatches": """
                SELECT count(*) FROM rides r JOIN drivers d ON d.id = r.driver_id
                WHERE r.status IN ('assigned','in_progress') AND d.current_ride_id IS DISTINCT FROM r.id""",
        }
        out = {k: await conn.fetchval(v) for k, v in q.items()}
        # Authoritative double-booking check. The trigger draws a global sequence number while holding the
        # driver's row lock, so per-driver sequence order IS the true modification order.
        # (Neither wall-clock stamps nor commit timestamps are a total order under concurrent commits.)
        out["non_linear_driver_histories"] = await conn.fetchval("""
            WITH s AS (SELECT old_status, old_ride, row_number() OVER w AS k,
                              lag(new_status) OVER w AS prev_new, lag(new_ride) OVER w AS prev_ride
                       FROM driver_audit WINDOW w AS (PARTITION BY driver_id ORDER BY seq))
            SELECT count(*) FROM s
            WHERE k > 1 AND (old_status IS DISTINCT FROM prev_new OR old_ride IS DISTINCT FROM prev_ride)""")
        out["claims_without_prior_release"] = await conn.fetchval("""
            WITH s AS (SELECT old_status, new_status, lag(new_status) OVER (PARTITION BY driver_id ORDER BY seq) AS prev
                       FROM driver_audit)
            SELECT count(*) FROM s WHERE old_status = 'available' AND new_status = 'assigned' AND prev = 'assigned'""")
        out["claims_audited"] = await conn.fetchval(
            "SELECT count(*) FROM driver_audit WHERE old_status = 'available' AND new_status = 'assigned'")
        out["transitions_audited"] = await conn.fetchval("SELECT count(*) FROM driver_audit")
        # Informational only (not a violation): statement wall-clock stamps can invert relative to commit order.
        out["wallclock_stamp_inversions_info"] = await conn.fetchval("""
            SELECT count(*) FROM (
              SELECT assigned_at, lag(coalesce(completed_at, cancelled_at, 'infinity'))
                     OVER (PARTITION BY driver_id ORDER BY assigned_at) AS prev_end
              FROM rides WHERE driver_id IS NOT NULL) x WHERE prev_end > assigned_at""")
        out["rides_total"] = await conn.fetchval("SELECT count(*) FROM rides")
        out["rides_assigned_ever"] = await conn.fetchval("SELECT count(*) FROM rides WHERE driver_id IS NOT NULL")
        out["rides_completed"] = await conn.fetchval("SELECT count(*) FROM rides WHERE status = 'completed'")
        out["pg_version"] = (await conn.fetchval("SELECT version()")).split(",")[0]
        return out
    finally:
        await conn.close()


VIOLATION_KEYS = ("claims_without_prior_release", "non_linear_driver_histories", "drivers_with_multiple_active_rides",
                  "capacity_violations", "vehicle_type_violations", "driver_ride_state_mismatches")


def to_markdown(rep: dict) -> str:
    env = rep["env"]
    L = ["# Matching load test (simulated traffic)", "",
         f"Environment: {env['where']}; host {env['host_cpu']} ({env['cores']} logical cores). "
         f"{rep['runs'][0]['invariants']['pg_version']}. API: {rep['config']['api']}. "
         f"Load generator: {rep['config']['client_processes']} client processes on the same machine.", "",
         f"Setup: {rep['config']['drivers']} drivers, {rep['config']['riders']} riders, "
         f"~{rep['config']['location_updates_per_s']:.0f} driver location updates/s in the background, "
         "assigned rides completed after 1-3 s (start + complete calls). `synchronous_commit=on`.", "",
         "| Target rate | Requests | Achieved | Success | Matched | p50 | p95 | p99 | max | Server match p50/p95 (≤) | WS fan-out p50/p95 | Invariant violations |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["runs"]:
        lat, sm, inv = r["latency_ms"], r["server_match_histogram"], r["invariants"]
        viol = sum(inv.get(k) or 0 for k in VIOLATION_KEYS)
        L.append(f"| {r['target_rate_rps']:.0f}/s | {r['requests']:,} | {r['achieved_throughput_rps']}/s | {r['success_rate']:.2%} | "
                 f"{r['matched_rate']:.1%} | {lat['p50']} ms | {lat['p95']} ms | {lat['p99']} ms | {lat['max']} ms | "
                 f"{sm.get('p50_le_ms', '-')} / {sm.get('p95_le_ms', '-')} ms | "
                 f"{r['ws_fanout_ms']['p50']} / {r['ws_fanout_ms']['p95']} ms | {viol} |")
    L += ["", "Latency = client-observed `POST /rides` round trip: validation, insert, spatial KNN match, atomic claim "
          "and NOTIFY in one statement, then the response. Server match = Prometheus histogram of the create+match "
          "statement for matched rides (bucket upper bounds).", "",
          "## Correctness invariants (checked in SQL after each run)", ""]
    for r in rep["runs"]:
        inv = r["invariants"]
        L.append(f"- {r['target_rate_rps']:.0f}/s: " + ", ".join(f"{k.replace('_', ' ')} = **{inv.get(k)}**" for k in VIOLATION_KEYS)
                 + f"; transitions audited {inv.get('transitions_audited', 0):,}, claims {inv.get('claims_audited', 0):,}, "
                 f"rides completed {inv['rides_completed']:,}")
    L += ["", "Double-booking is checked against the **true modification order**: an audit trigger on `drivers` "
          "draws a global sequence number while holding the row lock, so per-driver sequence order is exact. Every "
          "history must be linear (each transition's OLD = previous NEW) and every claim must follow a release. "
          "Wall-clock and commit timestamps are *not* used: under concurrent commits neither is a total order "
          "(both produced false positives during development; see docs/design.md). The partial unique index "
          "`rides_one_active_per_driver` independently makes a double assignment impossible to commit."]
    return "\n".join(L) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--requests", type=int, default=10_000)
    ap.add_argument("--rate", type=float, default=300)
    ap.add_argument("--sweep", type=float, nargs="*")
    ap.add_argument("--drivers", type=int, default=1000)
    ap.add_argument("--riders", type=int, default=2000)
    ap.add_argument("--location-rate", type=float, default=200)
    ap.add_argument("--client-procs", type=int, default=4)
    ap.add_argument("--api-desc", default=os.getenv("API_DESC", "uvicorn"))
    ap.add_argument("--where", default=os.getenv("LOADTEST_WHERE", "local"))
    ap.add_argument("--create-db-only", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    dsn = load_dsn()
    if args.create_db_only:
        await ensure_db(dsn)
        return
    REPORTS.mkdir(parents=True, exist_ok=True)
    await wait_ready(args.base_url)
    runs = []
    for i, rate in enumerate(args.sweep or [args.rate]):
        await prepare_db(dsn, args.drivers, args.riders, args.seed + i)
        await asyncio.sleep(1.5)  # let dispatcher loops observe the reset
        print(f"-> rate {rate}/s, {args.requests} requests", flush=True)
        res = await run_once(args.base_url, args, rate, args.seed + i)
        res["invariants"] = await invariants(dsn)
        print(json.dumps(res), flush=True)
        runs.append(res)

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "data": "SIMULATED requests and drivers",
        "env": {"where": args.where, "host_cpu": os.getenv("HOST_CPU", platform.processor() or platform.machine()),
                "cores": os.cpu_count(), "python": platform.python_version()},
        "config": {"drivers": args.drivers, "riders": args.riders, "api": args.api_desc,
                   "client_processes": args.client_procs, "location_updates_per_s": args.location_rate},
        "runs": runs,
    }
    name = "sweep" if args.sweep else f"run_{args.requests}_{int(args.rate)}"
    name += f"_{args.tag}" if args.tag else ""
    (REPORTS / f"loadtest_{name}.json").write_text(json.dumps(report, indent=2))
    (REPORTS / f"loadtest_{name}.md").write_text(to_markdown(report), encoding="utf-8")
    print(to_markdown(report))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
