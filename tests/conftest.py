import os
import re

import asyncpg
import pytest

BASE = os.getenv("DATABASE_URL", "postgresql://campusride:campusride@localhost:5433/campusride")
TEST_DSN = os.getenv("TEST_DATABASE_URL") or re.sub(r"/[^/]+$", "/campusride_test", BASE)


async def _ensure_db() -> bool:
    try:
        admin = await asyncpg.connect(re.sub(r"/[^/]+$", "/postgres", TEST_DSN), timeout=3)
    except (TimeoutError, OSError, asyncpg.PostgresError):
        return False
    name = TEST_DSN.rsplit("/", 1)[1]
    if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
        await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    return True


@pytest.fixture(scope="session")
async def db_dsn():
    if not await _ensure_db():
        pytest.skip("PostGIS not reachable; start it with `docker compose up -d db`")
    return TEST_DSN


@pytest.fixture
async def pool(db_dsn):
    from campusride.db import apply_schema, create_pool, reset_operational_data

    p = await create_pool(db_dsn, 2, 40)
    async with p.acquire() as conn:
        await apply_schema(conn)
        await reset_operational_data(conn)
    yield p
    await p.close()
