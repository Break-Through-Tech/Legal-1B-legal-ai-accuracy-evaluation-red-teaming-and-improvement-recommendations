"""Evaluate corpus existence predictions; false existence is the positive class.

Reads  data/processed/verification.jsonl  (produced by scripts/verify_citations.py)
Writes data/processed/existence-evaluation.json
The scoring logic lives in src/evaluation/existence.py.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.existence import EXCLUDED, evaluate, identity, indexed, metrics  # noqa: E402,F401


def main():
    path = ROOT / 'data/processed/verification.jsonl'
    if not path.exists():
        raise SystemExit('Run scripts/verify_citations.py first')
    report = evaluate(json.loads((ROOT / 'data/benchmark/answer-key.json').read_text()),
                      [json.loads(line) for line in path.read_text().splitlines() if line.strip()])
    output = ROOT / 'data/processed/existence-evaluation.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'coverage': report['coverage'], 'metrics': report['metrics'],
                      'audit_counts': {k: len(report[k]) for k in ('exclusions', 'false_positives', 'missed_fabrications', 'unmatched_extractions', 'abstentions', 'conflicting_predictions')}}, indent=2))
    print(f'Detailed results: {output}')


if __name__ == '__main__':
    main()
