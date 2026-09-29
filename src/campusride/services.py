"""Ride / driver domain operations over Postgres. Used by the HTTP API and by the agent's tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import asyncpg

from campusride import campus, events
from campusride.config import Settings, now_ist
from campusride.matching import MatchResult, RideSpec, create_and_match
from campusride.observability import RIDE_TRANSITIONS, RIDES_CREATED, span

ACTIVE_STATUSES = ("scheduled", "searching", "assigned", "in_progress")


class DomainError(Exception):
    """A request that is well-formed but violates a business rule (maps to HTTP 409/422)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Point:
    lat: float
    lon: float


def place_point(place_id: str) -> Point:
    p = campus.PLACES.get(place_id)
    if p is None:
        raise DomainError("unknown_place", f"unknown place {place_id!r}")
    return Point(p.lat, p.lon)


_RIDE_COLS = """
    r.id, r.rider_id, r.driver_id, r.status, r.pickup_place_id, r.dropoff_place_id, r.passengers,
    r.vehicle_type, r.pickup_at, r.requested_at, r.assigned_at, r.completed_at, r.cancelled_at,
    ST_Y(r.pickup::geometry) AS pickup_lat, ST_X(r.pickup::geometry) AS pickup_lon,
    ST_Y(r.dropoff::geometry) AS dropoff_lat, ST_X(r.dropoff::geometry) AS dropoff_lon,
    d.name AS driver_name, d.vehicle_type AS driver_vehicle_type,
    ST_Y(d.location::geometry) AS driver_lat, ST_X(d.location::geometry) AS driver_lon
"""


def ride_to_dict(row: asyncpg.Record) -> dict:
    out = dict(row)
    for k in ("pickup_at", "requested_at", "assigned_at", "completed_at", "cancelled_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    return out


# ------------------------------------------------------------------ riders


async def create_rider(conn: asyncpg.Connection, name: str) -> int:
    return await conn.fetchval("INSERT INTO riders (name) VALUES ($1) RETURNING id", name)


# ------------------------------------------------------------------ rides


async def create_ride(
    pool: asyncpg.Pool,
    settings: Settings,
    *,
    rider_id: int,
    pickup_place_id: str | None = None,
    dropoff_place_id: str | None = None,
    pickup: Point | None = None,
    dropoff: Point | None = None,
    passengers: int = 1,
    vehicle_type: str | None = None,
    pickup_at: datetime | None = None,
    idempotency_key: str | None = None,
    source: str = "api",
    now: datetime | None = None,
) -> tuple[dict, MatchResult | None]:
    """Create a ride. ASAP rides are matched inline so the response already carries the driver."""
    now = now or now_ist()
    if pickup_place_id:
        pickup = place_point(pickup_place_id)
    if dropoff_place_id:
        dropoff = place_point(dropoff_place_id)
    if pickup is None or dropoff is None:
        raise DomainError("missing_location", "pickup and dropoff are required")
    if pickup_place_id and pickup_place_id == dropoff_place_id:
        raise DomainError("same_place", "pickup and dropoff are the same place")
    if not 1 <= passengers <= campus.MAX_PASSENGERS:
        raise DomainError("passengers", f"passengers must be between 1 and {campus.MAX_PASSENGERS}")
    if vehicle_type and passengers > campus.CAPACITY[vehicle_type]:
        raise DomainError("capacity", f"a {vehicle_type} seats at most {campus.CAPACITY[vehicle_type]}")
    pickup_at = pickup_at or now
    if pickup_at < now - timedelta(minutes=1):
        raise DomainError("past_time", "pickup time is in the past")
    if pickup_at > now + timedelta(days=7):
        raise DomainError("too_far_ahead", "rides can be booked at most 7 days ahead")

    scheduled = pickup_at > now + timedelta(minutes=settings.schedule_lookahead_min)

    with span("create_ride", **{"ride.scheduled": scheduled, "ride.passengers": passengers}):
        async with pool.acquire() as conn:
            if idempotency_key:
                existing = await conn.fetchval(
                    "SELECT id FROM rides WHERE rider_id = $1 AND idempotency_key = $2", rider_id, idempotency_key
                )
                if existing:
                    return await get_ride(conn, existing), None
            spec = RideSpec(pickup.lat, pickup.lon, passengers, vehicle_type)
            match = None
            try:
                if scheduled:
                    ride_id = await conn.fetchval(
                        """
                        INSERT INTO rides (rider_id, status, pickup_place_id, dropoff_place_id, pickup, dropoff,
                                           passengers, vehicle_type, pickup_at, idempotency_key, source)
                        VALUES ($1, 'scheduled', $2, $3,
                                ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography,
                                ST_SetSRID(ST_MakePoint($7, $6), 4326)::geography,
                                $8, $9, $10, $11, $12)
                        RETURNING id
                        """,
                        rider_id, pickup_place_id, dropoff_place_id, pickup.lat, pickup.lon,
                        dropoff.lat, dropoff.lon, passengers, vehicle_type, pickup_at, idempotency_key, source,
                    )
                else:  # hot path: insert + match in one statement / one commit
                    ride_id, match = await create_and_match(
                        conn, settings, rider_id=rider_id, spec=spec, pickup_place_id=pickup_place_id,
                        dropoff_place_id=dropoff_place_id, dropoff_lat=dropoff.lat, dropoff_lon=dropoff.lon,
                        pickup_at=pickup_at, idempotency_key=idempotency_key, source=source,
                    )
            except asyncpg.UniqueViolationError:  # idempotency race: two identical requests at once
                ride_id = await conn.fetchval(
                    "SELECT id FROM rides WHERE rider_id = $1 AND idempotency_key = $2", rider_id, idempotency_key
                )
                return await get_ride(conn, ride_id), None
            except asyncpg.ForeignKeyViolationError as e:
                raise DomainError("unknown_rider", "rider does not exist") from e
            RIDES_CREATED.labels("scheduled" if scheduled else "asap", source).inc()
            return await get_ride(conn, ride_id), match


async def get_ride(conn: asyncpg.Connection, ride_id: int) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_RIDE_COLS} FROM rides r LEFT JOIN drivers d ON d.id = r.driver_id WHERE r.id = $1", ride_id
    )
    if row is None:
        raise DomainError("not_found", f"ride {ride_id} not found")
    return ride_to_dict(row)


async def latest_active_ride(conn: asyncpg.Connection, rider_id: int) -> int | None:
    return await conn.fetchval(
        "SELECT id FROM rides WHERE rider_id = $1 AND status = ANY($2::text[]) ORDER BY requested_at DESC LIMIT 1",
        rider_id,
        list(ACTIVE_STATUSES),
    )


async def latest_ride(conn: asyncpg.Connection, rider_id: int) -> int | None:
    return await conn.fetchval(
        "SELECT id FROM rides WHERE rider_id = $1 ORDER BY requested_at DESC LIMIT 1", rider_id
    )


async def cancel_ride(conn: asyncpg.Connection, ride_id: int, rider_id: int | None = None) -> dict:
    async with conn.transaction():
        row = await conn.fetchrow("SELECT rider_id, status, driver_id FROM rides WHERE id = $1 FOR UPDATE", ride_id)
        if row is None:
            raise DomainError("not_found", f"ride {ride_id} not found")
        if rider_id is not None and row["rider_id"] != rider_id:
            raise DomainError("forbidden", "that ride belongs to someone else")
        if row["status"] not in ("scheduled", "searching", "assigned"):
            raise DomainError("not_cancellable", f"ride is {row['status']} and can't be cancelled")
        await conn.execute("UPDATE rides SET status = 'cancelled', cancelled_at = clock_timestamp() WHERE id = $1", ride_id)
        if row["driver_id"]:
            await conn.execute(
                "UPDATE drivers SET status = 'available', current_ride_id = NULL WHERE id = $1 AND current_ride_id = $2",
                row["driver_id"], ride_id,
            )
    events.publish(ride_id, "cancelled", row["driver_id"])
    RIDE_TRANSITIONS.labels("cancelled").inc()
    return await get_ride(conn, ride_id)


async def quote(
    conn: asyncpg.Connection, settings: Settings, *, pickup_place_id: str, dropoff_place_id: str,
    passengers: int = 1, vehicle_type: str | None = None,
) -> dict:
    """Read-only availability + ETA + fare estimate. Never claims a driver."""
    p = place_point(pickup_place_id)
    rows = await conn.fetch(
        """
        SELECT vehicle_type, count(*) AS n, min(ST_Distance(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography)) AS nearest_m
        FROM drivers
        WHERE status = 'available' AND last_seen > now() - make_interval(secs => $5)
          AND capacity >= $3 AND ($4::text IS NULL OR vehicle_type = $4)
          AND ST_DWithin(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $6)
        GROUP BY vehicle_type
        """,
        p.lat, p.lon, passengers, vehicle_type, float(settings.driver_stale_after_s),
        float(max(settings.match_radius_tiers_m)),
    )
    trip_m = campus.place_distance_m(pickup_place_id, dropoff_place_id)
    options = [
        {
            "vehicle_type": r["vehicle_type"],
            "available_drivers": r["n"],
            "pickup_eta_min": round(campus.eta_seconds(r["nearest_m"], r["vehicle_type"]) / 60, 1),
            "trip_min": round(campus.eta_seconds(trip_m, r["vehicle_type"]) / 60, 1),
            "fare_inr": campus.fare_inr(trip_m, r["vehicle_type"]),
        }
        for r in sorted(rows, key=lambda r: r["nearest_m"])
    ]
    return {"pickup_place_id": pickup_place_id, "dropoff_place_id": dropoff_place_id, "passengers": passengers, "options": options}


# ------------------------------------------------------------------ drivers


async def create_driver(conn: asyncpg.Connection, name: str, vehicle_type: str, lat: float | None, lon: float | None) -> int:
    if vehicle_type not in campus.CAPACITY:
        raise DomainError("vehicle_type", f"unknown vehicle type {vehicle_type}")
    return await conn.fetchval(
        """
        INSERT INTO drivers (name, vehicle_type, capacity, status, location, last_seen)
        VALUES ($1, $2, $3, CASE WHEN $4::float8 IS NULL THEN 'offline' ELSE 'available' END,
                CASE WHEN $4::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography END,
                now())
        RETURNING id
        """,
        name, vehicle_type, campus.CAPACITY[vehicle_type], lat, lon,
    )


async def update_driver_location(conn: asyncpg.Connection, driver_id: int, lat: float, lon: float) -> None:
    await conn.execute(
        "UPDATE drivers SET location = ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, last_seen = now() WHERE id = $1",
        driver_id, lat, lon,
    )


async def set_driver_online(conn: asyncpg.Connection, driver_id: int, online: bool) -> None:
    res = await conn.execute(
        """
        UPDATE drivers SET status = CASE WHEN $2 THEN 'available' ELSE 'offline' END, last_seen = now()
        WHERE id = $1 AND status IN ('offline', 'available')
        """,
        driver_id, online,
    )
    if res.endswith(" 0"):
        raise DomainError("driver_busy", "driver not found or currently on a ride")


async def start_ride(conn: asyncpg.Connection, driver_id: int, ride_id: int) -> dict:
    return await _driver_transition(conn, driver_id, ride_id, "assigned", "in_progress", "on_trip")


async def complete_ride(conn: asyncpg.Connection, driver_id: int, ride_id: int) -> dict:
    return await _driver_transition(conn, driver_id, ride_id, "in_progress", "completed", "available")


async def _driver_transition(conn, driver_id: int, ride_id: int, from_s: str, to_s: str, driver_status: str) -> dict:
    async with conn.transaction():
        res = await conn.execute(
            f"UPDATE rides SET status = $3 {', completed_at = clock_timestamp()' if to_s == 'completed' else ''} "
            "WHERE id = $1 AND driver_id = $2 AND status = $4",
            ride_id, driver_id, to_s, from_s,
        )
        if res.endswith(" 0"):
            raise DomainError("bad_transition", f"ride {ride_id} is not {from_s} for driver {driver_id}")
        # Guarded: only touch the driver if it is still serving *this* ride.
        res = await conn.execute(
            "UPDATE drivers SET status = $2, current_ride_id = CASE WHEN $2 = 'available' THEN NULL ELSE current_ride_id END, "
            "last_seen = now() WHERE id = $1 AND current_ride_id = $3",
            driver_id, driver_status, ride_id,
        )
        if res.endswith(" 0"):
            raise DomainError("driver_state", f"driver {driver_id} is not serving ride {ride_id}")
    events.publish(ride_id, to_s, driver_id)
    RIDE_TRANSITIONS.labels(to_s).inc()
    return await get_ride(conn, ride_id)


async def expire_stale(conn: asyncpg.Connection, max_wait_min: int = 15) -> int:
    rows = await conn.fetch(
        """
        UPDATE rides SET status = 'expired'
        WHERE status = 'searching' AND pickup_at < now() - make_interval(mins => $1)
        RETURNING id
        """,
        max_wait_min,
    )
    for r in rows:
        events.publish(r["id"], "expired")
    return len(rows)
