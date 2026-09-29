"""Turn a zone demand forecast into driver repositioning recommendations.

Target: split idle drivers across zones in proportion to forecast demand (largest-remainder rounding).
Assignment: an optimal driver -> target-seat matching (Hungarian algorithm) that minimises total
repositioning distance. Only drivers whose assigned zone differs from their current zone get a move.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from campusride.campus import ZONES, haversine_m, zone_centroid

CENTROIDS = {z: zone_centroid(z) for z in ZONES}


def nearest_zone(lat: float, lon: float) -> str:
    return min(CENTROIDS, key=lambda z: haversine_m(lat, lon, *CENTROIDS[z]))


def target_counts(forecast: dict[str, float], n_drivers: int) -> dict[str, int]:
    zones = [z for z in ZONES if z in forecast]
    w = np.array([max(forecast[z], 0.0) for z in zones])
    if n_drivers == 0 or w.sum() <= 0:
        return {z: 0 for z in zones}
    raw = w / w.sum() * n_drivers
    counts = np.floor(raw).astype(int)
    for i in np.argsort(-(raw - counts))[: n_drivers - counts.sum()]:
        counts[i] += 1
    return dict(zip(zones, counts.tolist(), strict=False))


def recommend_moves(forecast: dict[str, float], drivers: list[tuple[int, float, float]],
                    min_gain_m: float = 0.0) -> list[dict]:
    """drivers: (id, lat, lon) of idle drivers. Returns [{driver_id, from_zone, to_zone, distance_m}]."""
    if not drivers:
        return []
    targets = target_counts(forecast, len(drivers))
    seats = [z for z, c in targets.items() for _ in range(c)]
    cost = np.array([[haversine_m(lat, lon, *CENTROIDS[z]) for z in seats] for _, lat, lon in drivers])
    rows, cols = linear_sum_assignment(cost)
    moves = []
    for r, c in zip(rows, cols, strict=False):
        did, lat, lon = drivers[r]
        cur, dest = nearest_zone(lat, lon), seats[c]
        if cur != dest and cost[r, c] > min_gain_m:
            moves.append({"driver_id": did, "from_zone": cur, "to_zone": dest, "distance_m": round(float(cost[r, c]), 1)})
    return moves
