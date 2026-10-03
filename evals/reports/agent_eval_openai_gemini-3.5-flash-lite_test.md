# Agent eval: `openai:gemini-3.5-flash-lite` on `test` (500 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **99.4%** |
| Tool selection (action) accuracy | 99.8% |
| Tool execution success (correct DB effect) | **99.5%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.0 |
| Latency p50 / p95 | 1139 ms / 2698 ms |
| Tokens per turn (in / out) | 2386 / 42 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 100.0% / 98.3% |
| Invalid requests declined (n=62) | 100.0% (reason correct 98.4%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 100.0% |
| dropoff | 100.0% |
| pickup_at | 99.2% |
| passengers | 100.0% |
| vehicle_type | 100.0% |
| ride_id | 100.0% |
| missing | 98.3% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 200 | 99.0% |
| cancel | 35 | 100.0% |
| clarify | 55 | 98.2% |
| decline | 55 | 100.0% |
| handwritten | 45 | 100.0% |
| multiturn | 30 | 100.0% |
| quote | 45 | 100.0% |
| status | 35 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 58 | 100.0% |
| ambiguous_place | 13 | 100.0% |
| bare_hour | 4 | 50.0% |
| booking_distractor | 1 | 100.0% |
| capacity | 20 | 100.0% |
| day_offset | 9 | 100.0% |
| distractor_time | 3 | 100.0% |
| explicit_id | 66 | 100.0% |
| hinglish | 60 | 100.0% |
| implicit_pickup | 3 | 100.0% |
| indirect | 1 | 100.0% |
| multiturn | 33 | 100.0% |
| no_context | 1 | 100.0% |
| out_of_area | 20 | 100.0% |
| out_of_scope | 8 | 100.0% |
| passenger_arithmetic | 31 | 100.0% |
| relative_time | 27 | 100.0% |
| same_place | 7 | 100.0% |
| slang | 2 | 100.0% |
| terse | 1 | 100.0% |
| typo | 27 | 100.0% |
| vehicle_distractor | 1 | 100.0% |
| vehicle_slang | 1 | 100.0% |
| verbal_time | 3 | 100.0% |
| weekday | 16 | 100.0% |
| word_order | 2 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `clarify->decline`: 1
