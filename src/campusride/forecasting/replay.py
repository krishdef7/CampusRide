"""Dispatch replay: does forecast-driven repositioning actually cut rider wait times?

Replays held-out test-period ride requests (synthetic) through a fleet simulator under four
repositioning policies that differ ONLY in the forecast they trust:

    none            drivers wait wherever their last trip ended
    static_share    no forecast: idle drivers rebalanced to each zone's *average* share of demand in the
                    training period (the obvious non-ML ops heuristic: fixed stands)
    seasonal_naive  reposition idle drivers each 30 min using last week's counts
    lightgbm        reposition using the day-ahead LightGBM forecast
    oracle          reposition using the realised counts (upper bound, not achievable)

Dispatch: nearest-in-time driver (idle or finishing soonest). Riders abandon after 20 min.
Repositioning drivers can be dispatched mid-move (position interpolated).

    python -m campusride.forecasting.replay --fleet 25
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from campusride.campus import PLACES, eta_seconds, haversine_m
from campusride.forecasting.allocation import CENTROIDS, recommend_moves
from campusride.forecasting.pipeline import REPORT_DIR
from campusride.forecasting.simulate import expand_to_rides

BOARDING_S = 60.0
ABANDON_S = 20 * 60.0
POLICIES = ["none", "static_share", "seasonal_naive", "lightgbm", "oracle"]


@dataclass
class Driver:
    free_at: float
    lat: float
    lon: float
    # repositioning leg (only meaningful when idle)
    o_lat: float = 0.0
    o_lon: float = 0.0
    depart: float = 0.0
    arrive: float = 0.0

    def pos(self, t: float) -> tuple[float, float]:
        if self.arrive <= self.depart or t >= self.arrive:
            return self.lat, self.lon
        if t <= self.depart:
            return self.o_lat, self.o_lon
        f =(t - self.depart) / (self.arrive - self.depart)
        return self.o_lat + f * (self.lat - self.o_lat), self.o_lon + f * (self.lon - self.o_lon)


def _travel(a: tuple[float, float], b: tuple[float, float]) -> float:
    return eta_seconds(haversine_m(*a, *b))


def replay_day(rides: pd.DataFrame, forecast: pd.DataFrame | None, fleet: int, seed: int) -> dict:
    """rides: requests for one day (ts, pickup, dropoff). forecast: zone x slot yhat for that day, or None."""
    rng = np.random.default_rng(seed)
    day0 = rides["ts"].min().normalize()
    places = list(PLACES.values())
    start = [places[i] for i in rng.integers(0, len(places), fleet)]
    drivers = [Driver(0.0, p.lat, p.lon) for p in start]
    t_rides = ((rides["ts"] - day0).dt.total_seconds()).to_numpy()
    fc_by_slot = {} if forecast is None else {s: g.set_index("zone")["yhat"].to_dict() for s, g in forecast.groupby("slot")}

    waits, abandoned, deadhead_m = [], 0, 0.0
    next_slot = 0
    for t, pu, do in zip(t_rides, rides["pickup"], rides["dropoff"], strict=False):
        while next_slot * 1800 <= t:
            if next_slot in fc_by_slot:
                slot_t = next_slot * 1800.0
                idle = [(i, *d.pos(slot_t)) for i, d in enumerate(drivers) if d.free_at <= slot_t]
                for mv in recommend_moves(fc_by_slot[next_slot], idle):
                    d = drivers[mv["driver_id"]]
                    cur = d.pos(slot_t)
                    tgt = CENTROIDS[mv["to_zone"]]
                    d.o_lat, d.o_lon = cur
                    d.lat, d.lon = tgt
                    d.depart, d.arrive = slot_t, slot_t + _travel(cur, tgt)
                    deadhead_m += mv["distance_m"]
            next_slot += 1
        p, q = PLACES[pu], PLACES[do]
        best, best_arrival = None, float("inf")
        for i, d in enumerate(drivers):
            ready = max(d.free_at, t)
            arrival = ready + _travel(d.pos(ready), (p.lat, p.lon))
            if arrival < best_arrival:
                best, best_arrival = i, arrival
        wait = best_arrival - t
        if wait > ABANDON_S:
            abandoned += 1
            continue
        waits.append(wait)
        d = drivers[best]
        trip = eta_seconds(haversine_m(p.lat, p.lon, q.lat, q.lon))
        d.free_at = best_arrival + BOARDING_S + trip
        d.lat, d.lon = q.lat, q.lon
        d.depart = d.arrive = 0.0
    w = np.array(waits) / 60
    return {"requests": len(t_rides), "served": len(waits), "abandoned": abandoned, "waits_min": w, "deadhead_km": deadhead_m / 1000}


def run(fleet: int = 25, n_days: int = 21, seed: int = 3) -> dict:
    preds = pd.read_parquet(REPORT_DIR / "test_predictions.parquet")
    days = sorted(preds["date"].unique())
    # Deterministic sample of test days that always includes the fest days.
    fest_days = sorted(preds.loc[preds.is_fest == 1, "date"].unique())
    rng = np.random.default_rng(seed)
    others = [d for d in days if d not in fest_days]
    chosen = sorted(set(fest_days) | set(rng.choice(others, size=max(0, n_days - len(fest_days)), replace=False)))

    col = {"seasonal_naive": "seasonal_naive_7d", "lightgbm": "lightgbm", "oracle": "y"}
    from campusride.forecasting.pipeline import TRAIN_END
    from campusride.forecasting.simulate import simulate

    hist = simulate(seed=7)
    share = hist[hist.date <= TRAIN_END].groupby("zone")["y"].mean().to_dict()
    agg = {p: {"waits": [], "requests": 0, "abandoned": 0, "deadhead_km": 0.0} for p in POLICIES}
    for k, day in enumerate(chosen):
        dd = preds[preds.date == day]
        rides = expand_to_rides(dd.rename(columns={"y": "y"}), seed=1000 + k)
        for policy in POLICIES:
            if policy == "none":
                fc = None
            elif policy == "static_share":
                fc = dd[["zone", "slot"]].assign(yhat=dd["zone"].map(share))
            else:
                fc = dd[["zone", "slot", col[policy]]].rename(columns={col[policy]: "yhat"})
            r = replay_day(rides, fc, fleet, seed=k)
            a = agg[policy]
            a["waits"].append(r["waits_min"])
            a["requests"] += r["requests"]
            a["abandoned"] += r["abandoned"]
            a["deadhead_km"] += r["deadhead_km"]

    out = {"data": "SYNTHETIC test-period requests; simulated fleet", "fleet": fleet, "days": len(chosen),
           "policies": {}}
    for p, a in agg.items():
        w = np.concatenate(a["waits"])
        out["policies"][p] = {
            "requests": a["requests"], "mean_wait_min": round(float(w.mean()), 2),
            "p90_wait_min": round(float(np.percentile(w, 90)), 2),
            "served_within_5min": round(float((w <= 5).mean()), 4),
            "abandon_rate": round(a["abandoned"] / a["requests"], 4),
            "deadhead_km_per_day": round(a["deadhead_km"] / len(chosen), 1),
        }
    base = out["policies"]["none"]["mean_wait_min"]
    for p in POLICIES:
        out["policies"][p]["mean_wait_reduction_vs_none"] = round(1 - out["policies"][p]["mean_wait_min"] / base, 4)
    return out


def to_markdown(r: dict) -> str:
    lines = [f"# Dispatch replay ({r['data']})", "", f"Fleet: {r['fleet']} e-rickshaws · {r['days']} held-out days", "",
             "| Policy | Mean wait (min) | p90 wait | ≤5 min | Abandoned | Dead-head km/day | Mean wait vs none | Mean wait vs static stands |",
             "|---|---|---|---|---|---|---|---|"]
    static = r["policies"]["static_share"]["mean_wait_min"]
    for p, v in r["policies"].items():
        lines.append(f"| {p} | {v['mean_wait_min']:.2f} | {v['p90_wait_min']:.2f} | {v['served_within_5min']:.1%} | "
                     f"{v['abandon_rate']:.2%} | {v['deadhead_km_per_day']:.0f} | {-v['mean_wait_reduction_vs_none']:+.1%} | "
                     f"{v['mean_wait_min'] / static - 1:+.1%} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fleet", type=int, nargs="+", default=[20, 25, 30])
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()
    reports = [run(fleet=f, n_days=args.days) for f in args.fleet]
    (REPORT_DIR / "replay_report.json").write_text(json.dumps(reports, indent=2))
    md = "\n".join(to_markdown(r) for r in reports)
    (REPORT_DIR / "replay_report.md").write_text(md, encoding="utf-8")
    print(md)
