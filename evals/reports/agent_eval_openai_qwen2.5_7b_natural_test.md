# Agent eval: `openai:qwen2.5:7b` on `natural_test` (120 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **73.3%** |
| Tool selection (action) accuracy | 85.0% |
| Tool execution success (correct DB effect) | **80.6%** |
| Invalid tool-call rate (args rejected by validator) | 14.7% |
| Turns needing self-repair | 10.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.172 |
| Latency p50 / p95 | 12953 ms / 21808 ms |
| Tokens per turn (in / out) | 2651 / 59 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 33.3% / 40.0% |
| Invalid requests declined (n=12) | 66.7% (reason correct 58.3%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 93.0% |
| dropoff | 94.2% |
| pickup_at | 88.5% |
| passengers | 91.9% |
| vehicle_type | 91.9% |
| ride_id | 66.7% |
| missing | 30.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 120 | 73.3% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 1 | 100.0% |
| ambiguous_place | 4 | 50.0% |
| bare_hour | 3 | 33.3% |
| booking_distractor | 2 | 50.0% |
| chat_speak | 6 | 100.0% |
| correction | 9 | 88.9% |
| distractor_number | 2 | 50.0% |
| distractor_place | 2 | 50.0% |
| distractor_time | 7 | 85.7% |
| emoji | 4 | 100.0% |
| explicit_id | 3 | 100.0% |
| hinglish | 16 | 62.5% |
| implicit_pickup | 5 | 100.0% |
| indirect | 8 | 87.5% |
| long_context | 6 | 100.0% |
| multiturn | 8 | 75.0% |
| passenger_arithmetic | 13 | 84.6% |
| quote_then_book | 1 | 100.0% |
| relative_time | 7 | 100.0% |
| terse | 9 | 88.9% |
| third_party | 1 | 100.0% |
| typo | 7 | 85.7% |
| vehicle_distractor | 2 | 0.0% |
| verbal_time | 4 | 75.0% |
| weekday | 3 | 33.3% |
| word_order | 1 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 2
- `book_ride->decline`: 2
- `cancel_ride->clarify`: 1
- `clarify->book_ride`: 5
- `clarify->get_quote`: 1
- `decline->clarify`: 4
- `get_ride_status->clarify`: 1
- `get_ride_status->decline`: 1
- `get_ride_status->get_quote`: 1
