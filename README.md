# CampusRide: AI-enabled real-time campus mobility (IIT Roorkee)

An LLM ride-booking agent, a real-time spatial matching backend and a demand-forecasting pipeline
for on-campus e-rickshaws, autos and cabs. Each part has a benchmark behind it: a held-out 500-case
agent eval, a load test with correctness invariants, and a backtested forecast with an ablation and a
dispatch replay.

> **Data honesty.** Place names are real IIT Roorkee landmarks (approximate coordinates). **All rides,
> drivers and demand are simulated.** No real users or trip logs are involved. Every number below
> is produced by a script in this repo, and each report says which data it used.

```
┌──────────────┐  natural language   ┌──────────────────────────────┐   tool call    ┌──────────────────────────┐
│ rider (web / │ ──────────────────▶ │ LangGraph agent              │ ─────────────▶ │ FastAPI + PostGIS         │
│  chat)       │ ◀── reply + WS ──── │ 1 LLM call → validate →      │ ◀───────────── │ KNN matching, atomic claim│
└──────────────┘                     │ execute → templated reply    │                │ LISTEN/NOTIFY → WebSocket │
                                     └──────────────────────────────┘                └───────────▲──────────────┘
                                                                                                  │ zone forecasts
                                      ┌────────────────────────────────────────────┐             │
                                      │ LightGBM day-ahead demand (zone × 30 min)  │ ────────────┘
                                      │ → driver repositioning (Hungarian)         │
                                      └────────────────────────────────────────────┘
  Prometheus metrics · OpenTelemetry traces (Jaeger) · Grafana dashboard · every agent turn logged to Postgres
```

## Results

### 1. LLM agent reliability: 500 held-out labeled requests

| System | Intent exact match | Tool selection | Tool execution success (DB effect) | Invalid requests declined | p50 / p95 latency | Cost / 1k turns |
|---|---|---|---|---|---|---|
| **LLM agent** | *pending: run with an API key* | | | | | |
| Rule-based baseline (regex + gazetteer) | 88.6% | 94.4% | n/a | 90.3% | <1 ms | $0 |
| Oracle (gold tool calls through the harness) | 100.0% | 100.0% | 100.0% | 100.0% | 92 ms / 183 ms (non-LLM overhead) | $0 |

The baseline is deliberately strong. Its rules were refined while looking at test failures, which makes
any LLM advantage *conservative*. Where it breaks: typos (33% exact), hand-written phrasing (73%), ambiguity
handling (clarification precision 69.5%).

The eval runs the agent **end to end against a real PostGIS database**. "Tool execution success"
means the right row ended up in the right state (ride created with the right places, time,
passengers and vehicle; the right ride cancelled), not merely that a tool call was emitted.
Before any model was evaluated, an oracle run (gold tool calls through the same harness) scored
100.0% on every metric. That shows the labels, validator, executor and scorer are mutually consistent.

Dataset: 455 template-generated cases (labels correct by construction; English, Hinglish, abbreviations,
typos, relative, weekday and bare-hour times, passenger arithmetic, multi-turn) plus 45 hand-labeled hard
cases. Prompt iteration used the 100-case dev split only. See [docs/labeling_policy.md](docs/labeling_policy.md).

### 2. Real-time matching: load test and query benchmark

Open-loop Poisson load (no coordinated omission): 1,000 simulated drivers streaming ~200 location
updates/s, rides completed 1–3 s after assignment. API (uvicorn ×4, uvloop), PostGIS and the load generator
all run in Linux containers on one laptop (Ryzen, 16 threads), with durable commits (`synchronous_commit=on`).

**Headline: 10,000 ride requests at ~196 req/s.** 100% success, 100% matched.
Latency p50 **10.9 ms** · p95 **16.8 ms** · p99 **27.5 ms** (client-observed `POST /rides`, which includes
validation, insert, KNN match and atomic claim). WebSocket fan-out (commit → client) p50 **5.8 ms** / p95 **7.9 ms**.
**0 invariant violations across 30,000 audited driver state transitions.**

| Offered load | Achieved | p50 | p95 | p99 | Matched | Violations |
|---|---|---|---|---|---|---|
| 100/s | 102/s | 9.7 ms | 14.3 ms | 25.3 ms | 100% | 0 |
| 200/s | 193/s | 10.4 ms | 14.5 ms | 18.4 ms | 100% | 0 |
| 300/s | 296/s | 11.0 ms | 16.2 ms | 20.6 ms | 100% | 0 |
| 400/s | 388/s | 11.9 ms | 19.1 ms | 26.9 ms | 100% | 0 |
| 500/s | 462/s | 13.5 ms | 26.2 ms | 39.3 ms | 99.0% | 0 |
| 600/s | 587/s | 22.0 ms | 64.4 ms | 77.9 ms | 83.0%* | 0 |

\*Fleet saturation: 1,000 simulated drivers can't serve more. Not a system error.

**Correctness is audited, not assumed.** A load-test trigger sequence-numbers every driver status change
under the row lock. Every per-driver history must be linear (each transition's OLD = previous NEW) and every
claim must follow a release. Getting this check right took two false starts: wall-clock timestamps and
Postgres commit timestamps are *not* total orders under concurrent commits.

**How the numbers were found** ([docs/performance_log.md](docs/performance_log.md)): the first sweep capped
at ~55 req/s because the *load generator* was the bottleneck. Creating and matching in one statement took
sequential latency from 11.6 → 7.3 ms. The big one: `pg_notify` inside write transactions made Postgres
serialize every commit on a database-wide lock through the WAL flush (78 sessions waiting on `Lock:
object`). Batching NOTIFYs after commit raised throughput **~86 → ~590 req/s**.

**Matching query benchmark** (one connection, one claim per rolled-back transaction, 50% of drivers available,
p50 ms; [loadtest/reports/matching_query_bench.md](loadtest/reports/matching_query_bench.md)):

| Dense campus | KNN top-K on partial GiST (production) | Radius + sort all | Same SQL, no index | Scan in Python |
|---|---|---|---|---|
| 1,000 drivers | 0.87 | 2.09 | 2.38 | 2.54 |
| 10,000 drivers | 0.92 | 15.4 | 34.4 | 9.2 |
| 100,000 drivers | **0.98** | 145 (148×) | 411 (419×) | 90 (91×) |

The production query stays ~1 ms from 1k to 100k drivers. Honest caveat: when drivers are spread over a city
and the radius is very selective, plain radius-sort is as fast or faster at small fleets (0.8 vs 1.2 ms at 1k).
KNN wins at 100k (1.0 vs 6.1 ms).

### 3. Demand forecasting: day-ahead, 9 zones × 48 half-hour slots (synthetic data)

Chronological split: train 2025-08-11 → 2026-01-31, validation Feb 2026, test 2026-03-01 → 2026-05-03
(64 days, 27,648 zone-slots). Rolling-origin backtest with weekly refits. Features and hyperparameters
were chosen on validation only.

| Model | MAE | RMSE | WAPE |
|---|---|---|---|
| Seasonal-naive (same slot, last week) | 1.409 | 2.777 | 90.6% |
| Naive (same slot, yesterday) | 1.421 | 2.813 | 91.5% |
| 4-week same-weekday mean | 1.154 | 2.184 | 74.2% |
| **LightGBM (Poisson)** | **1.019** | **1.894** | **65.6%** |
| Oracle (true generating rate) | 0.940 | 1.694 | 60.5% |

* **MAE −27.6% vs seasonal-naive** (95% day-block bootstrap CI 24.1–31.2%), and **−11.7% vs the strongest
  baseline** (CI 8.8–14.6%).
* The simulator records the true demand rate, so the achievable ceiling is known: an oracle is 33.3% better than
  seasonal-naive, which means **LightGBM captures 83% of the achievable gain**. The rest is irreducible count noise.
* Largest gains are where last week is a bad guide: academic phase transitions (−44%) and fests (−28%).
* Ablation (test MAE, one feature group dropped): calendar/events matter most (1.019 → 1.088), then smoothed
  history (→ 1.031), then the rain forecast (→ 1.022).

**Does the forecast create value?** Held-out requests are replayed through a fleet simulator. Idle drivers
are rebalanced every 30 min under different policies (25 e-rickshaws, 21 held-out days):

| Repositioning policy | Mean wait | p90 wait | Dead-head km/day | vs static stands |
|---|---|---|---|---|
| None (stay where the last trip ended) | 2.01 min | 4.06 | 0 | +42.6% |
| Static stands (historical zone share, no ML) | 1.41 min | 3.36 | 198 | — |
| Seasonal-naive forecast | 1.49 min | 3.42 | 507 | +5.7% |
| **LightGBM forecast** | **1.24 min** | **3.04** | 269 | **−12.1%** |
| Oracle (true future demand) | 1.08 min | 2.74 | 481 | −23.4% |

A naive forecast is *worse* than no forecast: it chases noise, with 2.5× the dead-heading of static stands.
LightGBM cuts mean wait 12.1% over the static heuristic (8.7–13.6% across 20–30 vehicle fleets).
Details: [evals/reports/forecast_report.md](evals/reports/forecast_report.md),
[evals/reports/replay_report.md](evals/reports/replay_report.md).

## Engineering decisions (short version, full reasoning in [docs/design.md](docs/design.md))

* **The LLM does language; code does facts.** Tools take surface arguments ("RB", `{type: at, day_offset: 1,
  time_24h: "18:30"}`). A deterministic validator resolves places against a gazetteer, does the calendar
  arithmetic and enforces business rules. Malformed arguments go back to the LLM with the exact error
  (bounded self-repair). Semantic problems (unknown or ambiguous place, 9 passengers, past time) become
  deterministic clarify/decline actions with no extra LLM call. Replies are rendered from tool results,
  so ride facts can't be hallucinated.
* **One LLM call on the happy path** (forced tool choice, `ask_clarification` and `decline` are tools too).
* **Create + match in one SQL statement** (one round trip, one commit): KNN top-K over a partial GiST index
  of available drivers → re-rank by distance plus a seat-waste penalty → `FOR UPDATE SKIP LOCKED` on the winner →
  compare-and-set claim → insert the ride already assigned. A partial unique index makes double assignment
  impossible to commit.
* **Realtime without a broker**: events are published *after* commit, batched per worker into one `NOTIFY`
  every ~5 ms → each worker LISTENs → WebSocket fan-out. Clients only ever see committed state.
* **Idempotent booking** (per-session-turn key + unique index), bounded retries, typed domain errors.

## Observability

* `/metrics` (Prometheus, multi-worker safe): HTTP latency by route, match latency and outcomes, ride
  transitions, open WebSockets, agent turn latency, LLM latency, tokens and USD spend, tool outcomes, self-repairs by reason.
* OpenTelemetry traces: `agent.turn → agent.llm_decide → llm.chat (gen_ai.* attrs) → agent.validate → agent.tool → match_ride`.
* Structured JSON logs carrying `trace_id`. Every agent turn is stored in `agent_turns` (input, tool args, outcome,
  repairs, tokens, latency, trace id) as raw material for new eval cases.
* `docker compose --profile obs up -d` starts Prometheus, Grafana (pre-provisioned dashboard) and Jaeger.

## Run it

```bash
docker compose up -d db                      # PostGIS on :5433
python -m venv .venv && .venv/Scripts/activate   # (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env                         # add an LLM key to enable the agent

pytest -q                                    # 69 tests (unit + PostGIS integration, incl. a 200-way concurrency race)
uvicorn campusride.api.app:create_app --factory --port 8000
python scripts/driver_sim.py --drivers 40    # simulated fleet; open http://localhost:8000 for the live map + chat
```

Reproduce every number:

```bash
python evals/build_dataset.py                          # deterministic; CI checks it's unchanged
python evals/run_agent_eval.py --split test --oracle   # harness sanity check (should be 100%)
python evals/run_agent_eval.py --split test --baseline # rule-based baseline
python evals/run_agent_eval.py --split test            # the LLM agent (uses LLM_* env vars)
python -m campusride.forecasting.pipeline              # forecast backtest + ablation (~3 min)
python -m campusride.forecasting.replay                # dispatch replay
python loadtest/bench_matching_query.py                # query variants × fleet sizes
loadtest/run_in_docker.sh --requests 10000 --rate 200  # API + DB + load generator in containers
loadtest/run_in_docker.sh --sweep 100 200 300 400 500 600 --requests 3000
```

## Layout

```
src/campusride/
  campus.py            gazetteer, fuzzy/ambiguity-aware place resolution, ETA/fare model
  matching.py          single-statement create+match: KNN claim with SKIP LOCKED + compare-and-set
  services.py          ride/driver domain operations, idempotency, guarded state machine
  events.py            post-commit event publishing (batched NOTIFY; see docs/performance_log.md)
  api/app.py           FastAPI routes, dispatcher loop, metrics middleware; api/realtime.py LISTEN/NOTIFY hub
  agent/               schema (tools + Action), validate, graph (LangGraph), llm (cache/cost), baseline, backend
  forecasting/         simulate, features, pipeline (backtest), allocation (Hungarian), replay
evals/                 dataset builder, hand-written cases, runner, regression gate, reports
loadtest/              open-loop load test with invariants, matching query benchmark, reports
infra/                 Prometheus, Grafana provisioning;  docs/  design + labeling policy
```

## Limitations (on purpose, and stated)

* Demand, rides and drivers are simulated, so forecasting results show the pipeline and evaluation
  method, not real IIT Roorkee demand. The oracle ceiling and the static-stands baseline exist to keep claims honest.
* Templated eval language is more regular than real traffic, which is why a regex baseline does well on it.
  The hand-written, typo and ambiguity slices are the better robustness signal.
* Straight-line distance × 1.3 detour factor instead of road routing. The load generator runs on the same machine as the API.
