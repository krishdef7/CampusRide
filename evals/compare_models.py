"""Collect every agent eval report into one comparison table: evals/reports/agent_model_comparison.md.

    python evals/compare_models.py

Only numbers already written by run_agent_eval.py are used; missing runs show as "–".
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parent / "reports"
SPLITS = [("test", "Templated test (500)"), ("natural_test", "Natural test (120)"), ("safety_test", "Safety test (40)")]
SYSTEMS = [
    ("baseline", "Rule-based baseline (regex + gazetteer)"),
    ("openai_gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite (prompt tuned on its dev runs)"),
    ("openai_gemma-4-26b-a4b-it", "Gemma 4 26B-A4B (open weights, hosted)"),
    ("openai_qwen2.5_7b", "Qwen 2.5 7B (open weights, local RTX 3060 6 GB)"),
    ("oracle", "Oracle (gold tool calls through the harness)"),
]
ABLATIONS = [("openai_qwen2.5_7b", "openai_qwen2.5_7b_llm_resolves", "Qwen 2.5 7B"),
             ("openai_gemma-4-26b-a4b-it", "openai_gemma-4-26b-a4b-it_llm_resolves", "Gemma 4 26B-A4B")]
VARIANTS = [("openai_gemma-4-26b-a4b-it", "openai_gemma-4-26b-a4b-it_v4", "Gemma 4 26B-A4B")]


def load(slug: str, split: str) -> dict | None:
    f = REPORTS / f"agent_eval_{slug}_{split}.json"
    return json.loads(f.read_text()) if f.exists() else None


def pct(x) -> str:
    return "–" if x is None else f"{x:.1%}"


def main() -> None:
    L = ["# Agent: model comparison", "",
         "Exact match = action and every normalized argument equal the label. Latency is per case, excluding",
         "client-side rate-limit waits. All numbers come from the per-run reports in this folder.", ""]
    L += ["| System | " + " | ".join(n for _, n in SPLITS) + " | p50 / p95 latency | Exceptions |",
          "|---|" + "---|" * (len(SPLITS) + 2)]
    for slug, name in SYSTEMS:
        runs = [load(slug, sp) for sp, _ in SPLITS]
        if not any(runs):
            continue
        t = runs[0] or next(r for r in runs if r)
        lat = t.get("latency_ms")
        lat_s = f"{lat['p50'] / 1000:.1f} s / {lat['p95'] / 1000:.1f} s" if lat and slug not in ("oracle",) else (
            "<1 ms" if slug == "baseline" else f"{lat['p50']:.0f} / {lat['p95']:.0f} ms (no LLM)" if lat else "–")
        exc = sum((r or {}).get("exceptions", 0) for r in runs)
        L.append(f"| {name} | " + " | ".join(pct(r and r["intent_exact_match"]) for r in runs) + f" | {lat_s} | {exc} |")

    L += ["", "## Safety invariants (safety_test; must be 0)", "",
          "| System | Another rider's ride changed | Disclosed | System prompt disclosed | Executed where policy says decline |",
          "|---|---|---|---|---|"]
    for slug, name in SYSTEMS:
        r = load(slug, "safety_test")
        if r and "safety" in r:
            s = r["safety"]
            L.append(f"| {name} | {s['unauthorized_mutations']} / {s['cases_with_foreign_rides']} | "
                     f"{s['foreign_data_disclosures']} | {s['system_prompt_disclosures']} | {s['policy_bypasses']} |")

    rows = []
    for base, abl, name in ABLATIONS:
        for sp, spn in SPLITS:
            a, b = load(base, sp), load(abl, sp)
            if a and b:
                rows.append(f"| {name} | {spn} | {pct(a['intent_exact_match'])} | {pct(b['intent_exact_match'])} | "
                            f"{(a['intent_exact_match'] - b['intent_exact_match']) * 100:+.1f} pts |")
    if rows:
        L += ["", "## Ablation: deterministic resolution vs LLM-resolved places and times", "",
              "`llm_resolves`: the LLM returns place IDs and absolute timestamps itself; everything else is identical.", "",
              "| Model | Split | Code resolves (production) | LLM resolves | Gain from code |", "|---|---|---|---|---|", *rows]

    rows = []
    for base, var, name in VARIANTS:
        for sp in ("dev", "natural_dev", "safety_dev", "natural_test"):
            a, b = load(base, sp), load(var, sp)
            if a and b:
                rows.append(f"| {name} | {sp} | {pct(a['intent_exact_match'])} | {pct(b['intent_exact_match'])} |"
                            + (" post-hoc (test seen) |" if sp.endswith("test") else " clean |"))
    if rows:
        L += ["", "## Prompt v4 candidate (found by test error analysis; validated on dev)", "",
              "| Model | Split | v3 (frozen) | v4 | Status |", "|---|---|---|---|---|", *rows]
    (REPORTS / "agent_model_comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
