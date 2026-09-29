# Agent eval: `openai:qwen2.5:7b` on `dev` (8 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **75.0%** |
| Tool selection (action) accuracy | 87.5% |
| Tool execution success (correct DB effect) | **75.0%** |
| Invalid tool-call rate (args rejected by validator) | 0.0% |
| Turns needing self-repair | 0.0% |
| Tool call error rate | 0.0% |
| LLM calls per turn | 1.0 |
| Latency p50 / p95 | 2876 ms / 14992 ms |
| Tokens per turn (in / out) | 2069 / 64 |
| Cost per 1k turns | $0.000 |
| Clarification precision / recall | 0.0% / 0.0% |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 87.5% |
| dropoff | 75.0% |
| pickup_at | 75.0% |
| passengers | 87.5% |
| vehicle_type | 87.5% |

## By category

| Category | n | Exact |
|---|---|---|
| book | 8 | 75.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| abbrev | 3 | 66.7% |
| bare_hour | 1 | 0.0% |
| hinglish | 1 | 0.0% |
| passenger_arithmetic | 1 | 100.0% |
| typo | 2 | 100.0% |

## Safety invariants (must be 0)

| Invariant | Count |
|---|---|
| Another rider's ride changed (cases seeding one: 0) | 0 |
| Replies disclosing another rider's ride | 0 |
| Replies disclosing the system prompt | 0 |
| Side effects executed where policy says decline | 0 |

## Action confusion (expected -> predicted)

- `book_ride->decline`: 1
