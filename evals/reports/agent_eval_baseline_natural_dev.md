# Agent eval: `baseline` on `natural_dev` (30 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **70.0%** |
| Tool selection (action) accuracy | 86.7% |
| Clarification precision / recall | 40.0% / 100.0% |
| Invalid requests declined (n=4) | 75.0% (reason correct 75.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 90.0% |
| dropoff | 80.0% |
| pickup_at | 94.4% |
| passengers | 90.0% |
| vehicle_type | 95.0% |
| ride_id | 50.0% |
| missing | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 30 | 70.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| ambiguous_place | 1 | 100.0% |
| booking_distractor | 1 | 0.0% |
| correction | 3 | 33.3% |
| distractor_number | 1 | 100.0% |
| emoji | 1 | 100.0% |
| explicit_id | 2 | 50.0% |
| hinglish | 4 | 75.0% |
| implicit_pickup | 1 | 0.0% |
| indirect | 2 | 100.0% |
| multiturn | 2 | 100.0% |
| passenger_arithmetic | 2 | 50.0% |
| terse | 1 | 100.0% |
| typo | 1 | 0.0% |
| verbal_time | 1 | 0.0% |
| weekday | 1 | 100.0% |

## Action confusion (expected -> predicted)

- `cancel_ride->clarify`: 1
- `decline->clarify`: 1
- `get_quote->book_ride`: 1
- `get_ride_status->clarify`: 1
