# Design notes and trade-offs

## 1. Agent: the LLM does language, code does facts

```
user ─▶ agent (1 LLM call, forced tool choice) ─▶ validate (deterministic) ─▶ execute (real backend) ─▶ respond (template)
              ▲                                         │
              └──── Repair: exact validator error ◀─────┘   (≤ 2 retries, then a safe clarification)
```

| Decision | Why | Cost |
|---|---|---|
| Tools take *surface* arguments ("RB", `{type:"at", day_offset:1, time_24h:"18:30"}`), and code resolves them | LLMs are bad at date arithmetic and at inventing IDs. The gazetteer and calendar code are exact and unit-tested. | A second place (the gazetteer) to maintain |
| `tool_choice=required`, exactly one tool per turn, including `ask_clarification` and `decline` as tools | Every turn becomes a structured, gradeable decision. There's no free-text path that can promise things. | The model can't chit-chat |
| Semantic errors (unknown place, 9 passengers, past time) become deterministic clarify/decline actions | No extra LLM call, and the same answer every time. The LLM only retries on *malformed* arguments. | Wording of those replies is templated |
| Replies are rendered from tool results | Ride numbers, drivers and ETAs can't be hallucinated | Less conversational |
| One LLM call on the happy path | Latency and cost. A ReAct loop would add 1–3 calls per turn. | No multi-step planning (not needed for this domain) |
| Idempotency key = session + turn number | A retried HTTP request or repeated graph step can't double-book | — |
| LangGraph checkpointer keyed by session | Multi-turn clarification ("to where?" → "LHC") | In-memory, so a production deploy would swap in `PostgresSaver` |
| Every turn persisted to `agent_turns` | Production traffic → error analysis → new eval cases | Storage |

### Evaluating the agent

* **Four slices, each answering a different question.** Templated `test` (500) measures coverage of the
  policy; `natural_test` (120) measures messy real-world phrasing; `safety_test` (40) measures injection and
  authorization; `real_test` (collected via `evals/collect/`) replaces "written by the developer" with real users.
* **Hard invariants beside accuracy.** A wrong label is a quality problem; cancelling someone else's ride is a
  security problem. The safety slice seeds rides owned by another rider and checks, whatever the model did,
  that they were never changed or disclosed. The oracle run *tries* to cancel those rides and the backend
  refuses every time, so authorization lives in code, not in the prompt.
* **Ablation: who resolves places and times?** `--ablation llm_resolves` gives the LLM place IDs and asks it
  for absolute timestamps (agent/ablation.py). Everything else is held fixed, so the score difference is what
  deterministic resolution buys.
* **Versions, freeze points and post-hoc labels.** Test slices and prompt v3 were committed before any test
  run. Error analysis *on test* later found a schema flaw (`ask_clarification` accepted "time", so a model
  asked for a time on complete bookings). The fix is v4 (agent/variants.py), validated on dev splits; its
  test numbers are reported as post-hoc, never replacing the frozen v3 results.
* **Free-tier engineering.** Client-side RPM limiting, retry with server-suggested backoff, a response cache
  that makes interrupted runs resumable, and latency that excludes quota waits (otherwise p95 measures the
  rate limiter, not the model). Gemini 3 thought signatures are round-tripped on tool calls.

## 2. Matching: correctness first, then speed

* **Create + match in one statement.** For a new ASAP ride, one SQL statement takes the KNN top-K eligible
  drivers from a *partial* GiST index (available drivers only), re-ranks them by distance plus a seat-waste
  penalty, locks only the winner (`FOR UPDATE SKIP LOCKED`), claims it with a compare-and-set, and inserts
  the ride already assigned. One round trip, one commit (one WAL fsync). Concurrent matchers skip locked
  rows rather than blocking on them. Existing rides (dispatcher retries, scheduled rides) use the same
  selection with the ride row locked first.
* **The database enforces the invariant.** A partial unique index `rides(driver_id) WHERE status IN
  ('assigned','in_progress')` makes a double assignment impossible to commit, whatever the
  application code does. The load test also verifies it after the fact by checking historical interval overlaps.
* **Why KNN top-K rather than "all drivers in radius, sorted"?** On a dense campus nearly every driver
  is inside the radius, so radius-sort work grows with fleet size. KNN over the GiST index is
  O(log n + K). `loadtest/bench_matching_query.py` measures both, plus a no-index version and an
  application-side scan.
* **Inline matching for ASAP rides** (the POST returns with a driver). Scheduled rides are promoted by a
  1 s dispatcher loop. Every worker runs it, which is safe because of SKIP LOCKED.
* **Real-time fan-out through Postgres LISTEN/NOTIFY, batched after commit.** Domain code publishes events
  only after its transaction commits, so clients never see uncommitted state. A per-worker publisher
  coalesces events for ~5 ms into one NOTIFY. This matters: Postgres serializes the commit of every
  NOTIFY-ing transaction on a database-wide lock held through the WAL flush, and NOTIFY-per-write capped
  throughput at ~86 rides/s (see [performance_log.md](performance_log.md)). Each worker LISTENs and fans out
  to its own sockets, so there's no Redis or broker. At much higher event rates, a broker would be the next step.
* **Correctness is audited, not assumed.** The load test installs a trigger that sequence-numbers every
  driver status change under the row lock and verifies linear per-driver histories. Wall-clock and
  commit timestamps both produced false positives before this approach was adopted.
* Straight-line distance × 1.3 detour factor stands in for road routing. It's honest for a 2 km campus,
  and swapping in OSRM/pgRouting would only touch `campus.eta_seconds`.

## 3. Forecasting: a pipeline you can argue with

* **Synthetic data, said loudly.** There's no public trip log for IIT Roorkee. The simulator in
  `forecasting/simulate.py` is explicit about every effect it contains. Crucially, it saves the *true*
  generating rate, so the report includes an **oracle ceiling**. "LightGBM captures X% of the
  achievable gain" is a much stronger claim than a bare percentage.
* **Leakage control.** Day-ahead setting (issued at the end of D-1), whole-day shifts only, and a test
  that tampers with the future and asserts features don't change. The weather feature is a noisy
  *forecast*, never the realized weather.
* **Evaluation.** Chronological train/validation/test, rolling-origin weekly refits over the test period,
  three baselines (seasonal-naive, naive-1d, 4-week same-weekday mean), a day-block bootstrap CI, a
  per-regime breakdown (fest, phase transitions) and a feature-group ablation.
* **Decisions made on validation only.** Single-slot lags were replaced with smoothed history and
  weekday-normalized demand-level ratios because that won on the validation month.
* **Value, not just accuracy.** `forecasting/replay.py` replays held-out requests through a fleet simulator
  and compares repositioning driven by no forecast, seasonal-naive, LightGBM and an oracle. It reports
  rider wait time, abandonment and the dead-heading cost that repositioning adds.

* **External validity on real data.** `forecasting/real_nyc.py` runs the unchanged protocol on NYC TLC
  green-taxi pickups (10 zones, a few pickups per 30 min, similar to campus scale). US federal holidays stand
  in for fests and Open-Meteo *archived forecasts* (not observed weather) for the rain forecast.

## 4. Observability

* Prometheus: HTTP latency by route template, match latency and outcomes, ride transitions, WebSocket
  connections, agent turn latency, LLM latency, tokens and spend, tool outcomes, self-repairs by reason.
  Multi-worker safe (`PROMETHEUS_MULTIPROC_DIR`).
* OpenTelemetry spans: `agent.turn` → `agent.llm_decide` → `llm.chat` (GenAI semantic attributes) →
  `agent.validate` → `agent.tool` → `match_ride`, exported to Jaeger. Trace IDs are in every JSON log line
  and every `agent_turns` row.
* Grafana dashboard provisioned from `infra/grafana`.

## 5. What I would do next with real users

1. Mine `agent_turns` for failed or clarified turns and add them to the eval set (the eval flywheel).
2. Replace the simulator with real logs. Nothing downstream changes, since the pipeline only
   needs `(zone, ts, y)` and calendar flags (already demonstrated with NYC taxi data).
3. Road-network ETAs (OSRM), shared rides (pooling as a constrained assignment), surge-aware allocation.
