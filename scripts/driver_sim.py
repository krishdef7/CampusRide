"""Simulated driver fleet for the live demo. Each driver holds a WebSocket to /ws/drivers/{id}, streams
its GPS position, reacts to assignment events (drive to pickup -> start -> drive to dropoff -> complete)
and wanders between landmarks while idle.

    python scripts/driver_sim.py --drivers 40 --speedup 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from campusride import campus  # noqa: E402


class SimDriver:
    def __init__(self, base: str, name: str, vt: str, speedup: float, rng: random.Random):
        self.base, self.name, self.vt, self.speedup, self.rng = base, name, vt, speedup, rng
        p = rng.choice(list(campus.PLACES.values()))
        self.lat, self.lon = p.lat, p.lon
        self.job: asyncio.Queue = asyncio.Queue()

    async def drive_to(self, ws, lat: float, lon: float) -> None:
        dist = campus.haversine_m(self.lat, self.lon, lat, lon)
        secs = campus.eta_seconds(dist, self.vt) / self.speedup
        steps = max(1, int(secs))
        la0, lo0 = self.lat, self.lon
        for i in range(1, steps + 1):
            self.lat, self.lon = la0 + (lat - la0) * i / steps, lo0 + (lon - lo0) * i / steps
            await ws.send(json.dumps({"lat": self.lat, "lon": self.lon}))
            await asyncio.sleep(secs / steps)

    async def run(self) -> None:
        async with httpx.AsyncClient(base_url=self.base, timeout=10) as http:
            self.id = (await http.post("/drivers", json={"name": self.name, "vehicle_type": self.vt,
                                                        "lat": self.lat, "lon": self.lon})).json()["id"]
            async with websockets.connect(self.base.replace("http", "ws") + f"/ws/drivers/{self.id}") as ws:
                listener = asyncio.create_task(self.listen(ws))
                try:
                    while True:
                        try:
                            ride_id = await asyncio.wait_for(self.job.get(), timeout=self.rng.uniform(5, 15))
                        except TimeoutError:
                            p = self.rng.choice(list(campus.PLACES.values()))
                            await self.drive_to(ws, p.lat + self.rng.gauss(0, 3e-4), p.lon + self.rng.gauss(0, 3e-4))
                            continue
                        ride = (await http.get(f"/rides/{ride_id}")).json()
                        if ride["status"] != "assigned":
                            continue
                        await self.drive_to(ws, ride["pickup_lat"], ride["pickup_lon"])
                        if (await http.post(f"/drivers/{self.id}/rides/{ride_id}/start")).status_code != 200:
                            continue  # cancelled while we were on the way
                        await self.drive_to(ws, ride["dropoff_lat"], ride["dropoff_lon"])
                        await http.post(f"/drivers/{self.id}/rides/{ride_id}/complete")
                finally:
                    listener.cancel()

    async def listen(self, ws) -> None:
        async for raw in ws:
            ev = json.loads(raw)
            if ev.get("type") == "ride_event" and ev.get("status") == "assigned" and ev.get("driver_id") == self.id:
                await self.job.put(ev["ride_id"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--drivers", type=int, default=40)
    ap.add_argument("--speedup", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    fleet = [SimDriver(args.base_url, f"sim-{i}", rng.choices(["e_rickshaw", "auto", "cab"], [60, 25, 15])[0],
                       args.speedup, random.Random(args.seed + i)) for i in range(args.drivers)]
    await asyncio.gather(*(d.run() for d in fleet))


if __name__ == "__main__":
    asyncio.run(main())
