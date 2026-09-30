# Agent eval: `openai:qwen2.5:7b` on `dev` (100 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **82.0%** |
| Tool selection (action) accuracy | 84.0% |
| Tool execution success (correct DB effect) | **88.2%** |
| Invalid tool-call rate (args rejected by validator) | 10.7% |
| Turns needing self-repair | 9.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.12 |
| Latency p50 / p95 | 10076 ms / 17076 ms |
| Tokens per turn (in / out) | 2528 / 55 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 36.4% / 33.3% |
| Invalid requests declined (n=12) | 75.0% (reason correct 66.7%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 91.7% |
| dropoff | 90.0% |
| pickup_at | 92.0% |
| passengers | 93.3% |
| vehicle_type | 93.3% |
| ride_id | 93.8% |
| missing | 33.3% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 38 | 92.1% |
| cancel | 7 | 85.7% |
| clarify | 11 | 36.4% |
| decline | 11 | 72.7% |
| handwritten | 10 | 90.0% |
| multiturn | 7 | 57.1% |
| quote | 9 | 100.0% |
| status | 7 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 15 | 93.3% |
| bare_hour | 1 | 0.0% |
| capacity | 3 | 100.0% |
| explicit_id | 6 | 100.0% |
| hinglish | 11 | 90.9% |
| multiturn | 8 | 62.5% |
| out_of_area | 3 | 100.0% |
| out_of_scope | 4 | 25.0% |
| passenger_arithmetic | 7 | 100.0% |
| relative_time | 2 | 100.0% |
| same_place | 1 | 100.0% |
| terse | 1 | 100.0% |
| typo | 5 | 80.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->clarify`: 3
- `book_ride->decline`: 1
- `cancel_ride->clarify`: 1
- `clarify->book_ride`: 8
- `decline->clarify`: 3
