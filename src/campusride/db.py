"""asyncpg pool, schema bootstrap and gazetteer seeding."""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg

from campusride.campus import PLACES

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(dsn: str, min_size: int = 5, max_size: int = 20) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size, init=_init_conn, command_timeout=10)


async def apply_schema(conn: asyncpg.Connection) -> None:
    # Serialise concurrent bootstraps from several API workers.
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(424242)")
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        await conn.executemany(
            """
            INSERT INTO places (id, name, zone_id, location)
            VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, zone_id = EXCLUDED.zone_id, location = EXCLUDED.location
            """,
            [(p.id, p.name, p.zone, p.lat, p.lon) for p in PLACES.values()],
        )


async def reset_operational_data(conn: asyncpg.Connection) -> None:
    """Wipe rides/drivers/riders (used by load tests and evals, never by the API)."""
    await conn.execute("TRUNCATE rides, drivers, riders, agent_turns RESTART IDENTITY CASCADE")
