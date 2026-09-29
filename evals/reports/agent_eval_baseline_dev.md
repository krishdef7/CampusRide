# Agent eval: `baseline` on `dev` (100 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **87.0%** |
| Tool selection (action) accuracy | 94.0% |
| Clarification precision / recall | 66.7% / 100.0% |
| Invalid requests declined (n=12) | 91.7% (reason correct 91.7%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 91.7% |
| dropoff | 91.7% |
| pickup_at | 94.0% |
| passengers | 86.7% |
| vehicle_type | 91.7% |
| ride_id | 100.0% |
| missing | 66.7% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 38 | 84.2% |
| cancel | 7 | 100.0% |
| clarify | 11 | 63.6% |
| decline | 11 | 90.9% |
| handwritten | 10 | 100.0% |
| multiturn | 7 | 100.0% |
| quote | 9 | 77.8% |
| status | 7 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 15 | 86.7% |
| bare_hour | 1 | 100.0% |
| capacity | 3 | 100.0% |
| explicit_id | 6 | 100.0% |
| hinglish | 11 | 100.0% |
| multiturn | 8 | 100.0% |
| out_of_area | 3 | 100.0% |
| out_of_scope | 4 | 75.0% |
| passenger_arithmetic | 7 | 42.9% |
| relative_time | 2 | 50.0% |
| same_place | 1 | 100.0% |
| terse | 1 | 100.0% |
| typo | 5 | 0.0% |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 3
- `decline->clarify`: 1
- `get_quote->clarify`: 2
