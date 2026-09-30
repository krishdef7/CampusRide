# Agent eval: `openai:qwen2.5:7b+llm_resolves` on `natural_test` (120 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **60.0%** |
| Tool selection (action) accuracy | 82.5% |
| Tool execution success (correct DB effect) | **65.3%** |
| Invalid tool-call rate (args rejected by validator) | 5.9% |
| Turns needing self-repair | 4.2% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.062 |
| Latency p50 / p95 | 11283 ms / 14551 ms |
| Tokens per turn (in / out) | 2482 / 46 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 22.2% / 20.0% |
| Invalid requests declined (n=12) | 66.7% (reason correct 58.3%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 90.7% |
| dropoff | 91.9% |
| pickup_at | 70.5% |
| passengers | 90.7% |
| vehicle_type | 84.9% |
| ride_id | 75.0% |
| missing | 10.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 120 | 60.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 1 | 100.0% |
| ambiguous_place | 4 | 0.0% |
| bare_hour | 3 | 100.0% |
| booking_distractor | 2 | 100.0% |
| chat_speak | 6 | 83.3% |
| correction | 9 | 66.7% |
| distractor_number | 2 | 0.0% |
| distractor_place | 2 | 50.0% |
| distractor_time | 7 | 57.1% |
| emoji | 4 | 75.0% |
| explicit_id | 3 | 100.0% |
| hinglish | 16 | 50.0% |
| implicit_pickup | 5 | 80.0% |
| indirect | 8 | 75.0% |
| long_context | 6 | 83.3% |
| multiturn | 8 | 62.5% |
| passenger_arithmetic | 13 | 61.5% |
| quote_then_book | 1 | 100.0% |
| relative_time | 7 | 28.6% |
| terse | 9 | 44.4% |
| third_party | 1 | 100.0% |
| typo | 7 | 85.7% |
| vehicle_distractor | 2 | 50.0% |
| verbal_time | 4 | 75.0% |
| weekday | 3 | 33.3% |
| word_order | 1 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 1 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 3
- `book_ride->decline`: 1
- `book_ride->get_quote`: 1
- `cancel_ride->clarify`: 1
- `clarify->book_ride`: 6
- `clarify->decline`: 1
- `clarify->get_quote`: 1
- `decline->book_ride`: 1
- `decline->clarify`: 3
- `get_quote->decline`: 1
- `get_ride_status->decline`: 1
- `get_ride_status->get_quote`: 1
