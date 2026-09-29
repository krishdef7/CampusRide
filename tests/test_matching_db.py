"""Matching correctness against real PostGIS, including under heavy concurrency."""

import asyncio
from datetime import timedelta

import pytest

from campusride import campus, services
from campusride.config import Settings, now_ist
from campusride.services import DomainError

pytestmark = pytest.mark.db
S = Settings(match_radius_tiers_m=[1500, 4000])


async def add_driver(pool, vt, place, dlat=0.0):
    p = campus.PLACES[place]
    async with pool.acquire() as c:
        return await services.create_driver(c, f"{vt}@{place}", vt, p.lat + dlat, p.lon)


async def rider(pool):
    async with pool.acquire() as c:
        return await services.create_rider(c, "t")


async def test_nearest_eligible_driver_wins(pool):
    near = await add_driver(pool, "e_rickshaw", "rajendra")
    await add_driver(pool, "e_rickshaw", "main_gate")
    ride, m = await services.create_ride(pool, S, rider_id=await rider(pool), pickup_place_id="rajendra",
                                         dropoff_place_id="lhc")
    assert ride["status"] == "assigned" and m.driver_id == near


async def test_capacity_and_vehicle_constraints(pool):
    await add_driver(pool, "e_rickshaw", "sac")  # 4 seats, right there
    cab = await add_driver(pool, "cab", "mac")  # 6 seats, a bit further
    r = await rider(pool)
    _, m = await services.create_ride(pool, S, rider_id=r, pickup_place_id="sac", dropoff_place_id="lhc", passengers=5)
    assert m.driver_id == cab
    ride, m2 = await services.create_ride(pool, S, rider_id=r, pickup_place_id="sac", dropoff_place_id="lhc",
                                          vehicle_type="auto")
    assert m2 is None and ride["status"] == "searching"  # no auto exists: wait, don't substitute


async def test_seat_waste_penalty_prefers_right_sized_vehicle(pool):
    await add_driver(pool, "cab", "rajendra")  # closest, but 6 seats
    small = await add_driver(pool, "e_rickshaw", "rajendra", dlat=0.0004)  # ~45 m further
    _, m = await services.create_ride(pool, S, rider_id=await rider(pool), pickup_place_id="rajendra",
                                      dropoff_place_id="lhc", passengers=1)
    assert m.driver_id == small


async def test_scheduled_rides_are_not_matched_early(pool):
    await add_driver(pool, "auto", "lhc")
    ride, m = await services.create_ride(pool, S, rider_id=await rider(pool), pickup_place_id="lhc",
                                         dropoff_place_id="sac", pickup_at=now_ist() + timedelta(hours=3))
    assert ride["status"] == "scheduled" and m is None


async def test_idempotency_key(pool):
    await add_driver(pool, "auto", "lhc")
    r = await rider(pool)
    a, _ = await services.create_ride(pool, S, rider_id=r, pickup_place_id="lhc", dropoff_place_id="sac", idempotency_key="k1")
    b, _ = await services.create_ride(pool, S, rider_id=r, pickup_place_id="lhc", dropoff_place_id="sac", idempotency_key="k1")
    assert a["id"] == b["id"]


async def test_cancel_releases_driver(pool):
    d = await add_driver(pool, "auto", "lhc")
    r = await rider(pool)
    ride, _ = await services.create_ride(pool, S, rider_id=r, pickup_place_id="lhc", dropoff_place_id="sac")
    async with pool.acquire() as c:
        await services.cancel_ride(c, ride["id"], r)
        assert await c.fetchval("SELECT status FROM drivers WHERE id = $1", d) == "available"
        with pytest.raises(DomainError):
            await services.cancel_ride(c, ride["id"], r)


async def test_full_lifecycle(pool):
    d = await add_driver(pool, "cab", "ganga")
    ride, _ = await services.create_ride(pool, S, rider_id=await rider(pool), pickup_place_id="ganga", dropoff_place_id="railway_station")
    async with pool.acquire() as c:
        assert (await services.start_ride(c, d, ride["id"]))["status"] == "in_progress"
        assert (await services.complete_ride(c, d, ride["id"]))["status"] == "completed"
        with pytest.raises(DomainError):
            await services.complete_ride(c, d, ride["id"])
        assert await c.fetchval("SELECT status FROM drivers WHERE id = $1", d) == "available"


async def test_no_double_assignment_under_concurrency(pool):
    """200 simultaneous requests race for 50 drivers: exactly 50 matches, no driver twice."""
    places = list(campus.PLACES)
    for i in range(50):
        await add_driver(pool, "cab", places[i % len(places)])
    r = await rider(pool)
    results = await asyncio.gather(*[
        services.create_ride(pool, S, rider_id=r, pickup_place_id=places[i % len(places)],
                             dropoff_place_id=places[(i + 1) % len(places)])
        for i in range(200)
    ])
    matched = [m.driver_id for _, m in results if m is not None]
    assert len(matched) == len(set(matched)) == 50
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM rides WHERE status = 'assigned'") == 50
        assert await c.fetchval("SELECT count(*) FROM drivers WHERE status = 'assigned'") == 50
