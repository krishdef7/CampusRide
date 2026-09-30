# Agent eval: `openai:gemma-4-26b-a4b-it` on `test` (500 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **85.2%** |
| Tool selection (action) accuracy | 94.8% |
| Tool execution success (correct DB effect) | **92.1%** |
| Invalid tool-call rate (args rejected by validator) | 2.0% |
| Turns needing self-repair | 1.2% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.019 |
| Latency p50 / p95 | 2465 ms / 5398 ms |
| Tokens per turn (in / out) | 2434 / 41 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 79.7% / 100.0% |
| Invalid requests declined (n=62) | 80.7% (reason correct 72.6%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 95.4% |
| dropoff | 95.4% |
| pickup_at | 91.0% |
| passengers | 94.4% |
| vehicle_type | 93.4% |
| ride_id | 100.0% |
| missing | 47.5% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 200 | 90.5% |
| cancel | 35 | 100.0% |
| clarify | 55 | 47.3% |
| decline | 55 | 80.0% |
| handwritten | 45 | 82.2% |
| multiturn | 30 | 80.0% |
| quote | 45 | 97.8% |
| status | 35 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 58 | 94.8% |
| ambiguous_place | 13 | 7.7% |
| bare_hour | 4 | 25.0% |
| booking_distractor | 1 | 100.0% |
| capacity | 20 | 90.0% |
| day_offset | 9 | 100.0% |
| distractor_time | 3 | 66.7% |
| explicit_id | 66 | 100.0% |
| hinglish | 60 | 80.0% |
| implicit_pickup | 3 | 100.0% |
| indirect | 1 | 100.0% |
| multiturn | 33 | 81.8% |
| no_context | 1 | 0.0% |
| out_of_area | 20 | 55.0% |
| out_of_scope | 8 | 100.0% |
| passenger_arithmetic | 31 | 96.8% |
| relative_time | 27 | 88.9% |
| same_place | 7 | 100.0% |
| slang | 2 | 100.0% |
| terse | 1 | 100.0% |
| typo | 27 | 85.2% |
| vehicle_distractor | 1 | 100.0% |
| vehicle_slang | 1 | 100.0% |
| verbal_time | 3 | 66.7% |
| weekday | 16 | 62.5% |
| word_order | 2 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 2 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 5
- `book_ride->decline`: 8
- `book_ride->error`: 1
- `decline->book_ride`: 2
- `decline->clarify`: 10
