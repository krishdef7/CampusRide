"""Constraint-aware spatial matching with an atomic, race-free assignment.

Two single-statement operations, each one round trip, one implicit transaction and one WAL flush.
Events are published after commit via `campusride.events` (see there for why not in-transaction NOTIFY):

* `CREATE_AND_CLAIM_SQL` (hot path, new ASAP ride): pick and lock the best driver, claim it, insert
  the ride already assigned (or 'searching' if nobody qualifies). Creating
  and matching in one statement removes a commit, and on a durable database the fsync per commit is
  the dominant cost (measured: 2 commits ~9.4 ms -> 1 statement, see docs/design.md).
* `CLAIM_SQL` (existing ride: dispatcher retries, scheduled rides coming due): lock the ride row
  (SKIP LOCKED), claim a driver, assign.

Driver selection in both:
1. `knn`: the K nearest eligible drivers via an index-assisted KNN scan (`<->`) over a *partial* GiST
   index holding only available drivers. Eligibility: fresh heartbeat, enough seats, requested vehicle
   type, within the radius. Work is O(log n + K) however dense the fleet is.
2. `best`: re-rank those K by pickup distance plus a penalty for wasted seats (don't send a 6-seat cab to a
   solo rider when an e-rickshaw is nearly as close). Lock only the winner with `FOR UPDATE SKIP LOCKED`, so
   concurrent matchers take the next-best driver instead of queueing.

3. Claim with compare-and-set: the UPDATE re-checks `status = 'available'` itself. In READ COMMITTED an
   UPDATE re-evaluates its own WHERE clause against the latest committed row version, so a candidate that
   went stale between the KNN scan and the claim is simply not claimed. The row lock taken in `best` already
   ensures this; the predicate is defence in depth and costs nothing.

The partial unique index `rides_one_active_per_driver` is the backstop: a double assignment can't commit
even if this logic were wrong. Timestamps use clock_timestamp() (wall time at the write), not now()
(transaction start), so audit intervals are exact. `loadtest/bench_matching_query.py` compares the KNN
query with radius-sort, no-index and application-side variants.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from campusride import events
from campusride.config import Settings
from campusride.observability import MATCH_LATENCY, MATCH_OUTCOMES, RIDE_TRANSITIONS, span

KNN_K = 16

# $2 lat, $3 lon, $4 passengers, $5 stale-after secs, $6 vehicle type, $7 radius m, $8 K, $9 seat penalty m
_PICK = """
knn AS (
    SELECT id FROM drivers
    WHERE status = 'available'
      AND last_seen > now() - make_interval(secs => $5)
      AND capacity >= $4
      AND ($6::text IS NULL OR vehicle_type = $6)
      AND ST_DWithin(location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, $7)
    ORDER BY location <-> ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography
    LIMIT $8
),
best AS (
    SELECT d.id, ST_Distance(d.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography) AS dist_m
    FROM drivers d JOIN knn ON knn.id = d.id {extra_join}
    WHERE d.status = 'available'
    ORDER BY ST_Distance(d.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography) + $9 * (d.capacity - $4)
    LIMIT 1
    FOR UPDATE OF d SKIP LOCKED
)"""

CLAIM_SQL = f"""
WITH ride AS (
    SELECT id FROM rides WHERE id = $1 AND status IN ('searching', 'scheduled') FOR UPDATE SKIP LOCKED
),
{_PICK.format(extra_join="CROSS JOIN ride")},
claimed AS (
    UPDATE drivers d SET status = 'assigned', current_ride_id = $1
    FROM best WHERE d.id = best.id AND d.status = 'available'  -- compare-and-set, re-checked on the latest row version
    RETURNING d.id, d.name, d.vehicle_type, d.capacity, ST_Y(d.location::geometry) AS lat,
              ST_X(d.location::geometry) AS lon, best.dist_m
),
assigned AS (
    UPDATE rides r
    SET status = 'assigned', driver_id = claimed.id, assigned_at = clock_timestamp(), match_attempts = match_attempts + 1
    FROM claimed WHERE r.id = $1
    RETURNING r.id AS ride_id, claimed.id AS driver_id, claimed.name AS driver_name, claimed.vehicle_type,
              claimed.capacity, claimed.lat, claimed.lon, claimed.dist_m
)
SELECT a.*, 'assigned' AS status FROM assigned a
"""

# $1 rider, $10 pickup place, $11 dropoff place, $12/$13 dropoff lat/lon, $14 pickup_at, $15 idempotency key, $16 source
CREATE_AND_CLAIM_SQL = f"""
WITH new_ride AS (SELECT nextval(pg_get_serial_sequence('rides', 'id')) AS id),
{_PICK.format(extra_join="")},
claimed AS (
    UPDATE drivers d SET status = 'assigned', current_ride_id = (SELECT id FROM new_ride)
    FROM best WHERE d.id = best.id AND d.status = 'available'  -- compare-and-set, re-checked on the latest row version
    RETURNING d.id, d.name, d.vehicle_type, d.capacity, ST_Y(d.location::geometry) AS lat,
              ST_X(d.location::geometry) AS lon, best.dist_m
),
ins AS (
    INSERT INTO rides (id, rider_id, status, driver_id, pickup_place_id, dropoff_place_id, pickup, dropoff,
                       passengers, vehicle_type, pickup_at, requested_at, assigned_at, match_attempts,
                       idempotency_key, source)
    SELECT n.id, $1, CASE WHEN c.id IS NULL THEN 'searching' ELSE 'assigned' END, c.id, $10, $11,
           ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, ST_SetSRID(ST_MakePoint($13, $12), 4326)::geography,
           $4, $6, $14, clock_timestamp(), CASE WHEN c.id IS NULL THEN NULL ELSE clock_timestamp() END, 1, $15, $16
    FROM new_ride n LEFT JOIN claimed c ON true
    RETURNING id, status
)
SELECT ins.id AS ride_id, ins.status, c.id AS driver_id, c.name AS driver_name, c.vehicle_type, c.capacity,
       c.lat, c.lon, c.dist_m
FROM ins LEFT JOIN claimed c ON true
"""


@dataclass(frozen=True)
class RideSpec:
    lat: float
    lon: float
    passengers: int
    vehicle_type: str | None


@dataclass(frozen=True)
class MatchResult:
    ride_id: int
    driver_id: int
    driver_name: str
    vehicle_type: str
    capacity: int
    driver_lat: float
    driver_lon: float
    distance_m: float
    radius_m: int


def _result(row, radius: int) -> MatchResult:
    return MatchResult(ride_id=row["ride_id"], driver_id=row["driver_id"], driver_name=row["driver_name"],
                       vehicle_type=row["vehicle_type"], capacity=row["capacity"], driver_lat=row["lat"],
                       driver_lon=row["lon"], distance_m=row["dist_m"], radius_m=radius)


def _record(t0: float, matched: bool, ride_id: int | None = None, driver_id: int | None = None) -> None:
    outcome = "matched" if matched else "no_driver"
    MATCH_LATENCY.labels(outcome).observe(time.perf_counter() - t0)
    MATCH_OUTCOMES.labels(outcome).inc()
    if matched:
        RIDE_TRANSITIONS.labels("assigned").inc()
        events.publish(ride_id, "assigned", driver_id)  # statement already committed (autocommit)


def _pick_args(spec: RideSpec, settings: Settings, radius: int) -> tuple:
    return (spec.lat, spec.lon, spec.passengers, float(settings.driver_stale_after_s), spec.vehicle_type,
            float(radius), KNN_K, settings.match_capacity_waste_penalty_m)


async def _ride_spec(conn: asyncpg.Connection, ride_id: int) -> RideSpec | None:
    row = await conn.fetchrow(
        "SELECT ST_Y(pickup::geometry) AS lat, ST_X(pickup::geometry) AS lon, passengers, vehicle_type FROM rides WHERE id = $1",
        ride_id,
    )
    return RideSpec(row["lat"], row["lon"], row["passengers"], row["vehicle_type"]) if row else None


async def match_ride(conn: asyncpg.Connection, ride_id: int, settings: Settings, spec: RideSpec | None = None,
                     tiers: list[int] | None = None) -> MatchResult | None:
    """Try to assign a driver to an existing ride. Returns None when no eligible driver exists (it stays pending)."""
    t0 = time.perf_counter()
    with span("match_ride", **{"ride.id": ride_id}) as s:
        spec = spec or await _ride_spec(conn, ride_id)
        if spec is None:
            return None
        for radius in tiers or settings.match_radius_tiers_m:
            row = await conn.fetchrow(CLAIM_SQL, ride_id, *_pick_args(spec, settings, radius))
            if row is not None:
                _record(t0, True, ride_id, row["driver_id"])
                s.set_attribute("match.radius_m", radius)
                s.set_attribute("match.driver_id", row["driver_id"])
                return _result(row, radius)
        await conn.execute("UPDATE rides SET match_attempts = match_attempts + 1 WHERE id = $1", ride_id)
        _record(t0, False)
        s.set_attribute("match.outcome", "no_driver")
        return None


async def create_and_match(conn: asyncpg.Connection, settings: Settings, *, rider_id: int, spec: RideSpec,
                           pickup_place_id: str | None, dropoff_place_id: str | None, dropoff_lat: float,
                           dropoff_lon: float, pickup_at: datetime, idempotency_key: str | None,
                           source: str) -> tuple[int, MatchResult | None]:
    """Insert an ASAP ride and try to assign it in the same statement (first radius tier).
    Wider tiers, if any, fall back to `match_ride` on the now-existing ride."""
    t0 = time.perf_counter()
    first, *rest = settings.match_radius_tiers_m
    with span("create_and_match") as s:
        row = await conn.fetchrow(
            CREATE_AND_CLAIM_SQL, rider_id, *_pick_args(spec, settings, first), pickup_place_id, dropoff_place_id,
            dropoff_lat, dropoff_lon, pickup_at, idempotency_key, source,
        )
        ride_id = row["ride_id"]
        if row["driver_id"] is not None:
            _record(t0, True, ride_id, row["driver_id"])
            s.set_attribute("match.driver_id", row["driver_id"])
            return ride_id, _result(row, first)
    if rest:
        return ride_id, await match_ride(conn, ride_id, settings, spec, tiers=rest)
    _record(t0, False)
    return ride_id, None
