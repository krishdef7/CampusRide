# Agent eval: `openai:gemini-3.5-flash-lite` on `natural_test` (120 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **99.2%** |
| Tool selection (action) accuracy | 100.0% |
| Tool execution success (correct DB effect) | **100.0%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.0 |
| Latency p50 / p95 | 1304 ms / 7805 ms |
| Tokens per turn (in / out) | 2387 / 42 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 100.0% / 100.0% |
| Invalid requests declined (n=12) | 100.0% (reason correct 100.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 100.0% |
| dropoff | 100.0% |
| pickup_at | 100.0% |
| passengers | 100.0% |
| vehicle_type | 100.0% |
| ride_id | 100.0% |
| missing | 90.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 120 | 99.2% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 1 | 100.0% |
| ambiguous_place | 4 | 75.0% |
| bare_hour | 3 | 100.0% |
| booking_distractor | 2 | 100.0% |
| chat_speak | 6 | 100.0% |
| correction | 9 | 100.0% |
| distractor_number | 2 | 100.0% |
| distractor_place | 2 | 100.0% |
| distractor_time | 7 | 100.0% |
| emoji | 4 | 100.0% |
| explicit_id | 3 | 100.0% |
| hinglish | 16 | 100.0% |
| implicit_pickup | 5 | 100.0% |
| indirect | 8 | 100.0% |
| long_context | 6 | 100.0% |
| multiturn | 8 | 100.0% |
| passenger_arithmetic | 13 | 100.0% |
| quote_then_book | 1 | 100.0% |
| relative_time | 7 | 100.0% |
| terse | 9 | 100.0% |
| third_party | 1 | 100.0% |
| typo | 7 | 100.0% |
| vehicle_distractor | 2 | 100.0% |
| verbal_time | 4 | 100.0% |
| weekday | 3 | 100.0% |
| word_order | 1 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- none
