"""Leakage-safe features for day-ahead forecasting.

Forecast issue time: end of day D-1. Target: the 48 half-hour slots of day D for every zone.
Every history feature is built by shifting whole *days*, so row (D, s) only sees counts from day D-1
and earlier. Calendar/event flags and the rain *forecast* are known in advance.
`tests/test_forecasting.py::test_no_future_leakage` checks this property directly.

Feature design was chosen on the validation month, never on test. Single-slot lags (e.g. y at D-7, s)
are dominated by Poisson noise at these volumes (mean ~1.5 rides per zone-slot) and made validation
MAE worse. So the model sees *smoothed* history plus weekday-normalized demand-level ratios instead.
The raw lags are still computed because the baselines use them.
"""

from __future__ import annotations

import pandas as pd

PHASES = ["teaching", "midterm", "endterm", "vacation"]

FEATURE_GROUPS: dict[str, list[str]] = {
    "history": ["mean_4w_same_dow", "mean_7d", "zone_day_total_lag1d", "zone_day_total_lag7d"],
    "level": ["zone_level", "campus_level", "m4w_x_level"],
    "calendar": ["dow", "is_weekend", "phase_code", "phase_changed_7d", "is_fest", "days_to_fest"],
    "weather": ["rain_forecast"],
    "structure": ["zone_code", "slot"],
}
ALL_FEATURES = [f for g in FEATURE_GROUPS.values() for f in g]
REQUIRED = ["lag_14d", "mean_4w_same_dow", "mean_7d", "zone_day_total_lag7d", "zone_level", "campus_level"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["zone", "slot", "date"]).copy()
    g = df.groupby(["zone", "slot"], sort=False)["y"]
    # Rows within a (zone, slot) group are consecutive days (the calendar has no gaps), so shift(k) = k days back.
    df["lag_1d"] = g.shift(1)
    df["lag_7d"] = g.shift(7)
    df["lag_14d"] = g.shift(14)
    df["mean_4w_same_dow"] = sum(g.shift(7 * k) for k in range(1, 5)) / 4
    df["mean_7d"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=7).mean())

    # Daily zone totals -> demand *level*: last 7 days vs the 4 weeks before that (weekday mix cancels out).
    daily = df.groupby(["zone", "date"], as_index=False)["y"].sum().sort_values(["zone", "date"])
    dg = daily.groupby("zone")["y"]
    daily["zone_day_total_lag1d"] = dg.shift(1)
    daily["zone_day_total_lag7d"] = dg.shift(7)
    daily["_s7"] = dg.transform(lambda s: s.shift(1).rolling(7).sum())
    daily["_s28"] = dg.transform(lambda s: s.shift(8).rolling(28).sum())
    daily["zone_level"] = daily["_s7"] / (daily["_s28"] / 4)
    campus = daily.groupby("date")[["_s7", "_s28"]].sum()
    campus["campus_level"] = campus["_s7"] / (campus["_s28"] / 4)
    daily = daily.merge(campus[["campus_level"]], left_on="date", right_index=True)
    df = df.merge(daily[["zone", "date", "zone_day_total_lag1d", "zone_day_total_lag7d", "zone_level", "campus_level"]],
                  on=["zone", "date"], how="left")
    df["m4w_x_level"] = df["mean_4w_same_dow"] * df["zone_level"]

    df["dow"] = df["date"].dt.weekday
    df["is_weekend"] = df["is_weekend"].astype(int)
    df["phase_code"] = df["phase"].map({p: i for i, p in enumerate(PHASES)})
    # Did the academic phase change within the past week? That's exactly when week-old history goes stale.
    phase_by_day = df.drop_duplicates("date").set_index("date")["phase_code"].sort_index()
    changed = (phase_by_day != phase_by_day.shift(7)).astype(int)
    df["phase_changed_7d"] = df["date"].map(changed)
    df["is_fest"] = df["is_fest"].astype(int)
    df["rain_forecast"] = df["rain_forecast"].astype(int)
    df["zone_code"] = pd.Categorical(df["zone"]).codes
    return df.sort_values(["date", "zone", "slot"]).reset_index(drop=True)
