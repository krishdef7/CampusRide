# Agent eval: `openai:gemini-3.5-flash-lite` on `natural_dev` (30 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **96.7%** |
| Tool selection (action) accuracy | 96.7% |
| Tool execution success (correct DB effect) | **95.8%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.0 |
| Latency p50 / p95 | 1476 ms / 2926 ms |
| Tokens per turn (in / out) | 2383 / 40 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 100.0% / 100.0% |
| Invalid requests declined (n=4) | 100.0% (reason correct 100.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 95.0% |
| dropoff | 95.0% |
| pickup_at | 94.4% |
| passengers | 95.0% |
| vehicle_type | 95.0% |
| ride_id | 100.0% |
| missing | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 30 | 96.7% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| ambiguous_place | 1 | 100.0% |
| booking_distractor | 1 | 100.0% |
| correction | 3 | 66.7% |
| distractor_number | 1 | 100.0% |
| emoji | 1 | 100.0% |
| explicit_id | 2 | 100.0% |
| hinglish | 4 | 100.0% |
| implicit_pickup | 1 | 100.0% |
| indirect | 2 | 100.0% |
| multiturn | 2 | 100.0% |
| passenger_arithmetic | 2 | 100.0% |
| terse | 1 | 100.0% |
| typo | 1 | 100.0% |
| verbal_time | 1 | 100.0% |
| weekday | 1 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->get_quote`: 1
