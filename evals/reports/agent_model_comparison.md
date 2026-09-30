# Agent: model comparison

Exact match = action and every normalized argument equal the label. Latency is per case, excluding
client-side rate-limit waits. All numbers come from the per-run reports in this folder.

| System | Templated test (500) | Natural test (120) | Safety test (40) | p50 / p95 latency | Exceptions |
|---|---|---|---|---|---|
| Rule-based baseline (regex + gazetteer) | 88.6% | 65.8% | 75.0% | <1 ms | 0 |
| Gemini 3.5 Flash-Lite (prompt tuned on its dev runs) | – | – | 100.0% | 1.1 s / 1.7 s | 0 |
| Gemma 4 26B-A4B (open weights, hosted) | – | 75.8% | 97.5% | 2.3 s / 4.5 s | 2 |
| Qwen 2.5 7B (open weights, local RTX 3060 6 GB) | 77.8% | 73.3% | 67.5% | 12.4 s / 19.8 s | 1 |
| Oracle (gold tool calls through the harness) | 100.0% | 100.0% | 100.0% | 86 / 172 ms (no LLM) | 0 |

## Safety invariants (safety_test; must be 0)

| System | Another rider's ride changed | Disclosed | System prompt disclosed | Executed where policy says decline |
|---|---|---|---|---|
| Gemini 3.5 Flash-Lite (prompt tuned on its dev runs) | 0 / 12 | 0 | 0 | 0 |
| Gemma 4 26B-A4B (open weights, hosted) | 0 / 12 | 0 | 0 | 0 |
| Qwen 2.5 7B (open weights, local RTX 3060 6 GB) | 0 / 12 | 0 | 0 | 0 |
| Oracle (gold tool calls through the harness) | 0 / 12 | 0 | 0 | 0 |

## Ablation: deterministic resolution vs LLM-resolved places and times

`llm_resolves`: the LLM returns place IDs and absolute timestamps itself; everything else is identical.

| Model | Split | Code resolves (production) | LLM resolves | Gain from code |
|---|---|---|---|---|
| Qwen 2.5 7B | Natural test (120) | 73.3% | 60.0% | +13.3 pts |
| Qwen 2.5 7B | Safety test (40) | 67.5% | 75.0% | -7.5 pts |
