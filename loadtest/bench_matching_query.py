"""Matching-query benchmark: the production query vs. unoptimized alternatives, at several fleet sizes.

Variants (each claims one driver inside a transaction that is rolled back, so every iteration sees
identical state):

    knn_partial_gist   production: KNN (<->) top-K over a partial GiST index of available drivers
    radius_sort_gist   ST_DWithin + sort *every* driver in the radius by score (same index)
    knn_no_index       production SQL with the spatial index dropped (sequential scan)
    app_side_scan      fetch all available drivers, rank in Python (numpy haversine), conditional UPDATE

Scenarios: `campus` (drivers packed within ~2 km, where nearly everyone is inside the radius) and
`city` (drivers spread over ~20 x 20 km, so the radius filter is selective).

    python loadtest/bench_matching_query.py --sizes 1000 10000 100000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import asyncpg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusride import campus  # noqa: E402
from campusride.db import apply_schema, reset_operational_data  # noqa: E402
from campusride.matching import CLAIM_SQL, KNN_K  # noqa: E402

REPORTS = ROOT / "loadtest" / "reports"
BASE_DSN = os.getenv("DATABASE_URL", "postgresql://campusride:campusride@localhost:5433/campusride")
CENTER = (29.8660, 77.8960)

RADIUS_SORT_SQL = """
WITH ride AS (SELECT id FROM rides WHERE id = $1 AND status IN ('searching','scheduled') FOR UPDATE SKIP LOCKED),
best AS (
    SELECT d.id, ST_Distance(d.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography) AS dist_m
    FROM drivers d CROSS JOIN ride
    WHERE d.status = 'available' AND d.last_seen > now() - make_interval(secs => $5) AND d.capacity >= $4
      AND ($6::text IS NULL OR d.vehicle_type = $6) AND $8::int > 0  -- $8 (K) unused: no top-K bound here
      AND ST_DWithin(d.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, $7)
    ORDER BY ST_Distance(d.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography) + $9 * (d.capacity - $4)
    LIMIT 1 FOR UPDATE OF d SKIP LOCKED
),
claimed AS (UPDATE drivers d SET status = 'assigned', current_ride_id = $1 FROM best WHERE d.id = best.id RETURNING d.id)
UPDATE rides r SET status = 'assigned', driver_id = claimed.id, assigned_at = now() FROM claimed WHERE r.id = $1
RETURNING r.id, claimed.id AS driver_id
"""


async def setup(conn, n: int, scenario: str, seed: int) -> list[tuple]:
    await reset_operational_data(conn)
    spread = 0.012 if scenario == "campus" else 0.09  # degrees; ~1.3 km vs ~10 km std-dev
    await conn.execute(
        """
        INSERT INTO drivers (name, vehicle_type, capacity, status, location, last_seen)
        SELECT 'd' || g, vt, CASE vt WHEN 'e_rickshaw' THEN 4 WHEN 'auto' THEN 3 ELSE 6 END, st,
               ST_SetSRID(ST_MakePoint($3 + (random() - 0.5) * 2 * $4, $2 + (random() - 0.5) * 2 * $4), 4326)::geography,
               now() + interval '1 day'
        FROM (
            SELECT g,
                   (ARRAY['e_rickshaw','e_rickshaw','e_rickshaw','auto','cab'])[1 + floor(random() * 5)::int] AS vt,
                   (ARRAY['available','available','available','available','available',
                          'offline','offline','offline','on_trip','on_trip'])[1 + floor(random() * 10)::int] AS st
            FROM generate_series(1, $1) g
        ) x
        """, n, CENTER[0], CENTER[1], spread,
    )
    rider = await conn.fetchval("INSERT INTO riders (name) VALUES ('bench') RETURNING id")
    rng = np.random.default_rng(seed)
    places = list(campus.PLACES.values())
    rides = []
    for _i in range(1400):  # a fresh ride for every timed claim (4 variants x 320), no dead-version chains
        p = places[rng.integers(len(places))]
        q = places[(rng.integers(len(places) - 1) + 1 + places.index(p)) % len(places)]
        pax = int(rng.choice([1, 1, 1, 2, 3]))
        rid = await conn.fetchval(
            """INSERT INTO rides (rider_id, status, pickup_place_id, dropoff_place_id, pickup, dropoff, passengers, pickup_at)
               VALUES ($1, 'searching', $2, $3, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography,
                       ST_SetSRID(ST_MakePoint($7, $6), 4326)::geography, $8, now()) RETURNING id""",
            rider, p.id, q.id, p.lat, p.lon, q.lat, q.lon, pax)
        rides.append((rid, p.lat, p.lon, pax))
    await conn.execute("VACUUM ANALYZE drivers")
    return rides


async def app_side(conn, rid, lat, lon, pax, radius):
    rows = await conn.fetch(
        "SELECT id, capacity, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon FROM drivers "
        "WHERE status = 'available' AND capacity >= $1", pax)
    if not rows:
        return None
    arr = np.array([(r["lat"], r["lon"], r["capacity"]) for r in rows])
    la, lo = np.radians(arr[:, 0]), np.radians(arr[:, 1])
    a = np.sin((la - np.radians(lat)) / 2) ** 2 + np.cos(la) * np.cos(np.radians(lat)) * np.sin((lo - np.radians(lon)) / 2) ** 2
    dist = 2 * 6_371_000 * np.arcsin(np.sqrt(a))
    score = np.where(dist <= radius, dist + 150 * (arr[:, 2] - pax), np.inf)
    for idx in np.argsort(score)[:5]:
        if not np.isfinite(score[idx]):
            return None
        did = rows[int(idx)]["id"]
        if await conn.fetchval("UPDATE drivers SET status = 'assigned' WHERE id = $1 AND status = 'available' RETURNING id", did):
            await conn.execute("UPDATE rides SET status = 'assigned', driver_id = $2 WHERE id = $1", rid, did)
            return did
    return None


async def time_variant(conn, variant: str, rides, iters: int, radius: float, offset: int = 0) -> dict:
    await conn.execute("VACUUM ANALYZE drivers")
    await conn.execute("VACUUM ANALYZE rides")
    lat_ms, hits = [], 0
    for i in range(iters + 20):
        rid, lat, lon, pax = rides[(offset + i) % len(rides)]
        tr = conn.transaction()
        await tr.start()
        t0 = time.perf_counter()
        if variant == "app_side_scan":
            row = await app_side(conn, rid, lat, lon, pax, radius)
        else:
            sql = RADIUS_SORT_SQL if variant == "radius_sort_gist" else CLAIM_SQL
            row = await conn.fetchrow(sql, rid, lat, lon, pax, 1e7, None, radius, KNN_K, 150.0)
        dt = (time.perf_counter() - t0) * 1000
        await tr.rollback()
        if i >= 20:
            lat_ms.append(dt)
            hits += row is not None
    a = np.array(lat_ms)
    return {"p50_ms": round(float(np.percentile(a, 50)), 3), "p95_ms": round(float(np.percentile(a, 95)), 3),
            "mean_ms": round(float(a.mean()), 3), "matched": hits / iters}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 10_000, 100_000])
    ap.add_argument("--scenarios", nargs="+", default=["campus", "city"])
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--radius", type=float, default=1500)
    args = ap.parse_args()

    dsn = os.getenv("BENCH_DATABASE_URL") or re.sub(r"/[^/]+$", "/campusride_bench", BASE_DSN)
    admin = await asyncpg.connect(re.sub(r"/[^/]+$", "/postgres", dsn))
    if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dsn.rsplit("/", 1)[1]):
        await admin.execute(f'CREATE DATABASE "{dsn.rsplit("/", 1)[1]}"')
    await admin.close()
    conn = await asyncpg.connect(dsn)
    await apply_schema(conn)

    results, plan_text = [], ""
    for scenario in args.scenarios:
        for n in args.sizes:
            rides = await setup(conn, n, scenario, seed=n)
            in_radius = await conn.fetchval(
                "SELECT avg(c) FROM (SELECT (SELECT count(*) FROM drivers d WHERE d.status='available' AND "
                "ST_DWithin(d.location, r.pickup, $1)) c FROM rides r LIMIT 50) x", args.radius)
            row = {"scenario": scenario, "drivers": n, "avg_available_in_radius": round(float(in_radius), 1)}
            for k, v in enumerate(("knn_partial_gist", "radius_sort_gist", "app_side_scan")):
                row[v] = await time_variant(conn, v, rides, args.iters, args.radius, offset=k * (args.iters + 20))
            if scenario == "city" and n == max(args.sizes):
                rid, lat, lon, pax = rides[0]
                tr = conn.transaction()
                await tr.start()
                plan = await conn.fetch("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + CLAIM_SQL, rid, lat, lon, pax, 1e7, None,
                                        args.radius, KNN_K, 150.0)
                await tr.rollback()
                plan_text = "\n".join(r[0] for r in plan)
            await conn.execute("DROP INDEX drivers_available_location_gix")
            await conn.execute("ANALYZE drivers")
            row["knn_no_index"] = await time_variant(conn, "knn_no_index", rides, args.iters, args.radius, offset=3 * (args.iters + 20))
            await conn.execute("CREATE INDEX drivers_available_location_gix ON drivers USING gist (location) WHERE status = 'available'")
            results.append(row)
            print(json.dumps(row), flush=True)
    await conn.close()

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "matching_query_bench.json").write_text(json.dumps({"results": results, "plan": plan_text}, indent=2))
    variants = ["knn_partial_gist", "radius_sort_gist", "knn_no_index", "app_side_scan"]
    md = ["# Matching query benchmark (simulated drivers)", "",
          f"Single connection, {args.iters} claims per cell, each in a rolled-back transaction. "
          f"Radius {args.radius:.0f} m. 50% of drivers available. Latency = one DB round trip (p50 / p95 ms).", "",
          "| Scenario | Drivers | Avail. in radius | " + " | ".join(variants) + " |",
          "|---|---|---|" + "---|" * len(variants)]
    for r in results:
        md.append(f"| {r['scenario']} | {r['drivers']:,} | {r['avg_available_in_radius']:,.0f} | " +
                  " | ".join(f"{r[v]['p50_ms']:.2f} / {r[v]['p95_ms']:.2f}" for v in variants) + " |")
    md += ["", "Production query plan (city, largest fleet):", "", "```", plan_text, "```"]
    (REPORTS / "matching_query_bench.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
