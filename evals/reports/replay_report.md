# Dispatch replay (SYNTHETIC test-period requests; simulated fleet)

Fleet: 20 e-rickshaws · 21 held-out days

| Policy | Mean wait (min) | p90 wait | ≤5 min | Abandoned | Dead-head km/day | Mean wait vs none | Mean wait vs static stands |
|---|---|---|---|---|---|---|---|
| none | 2.48 | 4.79 | 91.3% | 0.07% | 0 | -0.0% | +27.2% |
| static_share | 1.95 | 3.99 | 94.6% | 0.06% | 172 | -21.4% | +0.0% |
| seasonal_naive | 2.00 | 4.01 | 94.1% | 0.04% | 400 | -19.4% | +2.6% |
| lightgbm | 1.78 | 3.80 | 95.0% | 0.05% | 227 | -28.2% | -8.7% |
| oracle | 1.59 | 3.56 | 95.5% | 0.07% | 383 | -35.9% | -18.5% |

# Dispatch replay (SYNTHETIC test-period requests; simulated fleet)

Fleet: 25 e-rickshaws · 21 held-out days

| Policy | Mean wait (min) | p90 wait | ≤5 min | Abandoned | Dead-head km/day | Mean wait vs none | Mean wait vs static stands |
|---|---|---|---|---|---|---|---|
| none | 2.01 | 4.06 | 95.1% | 0.00% | 0 | -0.0% | +42.6% |
| static_share | 1.41 | 3.36 | 97.9% | 0.00% | 198 | -29.8% | +0.0% |
| seasonal_naive | 1.49 | 3.42 | 97.3% | 0.00% | 507 | -25.9% | +5.7% |
| lightgbm | 1.24 | 3.04 | 98.2% | 0.00% | 269 | -38.3% | -12.1% |
| oracle | 1.08 | 2.74 | 98.3% | 0.00% | 481 | -46.3% | -23.4% |

# Dispatch replay (SYNTHETIC test-period requests; simulated fleet)

Fleet: 30 e-rickshaws · 21 held-out days

| Policy | Mean wait (min) | p90 wait | ≤5 min | Abandoned | Dead-head km/day | Mean wait vs none | Mean wait vs static stands |
|---|---|---|---|---|---|---|---|
| none | 1.78 | 3.82 | 97.1% | 0.00% | 0 | -0.0% | +50.8% |
| static_share | 1.18 | 2.94 | 99.1% | 0.00% | 213 | -33.7% | +0.0% |
| seasonal_naive | 1.29 | 3.07 | 98.6% | 0.00% | 612 | -27.5% | +9.3% |
| lightgbm | 1.02 | 2.61 | 99.4% | 0.00% | 310 | -42.7% | -13.6% |
| oracle | 0.86 | 2.17 | 99.5% | 0.00% | 577 | -51.7% | -27.1% |
