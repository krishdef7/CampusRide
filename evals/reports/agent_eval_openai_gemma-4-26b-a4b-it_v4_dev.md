# Agent eval: `openai:gemma-4-26b-a4b-it+v4` on `dev` (100 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **85.0%** |
| Tool selection (action) accuracy | 96.0% |
| Tool execution success (correct DB effect) | **89.5%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 0.991 |
| Latency p50 / p95 | 2602 ms / 5016 ms |
| Tokens per turn (in / out) | 2445 / 38 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 100.0% / 91.7% |
| Invalid requests declined (n=12) | 100.0% (reason correct 100.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 95.0% |
| dropoff | 95.0% |
| pickup_at | 90.0% |
| passengers | 95.0% |
| vehicle_type | 90.0% |
| ride_id | 100.0% |
| missing | 41.7% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 38 | 84.2% |
| cancel | 7 | 100.0% |
| clarify | 11 | 36.4% |
| decline | 11 | 100.0% |
| handwritten | 10 | 90.0% |
| multiturn | 7 | 85.7% |
| quote | 9 | 100.0% |
| status | 7 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 15 | 80.0% |
| bare_hour | 1 | 0.0% |
| capacity | 3 | 100.0% |
| explicit_id | 6 | 100.0% |
| hinglish | 11 | 81.8% |
| multiturn | 8 | 87.5% |
| out_of_area | 3 | 100.0% |
| out_of_scope | 4 | 100.0% |
| passenger_arithmetic | 7 | 85.7% |
| relative_time | 2 | 50.0% |
| same_place | 1 | 100.0% |
| terse | 1 | 100.0% |
| typo | 5 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->decline`: 1
- `book_ride->error`: 1
- `book_ride->get_quote`: 1
- `clarify->decline`: 1
