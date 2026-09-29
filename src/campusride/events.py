"""Post-commit ride events.

Domain code calls `publish(...)` *after* its transaction commits. The API process installs a
publisher (api/realtime.py) that batches events into a few NOTIFYs. Without one installed (tests,
evals, scripts) events are dropped, which is harmless because clients also receive state snapshots.

Why not `pg_notify` inside the write transaction? Postgres serializes the commit of every
NOTIFY-ing transaction on a database-wide lock, held through the WAL flush. Measured here, that capped
ride creation at ~85 req/s with 78 sessions queued on `Lock: object`. Batching after commit restores
parallel (group) commits.
"""

from __future__ import annotations

import time
from typing import Protocol


class Publisher(Protocol):
    def publish(self, event: dict) -> None: ...


_publisher: Publisher | None = None


def set_publisher(p: Publisher | None) -> None:
    global _publisher
    _publisher = p


def publish(ride_id: int, status: str, driver_id: int | None = None, **extra) -> None:
    if _publisher is not None:
        # `ts` = commit time; clients use it to measure commit -> WebSocket fan-out latency.
        _publisher.publish({"ride_id": ride_id, "status": status, "driver_id": driver_id, "ts": time.time(), **extra})
