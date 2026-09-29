"""External validity check: the same forecasting pipeline on REAL demand (NYC TLC green-taxi pickups).

The campus data is synthetic, so a skeptic can say the model only learns what the simulator put in. This
runs the unchanged protocol (features, baselines, rolling-origin backtest, bootstrap CI, ablation) on
public trip records instead. Green taxis are chosen because their per-zone volumes (a few pickups per
30 minutes) are close to campus scale; yellow-taxi zones are 10-100x busier and much easier to forecast.

Substitutions for the campus-only columns, all known before the forecast day:
* is_fest / days_to_fest -> US federal holidays (pandas USFederalHolidayCalendar)
* rain_forecast          -> Open-Meteo *archived* short-range forecast, daily precipitation >= 1 mm
                            (historical-forecast API; slightly optimistic vs a true D-1 forecast)
* phase                  -> constant (no academic calendar), so phase_changed_7d is always 0

Zones: the 10 busiest green-taxi pickup zones in the training period (chosen on training data only).

    python -m campusride.forecasting.real_nyc     # downloads ~20 MB once into data/nyc/, writes forecast_report_nyc.*
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from campusride.forecasting.pipeline import REPORT_DIR, evaluate, to_markdown

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "nyc"
MONTHS = pd.period_range("2023-07", "2024-06", freq="M")
TRAIN_END = pd.Timestamp("2024-01-31")
VAL_END = pd.Timestamp("2024-02-29")  # test = 2024-03-01 .. 2024-06-30
TRIPS_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_{m}.parquet"
ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
WEATHER_URL = ("https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=40.78&longitude=-73.93"
               "&start_date={a}&end_date={b}&daily=precipitation_sum&timezone=America%2FNew_York")
N_ZONES = 10


def _download(url: str, path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed https URLs
        tmp.rename(path)
    return path


def load_pickups() -> pd.DataFrame:
    frames = []
    for m in MONTHS:
        f = _download(TRIPS_URL.format(m=m), CACHE / f"green_{m}.parquet")
        t = pd.read_parquet(f, columns=["lpep_pickup_datetime", "PULocationID"])
        t = t[(t.lpep_pickup_datetime >= m.start_time) & (t.lpep_pickup_datetime <= m.end_time)]  # drop mis-dated rows
        frames.append(t)
    return pd.concat(frames, ignore_index=True)


def load_rain_forecast(start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    f = CACHE / f"rain_forecast_{start.date()}_{end.date()}.json"
    if not f.exists():
        _download(WEATHER_URL.format(a=start.date(), b=end.date()), f)
    d = json.loads(f.read_text())["daily"]
    s = pd.Series(d["precipitation_sum"], index=pd.to_datetime(d["time"]), dtype=float)
    return (s.fillna(0) >= 1.0).rename("rain_forecast")


def build_frame() -> tuple[pd.DataFrame, list[str]]:
    trips = load_pickups()
    names = pd.read_csv(_download(ZONES_URL, CACHE / "taxi_zone_lookup.csv")).set_index("LocationID")["Zone"]
    train_trips = trips[trips.lpep_pickup_datetime <= TRAIN_END + pd.Timedelta(days=1)]
    top = train_trips.PULocationID.value_counts().head(N_ZONES).index.tolist()
    trips = trips[trips.PULocationID.isin(top)]
    trips["ts"] = trips.lpep_pickup_datetime.dt.floor("30min")

    start, end = MONTHS[0].start_time.normalize(), MONTHS[-1].end_time.normalize()
    grid = pd.MultiIndex.from_product([top, pd.date_range(start, end + pd.Timedelta(hours=23, minutes=30), freq="30min")],
                                      names=["PULocationID", "ts"])
    counts = trips.groupby(["PULocationID", "ts"]).size().reindex(grid, fill_value=0).rename("y").reset_index()
    counts["zone"] = counts.PULocationID.map(names).str.replace(r"[^A-Za-z]+", "_", regex=True).str.strip("_").str.lower()
    counts["date"] = counts.ts.dt.normalize()
    counts["slot"] = counts.ts.dt.hour * 2 + counts.ts.dt.minute // 30

    days = pd.date_range(start, end, freq="D")
    hol = USFederalHolidayCalendar().holidays(start, end + pd.Timedelta(days=400))
    next_hol = pd.Series([int((hol[hol >= d].min() - d).days) for d in days], index=days)
    cal = pd.DataFrame({"date": days, "is_weekend": days.weekday >= 5, "is_fest": days.isin(hol),
                        "days_to_fest": next_hol.clip(upper=60).to_numpy(), "phase": "teaching"})
    cal = cal.merge(load_rain_forecast(start, end).rename_axis("date").reset_index(), on="date", how="left")
    cal["rain_forecast"] = cal["rain_forecast"].fillna(False).astype(bool)
    df = counts.merge(cal, on="date", how="left")
    zone_names = [names[z] for z in top]
    return df[["zone", "ts", "slot", "y", "phase", "is_weekend", "is_fest", "rain_forecast", "days_to_fest", "date"]], zone_names


def main() -> dict:
    df, zone_names = build_frame()
    report, *_ = evaluate(
        df, TRAIN_END, VAL_END,
        data=("REAL - NYC TLC green-taxi trip records (public), pickups in the 10 busiest zones of the training period; "
              "US federal holidays and Open-Meteo archived rain forecasts as the calendar/weather inputs"),
        task=f"day-ahead forecast of taxi pickups per zone per 30-min slot ({len(zone_names)} zones x 48 slots)",
        regime_names={"fest": "us_federal_holiday", "teaching": "regular_day"})
    report["zones"] = zone_names
    report["mean_pickups_per_zone_slot"] = round(float(df[df.date > VAL_END].y.mean()), 3)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "forecast_report_nyc.json").write_text(json.dumps(report, indent=2))
    md = to_markdown(report).replace("# Demand forecasting report", "# Demand forecasting report: real NYC taxi data", 1)
    md += (f"\nZones: {', '.join(zone_names)}. Mean pickups per zone-slot in test: {report['mean_pickups_per_zone_slot']}.\n"
           "No oracle row: real data has no known generating rate.\n")
    (REPORT_DIR / "forecast_report_nyc.md").write_text(md, encoding="utf-8")
    return report


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    rep = main()
    print((REPORT_DIR / "forecast_report_nyc.md").read_text(encoding="utf-8"))
