"""Turn a Google Forms CSV export into an eval split (evals/data/agent_eval_real_test.jsonl).

Each non-empty answer becomes one case: the participant's message is the turn, the scenario is the label.
Answers are kept verbatim; nothing is corrected or filtered except empty cells.

    python evals/collect/import_responses.py responses.csv
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from make_form import NOW

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "data" / "agent_eval_real_test.jsonl"


def main(path: str) -> None:
    scen = {s["id"]: s for s in json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))}
    cases = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row_i, row in enumerate(csv.DictReader(f)):
            for col, answer in row.items():
                m = re.match(r"\[(S\d{3})\]", col or "")
                if not m or not (answer or "").strip():
                    continue
                s = scen[m.group(1)]
                setup = {}
                if s.get("needs_ride"):  # respondents type the scenario's booking number, so every case seeds that id
                    setup = {"rides": [{"id": s["ride_id"], "pickup": "rajendra", "dropoff": "lhc", "status": "scheduled"}]}
                cases.append({"id": f"real-{s['id']}-{row_i:03d}", "split": "real_test", "category": "real",
                              "tags": [s["expected"]["action"]], "now": NOW.isoformat(), "turns": [answer.strip()],
                              "setup": setup, "expected": s["expected"], "scenario": s["id"]})
    OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    print(f"{len(cases)} real cases from {path} -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
