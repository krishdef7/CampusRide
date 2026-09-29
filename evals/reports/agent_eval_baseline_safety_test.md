# Agent eval: `baseline` on `safety_test` (40 cases)

| Metric | Value |
|---|---|
| Intent exact match (action + all normalized args) | **75.0%** |
| Tool selection (action) accuracy | 77.5% |
| Clarification precision / recall | 22.2% / 100.0% |
| Invalid requests declined (n=20) | 70.0% (reason correct 70.0%) |

## Field accuracy (booking / quote cases)

| Field | Accuracy |
|---|---|
| pickup | 87.5% |
| dropoff | 87.5% |
| pickup_at | 87.5% |
| passengers | 87.5% |
| vehicle_type | 87.5% |
| ride_id | 70.0% |
| missing | 100.0% |

## By category

| Category | n | Exact |
|---|---|---|
| safety | 40 | 75.0% |

## By tag (hard phenomena)

| Tag | n | Exact |
|---|---|---|
| arg_smuggling | 1 | 100.0% |
| authorization | 9 | 66.7% |
| exfiltration | 8 | 50.0% |
| fake_system | 8 | 100.0% |
| harmful | 3 | 100.0% |
| impersonation | 3 | 66.7% |
| indirect_injection | 1 | 0.0% |
| mass_action | 2 | 0.0% |
| multiturn | 1 | 100.0% |
| prompt_extraction | 4 | 75.0% |
| role_override | 5 | 60.0% |
| rule_bypass | 5 | 100.0% |
| social_engineering | 1 | 0.0% |
| sql_injection | 2 | 100.0% |
| template_injection | 1 | 100.0% |
| wrapped | 6 | 83.3% |

## Action confusion (expected -> predicted)

- `book_ride->cancel_ride`: 1
- `decline->cancel_ride`: 1
- `decline->clarify`: 5
- `get_ride_status->clarify`: 2
