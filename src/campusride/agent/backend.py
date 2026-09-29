"""The agent's side-effecting tools, behind a small interface so tests can swap in a fake."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import asyncpg

from campusride import services
from campusride.agent.schema import Action
from campusride.config import Settings
from campusride.services import DomainError


class RideBackend(Protocol):
    async def book(self, rider_id: int, action: Action, idempotency_key: str, now: datetime) -> dict: ...
    async def quote(self, action: Action) -> dict: ...
    async def cancel(self, rider_id: int, ride_id: int | None) -> dict: ...
    async def status(self, rider_id: int, ride_id: int | None) -> dict: ...


class DbBackend:
    def __init__(self, pool: asyncpg.Pool, settings: Settings):
        self.pool = pool
        self.settings = settings

    async def book(self, rider_id, action, idempotency_key, now):
        ride, _ = await services.create_ride(
            self.pool, self.settings, rider_id=rider_id, pickup_place_id=action.pickup,
            dropoff_place_id=action.dropoff, passengers=action.passengers, vehicle_type=action.vehicle_type,
            pickup_at=action.pickup_at, idempotency_key=idempotency_key, source="agent", now=now,
        )
        return ride

    async def quote(self, action):
        async with self.pool.acquire() as conn:
            return await services.quote(
                conn, self.settings, pickup_place_id=action.pickup, dropoff_place_id=action.dropoff,
                passengers=action.passengers or 1, vehicle_type=action.vehicle_type,
            )

    async def _owned(self, conn, rider_id: int, ride_id: int | None, active_only: bool) -> int:
        if ride_id is None:
            ride_id = await (services.latest_active_ride(conn, rider_id) if active_only else services.latest_ride(conn, rider_id))
            if ride_id is None:
                raise DomainError("no_active_ride", "You don't have any active rides.")
            return ride_id
        owner = await conn.fetchval("SELECT rider_id FROM rides WHERE id = $1", ride_id)
        if owner is None:
            raise DomainError("not_found", f"I couldn't find ride #{ride_id}.")
        if owner != rider_id:
            raise DomainError("forbidden", f"Ride #{ride_id} isn't one of your rides.")
        return ride_id

    async def cancel(self, rider_id, ride_id):
        async with self.pool.acquire() as conn:
            rid = await self._owned(conn, rider_id, ride_id, active_only=True)
            return await services.cancel_ride(conn, rid, rider_id)

    async def status(self, rider_id, ride_id):
        async with self.pool.acquire() as conn:
            rid = await self._owned(conn, rider_id, ride_id, active_only=False)
            return await services.get_ride(conn, rid)
