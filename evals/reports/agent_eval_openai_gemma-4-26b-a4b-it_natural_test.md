# Agent eval: `openai:gemma-4-26b-a4b-it` on `natural_test` (120 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **75.8%** |
| Tool selection (action) accuracy | 89.2% |
| Tool execution success (correct DB effect) | **76.5%** |
| Invalid tool-call rate (args rejected by validator) | 3.8% |
| Turns needing self-repair | 2.5% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.023 |
| Latency p50 / p95 | 2270 ms / 4492 ms |
| Tokens per turn (in / out) | 2448 / 41 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 50.0% / 100.0% |
| Invalid requests declined (n=12) | 100.0% (reason correct 83.3%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 86.1% |
| dropoff | 86.1% |
| pickup_at | 79.5% |
| passengers | 86.1% |
| vehicle_type | 79.1% |
| ride_id | 91.7% |
| missing | 40.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 120 | 75.8% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 1 | 0.0% |
| ambiguous_place | 4 | 0.0% |
| bare_hour | 3 | 66.7% |
| booking_distractor | 2 | 100.0% |
| chat_speak | 6 | 100.0% |
| correction | 9 | 77.8% |
| distractor_number | 2 | 50.0% |
| distractor_place | 2 | 100.0% |
| distractor_time | 7 | 71.4% |
| emoji | 4 | 75.0% |
| explicit_id | 3 | 100.0% |
| hinglish | 16 | 81.2% |
| implicit_pickup | 5 | 20.0% |
| indirect | 8 | 87.5% |
| long_context | 6 | 66.7% |
| multiturn | 8 | 37.5% |
| passenger_arithmetic | 13 | 76.9% |
| quote_then_book | 1 | 0.0% |
| relative_time | 7 | 100.0% |
| terse | 9 | 66.7% |
| third_party | 1 | 100.0% |
| typo | 7 | 71.4% |
| vehicle_distractor | 2 | 100.0% |
| verbal_time | 4 | 75.0% |
| weekday | 3 | 66.7% |
| word_order | 1 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 9
- `book_ride->decline`: 1
- `book_ride->error`: 2
- `cancel_ride->clarify`: 1
