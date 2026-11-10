"""Score quote-fidelity flags against the answer key: python scripts/evaluate_quotes.py

Reads  data/processed/quote-fidelity.jsonl  (produced by scripts/check_quotes.py)
Writes data/processed/quote-evaluation.json
The scoring logic lives in src/evaluation/quotes.py.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.quotes import alteration_type, evaluate_quotes, norm, prf  # noqa: E402,F401


def main() -> None:
    key = json.loads((ROOT / "data/benchmark/answer-key.json").read_text())
    path = ROOT / "data/processed/quote-fidelity.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found — run  python scripts/check_quotes.py  first.")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    try:
        report = evaluate_quotes(key, rows)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    out = ROOT / "data/processed/quote-evaluation.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("misses", "false_positives", "policy")},
                     indent=2))
    print(f"Detailed results: {out}")


if __name__ == "__main__":
    main()
