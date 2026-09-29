# Agent eval: `baseline` on `natural_test` (120 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **65.8%** |
| Tool selection (action) accuracy | 85.0% |
| Clarification precision / recall | 47.6% / 100.0% |
| Invalid requests declined (n=12) | 83.3% (reason correct 75.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 87.2% |
| dropoff | 86.1% |
| pickup_at | 82.0% |
| passengers | 77.9% |
| vehicle_type | 89.5% |
| ride_id | 33.3% |
| missing | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 120 | 65.8% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 1 | 0.0% |
| ambiguous_place | 4 | 100.0% |
| bare_hour | 3 | 66.7% |
| booking_distractor | 2 | 50.0% |
| chat_speak | 6 | 50.0% |
| correction | 9 | 44.4% |
| distractor_number | 2 | 50.0% |
| distractor_place | 2 | 0.0% |
| distractor_time | 7 | 28.6% |
| emoji | 4 | 100.0% |
| explicit_id | 3 | 66.7% |
| hinglish | 16 | 81.2% |
| implicit_pickup | 5 | 80.0% |
| indirect | 8 | 50.0% |
| long_context | 6 | 33.3% |
| multiturn | 8 | 75.0% |
| passenger_arithmetic | 13 | 46.2% |
| quote_then_book | 1 | 100.0% |
| relative_time | 7 | 57.1% |
| terse | 9 | 77.8% |
| third_party | 1 | 100.0% |
| typo | 7 | 28.6% |
| vehicle_distractor | 2 | 0.0% |
| verbal_time | 4 | 75.0% |
| weekday | 3 | 100.0% |
| word_order | 1 | 100.0% |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 3
- `book_ride->decline`: 2
- `cancel_ride->clarify`: 3
- `cancel_ride->decline`: 1
- `decline->clarify`: 2
- `get_quote->book_ride`: 3
- `get_ride_status->clarify`: 3
- `get_ride_status->decline`: 1
