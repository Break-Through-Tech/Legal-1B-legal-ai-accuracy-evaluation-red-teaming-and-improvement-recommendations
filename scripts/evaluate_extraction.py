"""Evaluate saved citation extraction against the benchmark key (no tuning).

Reads  data/processed/citations.jsonl and data/processed/documents.jsonl
Writes data/processed/extraction-evaluation.json
The scoring logic lives in src/evaluation/extraction.py.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.extraction import evaluate_extraction, normalize  # noqa: E402,F401


def read_jsonl(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = {row['doc_id']: row for row in rows}
    if len(rows) != len(result):
        raise ValueError(f"Duplicate document IDs in {path}")
    return result


def main():
    key = json.loads((ROOT / 'data/benchmark/answer-key.json').read_text())
    actual = read_jsonl(ROOT / 'data/processed/citations.jsonl')
    documents = read_jsonl(ROOT / 'data/processed/documents.jsonl')
    result = evaluate_extraction(key, actual, documents)
    path = ROOT / 'data/processed/extraction-evaluation.json'
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'metrics': result['metrics'], 'miss_reasons': result['miss_reasons']}, indent=2))
    print(f'Detailed results: {path}')


if __name__ == '__main__':
    main()
