from datetime import date

import numpy as np
import pandas as pd
import pytest

from campusride.forecasting.allocation import nearest_zone, recommend_moves, target_counts
from campusride.forecasting.features import FEATURE_GROUPS, build_features
from campusride.forecasting.simulate import Calendar, simulate


@pytest.fixture(scope="module")
def small():
    return simulate(seed=1, cal=Calendar(start=date(2025, 7, 7), end=date(2025, 9, 28)))


def test_simulator_shape_and_determinism(small):
    assert len(small) == small["date"].nunique() * 9 * 48
    again = simulate(seed=1, cal=Calendar(start=date(2025, 7, 7), end=date(2025, 9, 28)))
    pd.testing.assert_frame_equal(small, again)
    assert (small["y"] >= 0).all() and small["lam"].gt(0).all()


def test_no_future_leakage(small):
    """Features for day D must be identical whatever happens on day D or later."""
    cutoff = pd.Timestamp("2025-09-01")
    f1 = build_features(small)
    tampered = small.copy()
    tampered.loc[tampered["date"] >= cutoff, "y"] = 10_000
    f2 = build_features(tampered)
    cols = FEATURE_GROUPS["history"] + FEATURE_GROUPS["level"] + ["lag_1d", "lag_7d", "lag_14d"]
    upto = f1["date"] <= cutoff
    pd.testing.assert_frame_equal(f1.loc[upto, cols].reset_index(drop=True), f2.loc[upto, cols].reset_index(drop=True))
    assert f1.loc[upto, cols].notna().any().all()  # features actually populated
    # ...and the day after the cutoff *does* see the change (the test would pass vacuously otherwise)
    nxt = f1["date"] == cutoff + pd.Timedelta(days=1)
    assert not np.allclose(f1.loc[nxt, "lag_1d"], f2.loc[nxt, "lag_1d"])


def test_lag_alignment(small):
    f = build_features(small).set_index(["zone", "date", "slot"])
    row = f.loc[("acad", pd.Timestamp("2025-08-20"), 20)]
    prev = f.loc[("acad", pd.Timestamp("2025-08-13"), 20)]
    assert row["lag_7d"] == prev["y"]


def test_target_counts_proportional_and_exact():
    c = target_counts({"acad": 10, "gate": 5, "town": 5}, 8)
    assert sum(c.values()) == 8 and c["acad"] == 4


def test_recommend_moves_goes_where_demand_is():
    # 4 idle drivers all at the station, all demand in the academic core
    from campusride.campus import PLACES

    st = PLACES["railway_station"]
    drivers = [(i, st.lat, st.lon) for i in range(4)]
    fc = {z: 0.0 for z in ["acad", "activity", "hostels_w", "hostels_e", "hostels_g", "hospital", "gate", "station", "town"]}
    fc["acad"] = 12.0
    moves = recommend_moves(fc, drivers)
    assert len(moves) == 4 and all(m["to_zone"] == "acad" for m in moves)
    assert nearest_zone(st.lat, st.lon) == "station"
