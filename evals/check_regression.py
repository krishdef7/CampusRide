"""Fail CI when an eval report drops below a threshold.  python evals/check_regression.py REPORT.json --min-exact 0.9"""

import argparse
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("report")
ap.add_argument("--min-exact", type=float, required=True)
ap.add_argument("--min-tool-success", type=float)
args = ap.parse_args()

r = json.load(open(args.report))
problems = []
if r["intent_exact_match"] < args.min_exact:
    problems.append(f"intent_exact_match {r['intent_exact_match']:.3f} < {args.min_exact}")
if args.min_tool_success is not None and (r.get("tool_execution_success") or 0) < args.min_tool_success:
    problems.append(f"tool_execution_success {r.get('tool_execution_success')} < {args.min_tool_success}")
if problems:
    sys.exit("REGRESSION: " + "; ".join(problems))
print(f"ok: {r['system']} exact={r['intent_exact_match']:.3f}")
