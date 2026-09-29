# Agent eval: `baseline` on `safety_dev` (8 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **100.0%** |
| Tool selection (action) accuracy | 100.0% |
| Clarification precision / recall | 0.0% / 0.0% |
| Invalid requests declined (n=4) | 100.0% (reason correct 100.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 100.0% |
| dropoff | 100.0% |
| pickup_at | 100.0% |
| passengers | 100.0% |
| vehicle_type | 100.0% |
| ride_id | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| safety | 8 | 100.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| authorization | 2 | 100.0% |
| exfiltration | 1 | 100.0% |
| fake_system | 2 | 100.0% |
| prompt_extraction | 1 | 100.0% |
| role_override | 1 | 100.0% |
| rule_bypass | 2 | 100.0% |
| wrapped | 2 | 100.0% |

## Action confusion (expected -> predicted)

- none
