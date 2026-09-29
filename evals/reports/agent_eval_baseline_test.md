# Agent eval: `baseline` on `test` (500 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **88.6%** |
| Tool selection (action) accuracy | 94.4% |
| Clarification precision / recall | 69.5% / 96.6% |
| Invalid requests declined (n=62) | 90.3% (reason correct 90.3%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 92.1% |
| dropoff | 92.1% |
| pickup_at | 92.5% |
| passengers | 92.1% |
| vehicle_type | 93.8% |
| ride_id | 97.3% |
| missing | 74.6% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 200 | 90.0% |
| cancel | 35 | 100.0% |
| clarify | 55 | 72.7% |
| decline | 55 | 92.7% |
| handwritten | 45 | 73.3% |
| multiturn | 30 | 93.3% |
| quote | 45 | 91.1% |
| status | 35 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 58 | 94.8% |
| ambiguous_place | 13 | 69.2% |
| bare_hour | 4 | 100.0% |
| booking_distractor | 1 | 0.0% |
| capacity | 20 | 90.0% |
| day_offset | 9 | 100.0% |
| distractor_time | 3 | 33.3% |
| explicit_id | 66 | 100.0% |
| hinglish | 60 | 91.7% |
| implicit_pickup | 3 | 66.7% |
| indirect | 1 | 100.0% |
| multiturn | 33 | 90.9% |
| no_context | 1 | 100.0% |
| out_of_area | 20 | 100.0% |
| out_of_scope | 8 | 75.0% |
| passenger_arithmetic | 31 | 80.7% |
| relative_time | 27 | 92.6% |
| same_place | 7 | 100.0% |
| slang | 2 | 0.0% |
| terse | 1 | 100.0% |
| typo | 27 | 33.3% |
| vehicle_distractor | 1 | 0.0% |
| vehicle_slang | 1 | 100.0% |
| verbal_time | 3 | 66.7% |
| weekday | 16 | 93.8% |
| word_order | 2 | 100.0% |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 15
- `clarify->decline`: 2
- `decline->book_ride`: 1
- `decline->clarify`: 5
- `get_quote->clarify`: 3
- `get_ride_status->clarify`: 2
