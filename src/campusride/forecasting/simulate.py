"""Synthetic campus ride-demand generator.

THIS IS SIMULATED DATA. There's no public trip log for IIT Roorkee, so we generate one from an explicit,
documented process. It's built to contain the kinds of structure a forecaster must learn, and noise it
cannot learn:

* weekly x daily profiles that differ by zone (lectures pull hostels -> academic in the morning; evenings
  flow back; weekend nights flow to the gate, market and station)
* an academic calendar: semesters, mid/end-term exam weeks (library-heavy, late nights), vacations
  (demand collapses), public holidays
* campus events (cultural/tech fests) with multi-day surges around SAC and the gate
* train arrivals at Roorkee station at fixed times (spikes in the station zone)
* rain days with persistence (Markov) that inflate demand. The forecaster only gets a noisy
  *forecast* of rain, never the realised weather.
* slow adoption growth
* persistent (AR(1)) campus-wide and per-zone demand-level shocks. Recent history is informative,
  as it is for real demand, but the shocks can't be predicted from the calendar.
* overdispersed (negative-binomial) counts. These are irreducible.

The true intensity `lam` is saved alongside the counts, so evals can report an oracle ceiling:
the error you'd still get knowing the exact generating rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from campusride.campus import ZONES

SLOTS_PER_DAY = 48
ZONE_IDS = list(ZONES)


@dataclass(frozen=True)
class Calendar:
    start: date = date(2025, 7, 7)
    end: date = date(2026, 5, 3)  # inclusive
    # (start, end) inclusive ranges
    teaching: tuple = ((date(2025, 7, 21), date(2025, 11, 23)), (date(2026, 1, 2), date(2026, 4, 26)))
    midterms: tuple = ((date(2025, 9, 15), date(2025, 9, 21)), (date(2026, 2, 16), date(2026, 2, 22)))
    endterms: tuple = ((date(2025, 11, 24), date(2025, 12, 5)), (date(2026, 4, 27), date(2026, 5, 3)))
    fests: tuple = ((date(2025, 10, 16), date(2025, 10, 19)), (date(2026, 3, 19), date(2026, 3, 22)))
    holidays: tuple = (date(2025, 8, 15), date(2025, 10, 2), date(2025, 10, 20), date(2025, 10, 21),
                       date(2025, 11, 5), date(2026, 1, 26), date(2026, 3, 4), date(2026, 4, 3))

    def _in(self, d: date, ranges) -> bool:
        return any(a <= d <= b for a, b in ranges)

    def phase(self, d: date) -> str:
        if self._in(d, self.endterms):
            return "endterm"
        if self._in(d, self.midterms):
            return "midterm"
        if self._in(d, self.teaching):
            return "teaching"
        return "vacation"

    def is_fest(self, d: date) -> bool:
        return self._in(d, self.fests)

    def is_holiday(self, d: date) -> bool:
        return d in self.holidays

    def days_to_fest(self, d: date) -> int:
        future = [(a - d).days for a, _ in self.fests if (a - d).days >= 0]
        return min(future) if future else 99


def _bump(slot: np.ndarray, center_h: float, width_h: float) -> np.ndarray:
    return np.exp(-0.5 * ((slot / 2 - center_h) / width_h) ** 2)


def _profiles() -> dict[str, dict[str, np.ndarray]]:
    """Per-zone intra-day shape for weekday / weekend, as origin intensity multipliers per 30-min slot."""
    s = np.arange(SLOTS_PER_DAY)
    base = 0.03 + 0.0 * s
    wk, we = {}, {}
    wk["hostels_w"] = base + 1.6 * _bump(s, 8.4, 0.5) + 0.9 * _bump(s, 13.5, 0.6) + 0.5 * _bump(s, 19, 1.5) + 0.4 * _bump(s, 22, 1)
    wk["hostels_e"] = base + 1.5 * _bump(s, 8.5, 0.5) + 0.8 * _bump(s, 13.6, 0.6) + 0.5 * _bump(s, 19.5, 1.5) + 0.3 * _bump(s, 22, 1)
    wk["hostels_g"] = base + 1.2 * _bump(s, 8.3, 0.5) + 0.7 * _bump(s, 13.5, 0.7) + 0.5 * _bump(s, 18.5, 1.2)
    wk["acad"] = base + 0.4 * _bump(s, 10.5, 1.5) + 1.5 * _bump(s, 13.1, 0.5) + 1.8 * _bump(s, 17.6, 0.6) + 0.3 * _bump(s, 21, 1.5)
    wk["activity"] = base + 0.2 * _bump(s, 7, 1) + 0.9 * _bump(s, 19.5, 1.2) + 0.6 * _bump(s, 22, 0.8)
    wk["hospital"] = base + 0.35 * _bump(s, 11, 2.5) + 0.2 * _bump(s, 17, 2)
    wk["gate"] = base + 0.3 * _bump(s, 9, 1.5) + 0.6 * _bump(s, 18.5, 2) + 0.4 * _bump(s, 21.5, 1)
    wk["station"] = base * 0.5
    wk["town"] = base + 0.25 * _bump(s, 13, 3) + 0.7 * _bump(s, 20, 1.5)
    for z, v in wk.items():
        we[z] = v.copy()
    we["hostels_w"] = base + 0.5 * _bump(s, 11, 2) + 1.0 * _bump(s, 18, 1.5) + 0.3 * _bump(s, 22, 1)
    we["hostels_e"] = base + 0.5 * _bump(s, 11.5, 2) + 0.9 * _bump(s, 18, 1.5) + 0.3 * _bump(s, 22, 1)
    we["hostels_g"] = base + 0.5 * _bump(s, 11, 2) + 0.8 * _bump(s, 17.5, 1.5)
    we["acad"] = base + 0.2 * _bump(s, 12, 3)
    we["gate"] = base + 0.6 * _bump(s, 12, 2.5) + 0.9 * _bump(s, 21.5, 1.5)
    we["town"] = base + 0.6 * _bump(s, 14, 3) + 1.1 * _bump(s, 21, 1.5)
    we["activity"] = base + 0.6 * _bump(s, 17, 2.5) + 0.4 * _bump(s, 21, 1)
    return {"weekday": wk, "weekend": we}


# Train arrivals at Roorkee (illustrative times) -> station zone spikes in the following 30-60 min.
TRAIN_SLOTS = [11, 14, 21, 29, 35, 41, 45]  # 05:30, 07:00, 10:30, 14:30, 17:30, 20:30, 22:30
ZONE_SCALE = {"hostels_w": 7.0, "hostels_e": 7.0, "hostels_g": 4.0, "acad": 6.0, "activity": 3.0,
              "hospital": 1.5, "gate": 3.0, "station": 2.5, "town": 2.5}


def simulate(seed: int = 7, cal: Calendar | None = None) -> pd.DataFrame:
    """Return one row per (zone, 30-min slot): true intensity `lam`, realised count `y`, plus the
    *exogenous* information that would be known in advance (calendar, events, rain forecast)."""
    cal = cal or Calendar()
    rng = np.random.default_rng(seed)
    prof = _profiles()
    days = pd.date_range(cal.start, cal.end, freq="D")
    n_days = len(days)

    # Rain: Markov chain, monsoon (Jul-Sep) wetter. Forecast is right ~80% of the time.
    rain = np.zeros(n_days, dtype=bool)
    for i, d in enumerate(days):
        p_wet = 0.45 if d.month in (7, 8, 9) else 0.08
        p = 0.65 if i and rain[i - 1] else p_wet
        rain[i] = rng.random() < p
    rain_fc = np.where(rng.random(n_days) < 0.8, rain, ~rain)

    # Unexplained demand level: persistent (AR(1) in log space), like real busy/quiet spells.
    # Campus-wide factor (phi=0.85, marginal sd ~0.18) plus a smaller per-zone factor (phi=0.8, sd ~0.12).
    def ar1(phi: float, sd: float, n: int) -> np.ndarray:
        z = np.zeros(n)
        eps = rng.normal(0, sd * np.sqrt(1 - phi**2), n)
        z[0] = rng.normal(0, sd)
        for t in range(1, n):
            z[t] = phi * z[t - 1] + eps[t]
        return z

    day_shock = np.exp(ar1(0.85, 0.18, n_days))
    zone_shock = {z: np.exp(ar1(0.8, 0.12, n_days)) for z in ZONE_IDS}
    rows = []
    for i, d in enumerate(days):
        dd = d.date()
        phase = cal.phase(dd)
        weekend = d.weekday() >= 5 or cal.is_holiday(dd)
        fest = cal.is_fest(dd)
        growth = 1 + 0.0015 * i
        phase_mult = {"teaching": 1.0, "midterm": 0.85, "endterm": 0.75, "vacation": 0.22}[phase]
        for z in ZONE_IDS:
            shape = prof["weekend" if weekend else "weekday"][z].copy()
            s = np.arange(SLOTS_PER_DAY)
            if phase in ("midterm", "endterm"):
                # exams: less lecture traffic, more late-night library -> hostel flows
                if z == "acad":
                    shape = shape * 0.6 + 1.2 * _bump(s, 23, 1.2) + 0.6 * _bump(s, 1, 0.8)
                if z in ("hostels_w", "hostels_e", "hostels_g"):
                    shape = shape * 0.8 + 0.5 * _bump(s, 20.5, 1.0)
            if z == "station":
                for ts in TRAIN_SLOTS:
                    shape[min(ts + 1, 47)] += 0.9
                    shape[min(ts + 2, 47)] += 0.4
                if phase == "vacation" or (dd.weekday() == 4) or (dd.weekday() == 6):
                    shape *= 1.8  # travel days
            mult = phase_mult * growth * day_shock[i] * zone_shock[z][i] * (1.35 if rain[i] else 1.0)
            if z == "station" and phase == "vacation":
                mult /= phase_mult * 1.6  # station traffic doesn't collapse in vacation
            if fest:
                fest_boost = {"activity": 3.5, "gate": 2.5, "station": 2.0, "town": 1.6}.get(z, 1.3)
                shape = shape + fest_boost * 0.5 * _bump(s, 21, 2.5)
                mult *= 1.15
            lam = ZONE_SCALE[z] * shape * mult
            # Negative binomial with dispersion k: Var = lam + lam^2 / k
            k = 6.0
            y = rng.poisson(rng.gamma(k, lam / k))
            for slot in range(SLOTS_PER_DAY):
                rows.append((z, d + pd.Timedelta(minutes=30 * slot), slot, float(lam[slot]), int(y[slot]),
                             phase, weekend, fest, bool(rain_fc[i]), bool(rain[i]), cal.days_to_fest(dd)))
    df = pd.DataFrame(rows, columns=["zone", "ts", "slot", "lam", "y", "phase", "is_weekend", "is_fest",
                                     "rain_forecast", "rain_actual", "days_to_fest"])
    df["date"] = df["ts"].dt.normalize()
    return df


def expand_to_rides(demand: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    """Turn zone-slot counts into individual ride requests (origin/destination places, minute timestamps).
    Used by the dispatch replay and to seed the database with history."""
    from campusride.campus import PLACES

    rng = np.random.default_rng(seed)
    by_zone = {z: [p.id for p in PLACES.values() if p.zone == z] for z in ZONE_IDS}
    dest_pref = {
        "morning": {"acad": 6, "hospital": 1, "activity": 1, "gate": 1, "station": 1},
        "midday": {"hostels_w": 3, "hostels_e": 3, "hostels_g": 2, "acad": 2, "town": 1},
        "evening": {"hostels_w": 3, "hostels_e": 3, "hostels_g": 2, "activity": 2, "town": 2, "gate": 2},
        "night": {"hostels_w": 3, "hostels_e": 3, "hostels_g": 2, "town": 1, "station": 1},
    }
    out = []
    for r in demand.loc[demand["y"] > 0].itertuples(index=False):
        h = r.slot / 2
        band = "morning" if 6 <= h < 11 else "midday" if 11 <= h < 16 else "evening" if 16 <= h < 21 else "night"
        prefs = {z: w for z, w in dest_pref[band].items() if z != r.zone} or {"acad": 1}
        zs, ws = zip(*prefs.items(), strict=False)
        ws = np.array(ws, float) / sum(ws)
        for _ in range(r.y):
            dz = zs[rng.choice(len(zs), p=ws)]
            out.append((r.ts + pd.Timedelta(seconds=int(rng.integers(0, 1800))), r.zone,
                        rng.choice(by_zone[r.zone]), dz, rng.choice(by_zone[dz]), int(rng.choice([1, 1, 1, 2, 2, 3, 4]))))
    return pd.DataFrame(out, columns=["ts", "origin_zone", "pickup", "dest_zone", "dropoff", "passengers"]).sort_values("ts")
