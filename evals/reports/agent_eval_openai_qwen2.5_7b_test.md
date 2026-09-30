# Agent eval: `openai:qwen2.5:7b` on `test` (500 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **77.8%** |
| Tool selection (action) accuracy | 85.6% |
| Tool execution success (correct DB effect) | **86.8%** |
| Invalid tool-call rate (args rejected by validator) | 8.3% |
| Turns needing self-repair | 6.2% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.09 |
| Latency p50 / p95 | 12354 ms / 19755 ms |
| Tokens per turn (in / out) | 2460 / 56 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 41.4% / 20.3% |
| Invalid requests declined (n=62) | 79.0% (reason correct 75.8%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 92.4% |
| dropoff | 93.1% |
| pickup_at | 85.1% |
| passengers | 95.4% |
| vehicle_type | 94.7% |
| ride_id | 100.0% |
| missing | 17.0% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 200 | 89.5% |
| cancel | 35 | 100.0% |
| clarify | 55 | 14.5% |
| decline | 55 | 78.2% |
| handwritten | 45 | 77.8% |
| multiturn | 30 | 36.7% |
| quote | 45 | 95.6% |
| status | 35 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 58 | 89.7% |
| ambiguous_place | 13 | 7.7% |
| bare_hour | 4 | 50.0% |
| booking_distractor | 1 | 100.0% |
| capacity | 20 | 100.0% |
| day_offset | 9 | 100.0% |
| distractor_time | 3 | 100.0% |
| explicit_id | 66 | 100.0% |
| hinglish | 60 | 91.7% |
| implicit_pickup | 3 | 100.0% |
| indirect | 1 | 100.0% |
| multiturn | 33 | 33.3% |
| no_context | 1 | 100.0% |
| out_of_area | 20 | 90.0% |
| out_of_scope | 8 | 12.5% |
| passenger_arithmetic | 31 | 93.5% |
| relative_time | 27 | 100.0% |
| same_place | 7 | 57.1% |
| slang | 2 | 100.0% |
| terse | 1 | 100.0% |
| typo | 27 | 92.6% |
| vehicle_distractor | 1 | 100.0% |
| vehicle_slang | 1 | 100.0% |
| verbal_time | 3 | 66.7% |
| weekday | 16 | 31.2% |
| word_order | 2 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 2 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 6
- `book_ride->decline`: 6
- `clarify->book_ride`: 43
- `clarify->decline`: 4
- `decline->book_ride`: 2
- `decline->clarify`: 11
