"""WebSocket fan-out over Postgres LISTEN/NOTIFY, with batched publishing.

Domain code publishes an event only after its transaction commits (`campusride.events`). Each worker's
`NotifyPublisher` coalesces events for a few milliseconds and sends each batch as a single NOTIFY
(a JSON array, chunked under the 8 kB payload limit). Every worker holds one LISTEN connection and fans
events out to its own sockets, so this works across uvicorn workers without a separate broker.

Batching matters because Postgres serializes the commit of every NOTIFY-ing transaction on one
database-wide lock held through the WAL flush. One NOTIFY per ride write capped throughput at ~85 rides/s.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import asyncpg
from fastapi import WebSocket

from campusride.observability import WS_CONNECTIONS, get_logger

log = get_logger(__name__)


class Hub:
    def __init__(self) -> None:
        self.by_ride: dict[int, set[WebSocket]] = defaultdict(set)
        self.by_driver: dict[int, set[WebSocket]] = defaultdict(set)
        self.live: set[WebSocket] = set()
        self._listen_conn: asyncpg.Connection | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self, dsn: str) -> None:
        self._loop = asyncio.get_running_loop()
        self._listen_conn = await asyncpg.connect(dsn)
        await self._listen_conn.add_listener("ride_events", self._on_notify)

    async def stop(self) -> None:
        if self._listen_conn is not None:
            await self._listen_conn.close()

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        data = json.loads(payload)
        for event in data if isinstance(data, list) else [data]:
            self._loop.create_task(self.dispatch(event))

    async def dispatch(self, event: dict) -> None:
        msg = {"type": "ride_event", **event}
        targets = set(self.by_ride.get(event.get("ride_id"), ()))
        if event.get("driver_id") is not None:
            targets |= self.by_driver.get(event["driver_id"], set())
        targets |= self.live
        await asyncio.gather(*(self._send(ws, msg) for ws in targets), return_exceptions=True)

    async def _send(self, ws: WebSocket, msg: dict) -> None:
        try:
            await ws.send_json(msg)
        except Exception:  # client went away; the handler's finally block unregisters it
            pass

    # registration helpers -------------------------------------------------

    def add(self, kind: str, key: int | None, ws: WebSocket) -> None:
        {"ride": lambda: self.by_ride[key].add(ws), "driver": lambda: self.by_driver[key].add(ws),
         "live": lambda: self.live.add(ws)}[kind]()
        WS_CONNECTIONS.labels(kind).inc()

    def remove(self, kind: str, key: int | None, ws: WebSocket) -> None:
        if kind == "ride":
            self.by_ride[key].discard(ws)
            if not self.by_ride[key]:
                del self.by_ride[key]
        elif kind == "driver":
            self.by_driver[key].discard(ws)
            if not self.by_driver[key]:
                del self.by_driver[key]
        else:
            self.live.discard(ws)
        WS_CONNECTIONS.labels(kind).dec()

    async def broadcast_live(self, msg: dict) -> None:
        await asyncio.gather(*(self._send(ws, msg) for ws in list(self.live)), return_exceptions=True)


class NotifyPublisher:
    """Coalesce post-commit events and publish each batch with one NOTIFY."""

    MAX_PAYLOAD = 7900  # Postgres limit is 8000 bytes

    def __init__(self, pool: asyncpg.Pool, window_s: float = 0.005):
        self.pool = pool
        self.window_s = window_s
        self._queue: list[dict] = []
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def publish(self, event: dict) -> None:
        self._queue.append(event)
        self._wake.set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self._flush()

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            await asyncio.sleep(self.window_s)
            try:
                await self._flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("notify_flush_failed")

    async def _flush(self) -> None:
        events, self._queue = self._queue, []
        chunks, cur, size = [], [], 2
        for e in events:
            js = json.dumps(e)
            if cur and size + len(js) + 1 > self.MAX_PAYLOAD:
                chunks.append(cur)
                cur, size = [], 2
            cur.append(js)
            size += len(js) + 1
        if cur:
            chunks.append(cur)
        if not chunks:
            return
        async with self.pool.acquire() as conn:
            for c in chunks:
                await conn.execute("SELECT pg_notify('ride_events', $1)", "[" + ",".join(c) + "]")
