-- Idempotent schema; applied at API startup and by scripts/init_db.py.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS places (
    id        text PRIMARY KEY,
    name      text NOT NULL,
    zone_id   text NOT NULL,
    location  geography(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS riders (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drivers (
    id               bigserial PRIMARY KEY,
    name             text NOT NULL,
    vehicle_type     text NOT NULL CHECK (vehicle_type IN ('e_rickshaw', 'auto', 'cab')),
    capacity         smallint NOT NULL CHECK (capacity BETWEEN 1 AND 8),
    status           text NOT NULL DEFAULT 'offline' CHECK (status IN ('offline', 'available', 'assigned', 'on_trip')),
    location         geography(Point, 4326),
    last_seen        timestamptz,
    current_ride_id  bigint
);

-- KNN / radius search over *available* drivers only: a small, hot partial index.
CREATE INDEX IF NOT EXISTS drivers_available_location_gix
    ON drivers USING gist (location) WHERE status = 'available';

CREATE TABLE IF NOT EXISTS rides (
    id               bigserial PRIMARY KEY,
    rider_id         bigint NOT NULL REFERENCES riders(id),
    driver_id        bigint REFERENCES drivers(id),
    status           text NOT NULL CHECK (status IN ('scheduled', 'searching', 'assigned', 'in_progress', 'completed', 'cancelled', 'expired')),
    pickup_place_id  text REFERENCES places(id),
    dropoff_place_id text REFERENCES places(id),
    pickup           geography(Point, 4326) NOT NULL,
    dropoff          geography(Point, 4326) NOT NULL,
    passengers       smallint NOT NULL CHECK (passengers BETWEEN 1 AND 6),
    vehicle_type     text CHECK (vehicle_type IN ('e_rickshaw', 'auto', 'cab')),
    pickup_at        timestamptz NOT NULL,
    requested_at     timestamptz NOT NULL DEFAULT now(),
    assigned_at      timestamptz,
    completed_at     timestamptz,
    cancelled_at     timestamptz,
    match_attempts   int NOT NULL DEFAULT 0,
    idempotency_key  text,
    source           text NOT NULL DEFAULT 'api',
    CHECK (pickup_place_id IS NULL OR pickup_place_id <> dropoff_place_id)
);

-- Correctness invariant enforced by the database, not by application code:
-- a driver can hold at most one active ride, no matter how many API workers race.
CREATE UNIQUE INDEX IF NOT EXISTS rides_one_active_per_driver
    ON rides (driver_id) WHERE status IN ('assigned', 'in_progress');
CREATE UNIQUE INDEX IF NOT EXISTS rides_idempotency
    ON rides (rider_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS rides_pending_idx ON rides (pickup_at) WHERE status IN ('scheduled', 'searching');
CREATE INDEX IF NOT EXISTS rides_rider_idx ON rides (rider_id, requested_at DESC);

CREATE TABLE IF NOT EXISTS zone_forecasts (
    zone_id        text NOT NULL,
    slot_start     timestamptz NOT NULL,
    yhat           double precision NOT NULL,
    model_version  text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (zone_id, slot_start, model_version)
);

-- Every agent turn is persisted: input, tool calls, validation failures, latency, tokens.
-- This is the raw material for mining new eval cases from real traffic.
CREATE TABLE IF NOT EXISTS agent_turns (
    id             bigserial PRIMARY KEY,
    session_id     text NOT NULL,
    rider_id       bigint,
    user_message   text NOT NULL,
    action         text,
    tool_args      jsonb,
    outcome        text,
    reply          text,
    repairs        int NOT NULL DEFAULT 0,
    llm_calls      int NOT NULL DEFAULT 0,
    input_tokens   int NOT NULL DEFAULT 0,
    output_tokens  int NOT NULL DEFAULT 0,
    latency_ms     double precision,
    model          text,
    trace_id       text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
