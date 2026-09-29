# Agent eval: `oracle` on `dev` (100 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **100.0%** |
| Tool selection (action) accuracy | 100.0% |
| Tool execution success (correct DB effect) | **100.0%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.0 |
| Latency p50 / p95 | 68 ms / 127 ms |
| Tokens per turn (in / out) | 0 / 0 |
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
| missing | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 38 | 100.0% |
| cancel | 7 | 100.0% |
| clarify | 11 | 100.0% |
| decline | 11 | 100.0% |
| handwritten | 10 | 100.0% |
| multiturn | 7 | 100.0% |
| quote | 9 | 100.0% |
| status | 7 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 15 | 100.0% |
| bare_hour | 1 | 100.0% |
| capacity | 3 | 100.0% |
| explicit_id | 6 | 100.0% |
| hinglish | 11 | 100.0% |
| multiturn | 8 | 100.0% |
| out_of_area | 3 | 100.0% |
| out_of_scope | 4 | 100.0% |
| passenger_arithmetic | 7 | 100.0% |
| relative_time | 2 | 100.0% |
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

- none
