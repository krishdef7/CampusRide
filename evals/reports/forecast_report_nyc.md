# Demand forecasting report: real NYC taxi data

> REAL - NYC TLC green-taxi trip records (public), pickups in the 10 busiest zones of the training period; US federal holidays and Open-Meteo archived rain forecasts as the calendar/weather inputs

**Task:** day-ahead forecast of taxi pickups per zone per 30-min slot (10 zones x 48 slots)  
**Split:** train 2023-08-05..2024-01-31 · validation 2024-02-01..2024-02-29 · test 2024-03-01..2024-06-30 (122 days, 58,560 zone-slots)  
**Protocol:** rolling-origin, expanding window, weekly refit; features and boosting rounds chosen on validation only

| Model | MAE | RMSE | WAPE |
|---|---|---|---|
| seasonal_naive_7d | 1.494 | 2.492 | 55.4% |
| naive_1d | 1.663 | 2.941 | 61.7% |
| mean_4w_same_dow | 1.244 | 2.002 | 46.1% |
| lightgbm | 1.150 | 1.820 | 42.7% |

**LightGBM vs seasonal-naive:** MAE reduced by **23.0%** (95% day-block bootstrap CI 21.8% to 24.3%).  
**LightGBM vs the strongest baseline (4-week same-weekday mean):** MAE reduced by **7.6%** (95% CI 6.4% to 9.0%).

## By regime

| Regime | Slots | Seasonal-naive MAE | LightGBM MAE | Improvement |
|---|---|---|---|---|
| us_federal_holiday | 960 | 2.151 | 1.247 | 42.0% |
| regular_day | 57,600 | 1.483 | 1.148 | 22.5% |

## Ablation (test MAE, drop one feature group)

| Variant | MAE |
|---|---|
| all_features | 1.1501 |
| without_history | 1.1658 |
| without_level | 1.1489 |
| without_calendar | 1.1714 |
| without_weather | 1.1507 |

## Top features (gain)

- `m4w_x_level`: 806,223
- `mean_4w_same_dow`: 436,016
- `mean_7d`: 409,882
- `slot`: 31,737
- `zone_code`: 24,186
- `zone_day_total_lag1d`: 17,908
- `dow`: 13,060
- `zone_day_total_lag7d`: 12,988

Zones: East Harlem North, East Harlem South, Forest Hills, Central Harlem, Morningside Heights, Elmhurst, Central Park, Fort Greene, Downtown Brooklyn/MetroTech, Jamaica. Mean pickups per zone-slot in test: 2.696.
No oracle row: real data has no known generating rate.
