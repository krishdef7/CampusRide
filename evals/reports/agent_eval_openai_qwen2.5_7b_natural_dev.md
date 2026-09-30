# Agent eval: `openai:qwen2.5:7b` on `natural_dev` (30 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **73.3%** |
| Tool selection (action) accuracy | 83.3% |
| Tool execution success (correct DB effect) | **75.0%** |
| Invalid tool-call rate (args rejected by validator) | 13.5% |
| Turns needing self-repair | 10.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.156 |
| Latency p50 / p95 | 12239 ms / 15731 ms |
| Tokens per turn (in / out) | 2609 / 54 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 0.0% / 0.0% |
| Invalid requests declined (n=4) | 100.0% (reason correct 75.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 90.0% |
| dropoff | 90.0% |
| pickup_at | 77.8% |
| passengers | 85.0% |
| vehicle_type | 85.0% |
| ride_id | 75.0% |
| missing | 0.0% |

## By category

| Category | n | Exact |
|---|---|---|
| natural | 30 | 73.3% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| ambiguous_place | 1 | 0.0% |
| booking_distractor | 1 | 100.0% |
| correction | 3 | 66.7% |
| distractor_number | 1 | 100.0% |
| emoji | 1 | 0.0% |
| explicit_id | 2 | 100.0% |
| hinglish | 4 | 75.0% |
| implicit_pickup | 1 | 100.0% |
| indirect | 2 | 50.0% |
| multiturn | 2 | 50.0% |
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

- `book_ride->clarify`: 1
- `book_ride->get_quote`: 1
- `cancel_ride->clarify`: 1
- `clarify->book_ride`: 2
