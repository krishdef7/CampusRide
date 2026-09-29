"""FastAPI application: REST + WebSockets + background dispatcher + /metrics."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Literal

import asyncpg
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from campusride import campus, events, services
from campusride.api.realtime import Hub, NotifyPublisher
from campusride.config import Settings, get_settings
from campusride.db import apply_schema, create_pool
from campusride.matching import match_ride
from campusride.observability import (
    DRIVER_LOCATION_UPDATES,
    HTTP_LATENCY,
    configure_logging,
    configure_tracing,
    get_logger,
)
from campusride.services import DomainError, Point

log = get_logger(__name__)
WEB_DIR = Path(__file__).resolve().parents[3] / "web"

VehicleType = Literal["e_rickshaw", "auto", "cab"]


# ------------------------------------------------------------------ request models

class RiderIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RideIn(BaseModel):
    rider_id: int
    pickup_place_id: str | None = None
    dropoff_place_id: str | None = None
    pickup: LatLon | None = None
    dropoff: LatLon | None = None
    passengers: int = Field(1, ge=1, le=campus.MAX_PASSENGERS)
    vehicle_type: VehicleType | None = None
    pickup_at: datetime | None = None
    idempotency_key: str | None = Field(None, max_length=128)


class CancelIn(BaseModel):
    rider_id: int | None = None


class DriverIn(BaseModel):
    name: str
    vehicle_type: VehicleType
    lat: float | None = None
    lon: float | None = None


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    rider_id: int
    message: str = Field(min_length=1, max_length=1000)


# ------------------------------------------------------------------ middleware

class MetricsMiddleware:
    """Pure-ASGI latency histogram keyed by route *template* (bounded label cardinality)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        status = {"code": 500}

        async def _send(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", "unmatched")
            if path != "/metrics":
                HTTP_LATENCY.labels(scope["method"], path, str(status["code"])).observe(time.perf_counter() - t0)


# ------------------------------------------------------------------ background loops

async def dispatcher_loop(app: FastAPI) -> None:
    """Promote due scheduled rides, retry unmatched ones, expire stale ones."""
    s: Settings = app.state.settings
    pool: asyncpg.Pool = app.state.pool
    while True:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE rides SET status = 'searching' WHERE status = 'scheduled' "
                    "AND pickup_at <= now() + make_interval(mins => $1)", s.schedule_lookahead_min,
                )
                pending = await conn.fetch(
                    "SELECT id FROM rides WHERE status = 'searching' AND pickup_at <= now() + make_interval(mins => $1) "
                    "ORDER BY pickup_at LIMIT 200", s.schedule_lookahead_min,
                )
                for r in pending:
                    if await match_ride(conn, r["id"], s) is None:
                        break  # nobody free for the oldest ride; don't hammer the DB for the rest this tick
                await services.expire_stale(conn)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dispatcher_tick_failed")
        await asyncio.sleep(s.dispatch_interval_s)


async def live_snapshot_loop(app: FastAPI) -> None:
    hub: Hub = app.state.hub
    while True:
        await asyncio.sleep(1.0)
        if not hub.live:
            continue
        try:
            async with app.state.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, status, vehicle_type, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
                    "FROM drivers WHERE status <> 'offline' AND location IS NOT NULL LIMIT 3000"
                )
            await hub.broadcast_live({"type": "drivers", "drivers": [dict(r) for r in rows]})
        except Exception:
            log.exception("live_snapshot_failed")


# ------------------------------------------------------------------ app factory

def create_app(settings: Settings | None = None, *, run_background: bool = True, agent=None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    configure_tracing(settings.service_name, settings.otel_exporter_otlp_endpoint)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.pool = await create_pool(settings.database_url, settings.db_pool_min, settings.db_pool_max)
        async with app.state.pool.acquire() as conn:
            await apply_schema(conn)
        app.state.hub = Hub()
        await app.state.hub.start(settings.database_url)
        app.state.publisher = NotifyPublisher(app.state.pool)
        app.state.publisher.start()
        events.set_publisher(app.state.publisher)
        app.state.agent = agent or _build_agent(app, settings)
        tasks = [asyncio.create_task(live_snapshot_loop(app))]
        if run_background:
            tasks.append(asyncio.create_task(dispatcher_loop(app)))
        log.info("startup_complete", agent=app.state.agent is not None)
        yield
        for t in tasks:
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t
        events.set_publisher(None)
        await app.state.publisher.stop()
        await app.state.hub.stop()
        await app.state.pool.close()

    app = FastAPI(title="CampusRide", version="0.1.0", lifespan=lifespan)
    app.add_middleware(MetricsMiddleware)
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,healthz")

    @app.exception_handler(DomainError)
    async def _domain_error(_, exc: DomainError):
        code = 404 if exc.code == "not_found" else 403 if exc.code == "forbidden" else 409
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=code)

    _routes(app)
    return app


def _build_agent(app: FastAPI, settings: Settings):
    """Return None (agent disabled, rest of the platform still runs) when no LLM is configured."""
    env_key = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(settings.llm_provider)
    if env_key is None or not (settings.llm_api_key or settings.llm_base_url or os.getenv(env_key)):
        return None
    from campusride.agent.backend import DbBackend
    from campusride.agent.graph import RideAgent
    from campusride.agent.llm import LLMClient
    from campusride.agent.schema import TOOLS

    async def record(session_id, rider_id, message, res):
        async with app.state.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO agent_turns (session_id, rider_id, user_message, action, tool_args, outcome, reply,
                   repairs, llm_calls, input_tokens, output_tokens, latency_ms, model, trace_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
                session_id, rider_id, message, res.action.name, res.raw_tool_calls, res.outcome, res.reply,
                res.repairs, res.llm_calls, res.input_tokens, res.output_tokens, res.latency_s * 1000,
                settings.llm_model, res.trace_id,
            )

    return RideAgent(LLMClient(settings, TOOLS), DbBackend(app.state.pool, settings), settings, recorder=record)


def _routes(app: FastAPI) -> None:
    def pool(): return app.state.pool  # noqa: E704

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/readyz")
    async def readyz():
        async with pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"ok": True}

    @app.get("/metrics")
    async def metrics():
        if os.getenv("PROMETHEUS_MULTIPROC_DIR"):  # several uvicorn workers: aggregate their metric files
            from prometheus_client import CollectorRegistry, multiprocess

            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/places")
    async def places():
        return [{"id": p.id, "name": p.name, "lat": p.lat, "lon": p.lon, "zone": p.zone} for p in campus.PLACES.values()]

    # riders & rides ---------------------------------------------------------

    @app.post("/riders", status_code=201)
    async def create_rider(body: RiderIn):
        async with pool().acquire() as conn:
            return {"id": await services.create_rider(conn, body.name)}

    @app.post("/rides", status_code=201)
    async def create_ride(body: RideIn):
        for pid in (body.pickup_place_id, body.dropoff_place_id):
            if pid is not None and pid not in campus.PLACES:
                raise HTTPException(422, f"unknown place {pid}")
        ride, match = await services.create_ride(
            pool(), app.state.settings, rider_id=body.rider_id,
            pickup_place_id=body.pickup_place_id, dropoff_place_id=body.dropoff_place_id,
            pickup=Point(body.pickup.lat, body.pickup.lon) if body.pickup else None,
            dropoff=Point(body.dropoff.lat, body.dropoff.lon) if body.dropoff else None,
            passengers=body.passengers, vehicle_type=body.vehicle_type, pickup_at=body.pickup_at,
            idempotency_key=body.idempotency_key,
        )
        return {**ride, "match": None if match is None else {"distance_m": round(match.distance_m, 1), "radius_m": match.radius_m}}

    @app.get("/rides/{ride_id}")
    async def get_ride(ride_id: int):
        async with pool().acquire() as conn:
            return await services.get_ride(conn, ride_id)

    @app.post("/rides/{ride_id}/cancel")
    async def cancel(ride_id: int, body: CancelIn):
        async with pool().acquire() as conn:
            return await services.cancel_ride(conn, ride_id, body.rider_id)

    @app.get("/quote")
    async def quote(pickup: str, dropoff: str, passengers: int = Query(1, ge=1, le=6), vehicle_type: VehicleType | None = None):
        if pickup not in campus.PLACES or dropoff not in campus.PLACES:
            raise HTTPException(422, "unknown place")
        async with pool().acquire() as conn:
            return await services.quote(conn, app.state.settings, pickup_place_id=pickup, dropoff_place_id=dropoff,
                                        passengers=passengers, vehicle_type=vehicle_type)

    # drivers ----------------------------------------------------------------

    @app.post("/drivers", status_code=201)
    async def create_driver(body: DriverIn):
        async with pool().acquire() as conn:
            return {"id": await services.create_driver(conn, body.name, body.vehicle_type, body.lat, body.lon)}

    @app.put("/drivers/{driver_id}/location", status_code=204)
    async def driver_location(driver_id: int, body: LatLon):
        async with pool().acquire() as conn:
            await services.update_driver_location(conn, driver_id, body.lat, body.lon)
        DRIVER_LOCATION_UPDATES.labels("http").inc()

    @app.post("/drivers/{driver_id}/online", status_code=204)
    async def driver_online(driver_id: int):
        async with pool().acquire() as conn:
            await services.set_driver_online(conn, driver_id, True)

    @app.post("/drivers/{driver_id}/offline", status_code=204)
    async def driver_offline(driver_id: int):
        async with pool().acquire() as conn:
            await services.set_driver_online(conn, driver_id, False)

    @app.post("/drivers/{driver_id}/rides/{ride_id}/start")
    async def start(driver_id: int, ride_id: int):
        async with pool().acquire() as conn:
            return await services.start_ride(conn, driver_id, ride_id)

    @app.post("/drivers/{driver_id}/rides/{ride_id}/complete")
    async def complete(driver_id: int, ride_id: int):
        async with pool().acquire() as conn:
            return await services.complete_ride(conn, driver_id, ride_id)

    # agent -------------------------------------------------------------------

    @app.post("/agent/chat")
    async def chat(body: ChatIn):
        agent = app.state.agent
        if agent is None:
            raise HTTPException(503, "LLM agent disabled: set LLM_PROVIDER / LLM_MODEL / LLM_API_KEY")
        try:
            res = await agent.run_turn(body.session_id, body.rider_id, body.message)
        except Exception as e:  # provider outage / quota: a clear 502 instead of an opaque 500
            log.warning("agent_turn_failed", error=f"{type(e).__name__}: {e}"[:300])
            raise HTTPException(502, "The language model is unavailable right now. Please try again.") from e
        return {
            "reply": res.reply, "action": res.action.as_label(), "outcome": res.outcome,
            "ride": res.result if res.action.name in ("book_ride", "cancel_ride", "get_ride_status") else None,
            "quote": res.result if res.action.name == "get_quote" else None,
            "latency_ms": round(res.latency_s * 1000, 1), "llm_calls": res.llm_calls, "repairs": res.repairs,
            "tokens": {"input": res.input_tokens, "output": res.output_tokens}, "trace_id": res.trace_id,
        }

    # forecasting / allocation ---------------------------------------------------

    @app.get("/forecast")
    async def forecast(start: datetime, hours: int = Query(3, ge=1, le=48)):
        async with pool().acquire() as conn:
            rows = await conn.fetch(
                "SELECT zone_id, slot_start, yhat, model_version FROM zone_forecasts "
                "WHERE slot_start >= $1 AND slot_start < $1 + make_interval(hours => $2) ORDER BY slot_start, zone_id",
                start, hours,
            )
        return [dict(r) for r in rows]

    @app.get("/allocation/recommendations")
    async def allocation(slot_start: datetime):
        from campusride.forecasting.allocation import recommend_moves

        async with pool().acquire() as conn:
            fc = await conn.fetch(
                "SELECT DISTINCT ON (zone_id) zone_id, yhat FROM zone_forecasts WHERE slot_start = $1 "
                "ORDER BY zone_id, created_at DESC", slot_start,
            )
            drivers = await conn.fetch(
                "SELECT id, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon FROM drivers "
                "WHERE status = 'available' AND location IS NOT NULL"
            )
        if not fc:
            raise HTTPException(404, "no forecast for that slot; run `python -m campusride.forecasting.publish`")
        moves = recommend_moves({r["zone_id"]: r["yhat"] for r in fc}, [(r["id"], r["lat"], r["lon"]) for r in drivers])
        return {"slot_start": slot_start, "forecast": {r["zone_id"]: round(r["yhat"], 2) for r in fc}, "moves": moves}

    # websockets ----------------------------------------------------------------

    @app.websocket("/ws/rides/{ride_id}")
    async def ws_ride(ws: WebSocket, ride_id: int):
        await ws.accept()
        hub: Hub = app.state.hub
        hub.add("ride", ride_id, ws)
        try:
            async with pool().acquire() as conn:
                await ws.send_json({"type": "snapshot", "ride": await services.get_ride(conn, ride_id)})
            while True:
                await ws.receive_text()  # keepalive / ignore
        except (WebSocketDisconnect, DomainError):
            pass
        finally:
            hub.remove("ride", ride_id, ws)

    @app.websocket("/ws/drivers/{driver_id}")
    async def ws_driver(ws: WebSocket, driver_id: int):
        """Drivers stream {"lat", "lon"} and receive ride assignment / cancellation events."""
        await ws.accept()
        hub: Hub = app.state.hub
        hub.add("driver", driver_id, ws)
        try:
            while True:
                msg = await ws.receive_json()
                if "lat" in msg and "lon" in msg:
                    async with pool().acquire() as conn:
                        await services.update_driver_location(conn, driver_id, float(msg["lat"]), float(msg["lon"]))
                    DRIVER_LOCATION_UPDATES.labels("ws").inc()
        except (WebSocketDisconnect, ValueError, KeyError):
            pass
        finally:
            hub.remove("driver", driver_id, ws)

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        hub: Hub = app.state.hub
        hub.add("live", None, ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove("live", None, ws)
