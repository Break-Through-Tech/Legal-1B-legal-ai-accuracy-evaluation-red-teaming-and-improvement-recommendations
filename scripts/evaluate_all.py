"""Score a detector run against the frozen answer key: python scripts/evaluate_all.py

Reads  data/processed/detect/reports.jsonl and run-log.json  (from scripts/detect.py)
Writes data/processed/detect/scorecard.json, scorecard.md and *-evaluation.json details

    --compare OLD/scorecard.json   also write compare.md: headline metrics before vs after
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.scorecard import compare, render_compare_markdown, write_scorecard  # noqa: E402

DEFAULT_DIR = ROOT / "data" / "processed" / "detect"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default=str(DEFAULT_DIR), help="folder with reports.jsonl (output goes here too)")
    parser.add_argument("--compare", help="an earlier scorecard.json to compare against")
    args = parser.parse_args()

    run = Path(args.run)
    reports_path = run / "reports.jsonl"
    if not reports_path.exists():
        raise SystemExit(f"{reports_path} not found. Run  python scripts/detect.py  first.")
    reports = [json.loads(line) for line in reports_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    run_log_path = run / "run-log.json"
    run_log = json.loads(run_log_path.read_text()) if run_log_path.exists() else None

    card = write_scorecard(reports, run, run_log=run_log)
    if not card["meta"]["answer_key_frozen"]:
        print("WARNING: answer-key.json does not match the frozen benchmark hash.", file=sys.stderr)
    for m in card["headline"]:
        ci = f"  [{m['ci95'][0]:.3f}, {m['ci95'][1]:.3f}]" if m["ci95"] else ""
        value = "n/a" if m["value"] is None else f"{m['value']:.3f}"
        print(f"{m['label']:<66} {value}{ci}  (n={m['n']})")
    print(f"Scorecard: {run / 'scorecard.md'}")

    if args.compare:
        diff = compare(json.loads(Path(args.compare).read_text()), card)
        (run / "compare.json").write_text(json.dumps(diff, indent=2) + "\n")
        (run / "compare.md").write_text(render_compare_markdown(diff))
        print(f"Comparison: {run / 'compare.md'}")


if __name__ == "__main__":
    main()
