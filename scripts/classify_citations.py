"""Classify verified citations: python scripts/classify_citations.py.

Consumes the corpus-backed output from scripts/verify_citations.py and keeps
the per-document JSONL structure for downstream fidelity and risk scoring.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.classify import classify, explain_reason  # noqa: E402

INPUT_FILE = ROOT / "data" / "processed" / "verification.jsonl"
OUTPUT_FILE = ROOT / "data" / "processed" / "classified-citations.jsonl"


def main():
    counts = {}
    document_count = 0

    if not INPUT_FILE.exists():
        raise SystemExit(
            f"Input file not found: {INPUT_FILE}\n"
            "Run  python scripts/verify_citations.py  first."
        )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with INPUT_FILE.open(encoding="utf-8") as src, OUTPUT_FILE.open("w", encoding="utf-8") as dst:
        for line_no, line in enumerate(src, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("doc_id"):
                raise SystemExit(f"Missing 'doc_id' in verification.jsonl at line {line_no}")

            classified = []
            for citation in record.get("citations", []):
                exists = citation.get("exists")
                label = classify(exists)
                counts[label] = counts.get(label, 0) + 1
                classified.append({
                    **citation,
                    "classification": label,
                    "reason": explain_reason(exists, label),
                })

            dst.write(json.dumps(
                {"doc_id": record["doc_id"], "citations": classified},
                ensure_ascii=False,
            ) + "\n")
            document_count += 1

    print(f"Documents written: {document_count}")
    print(f"Citations classified: {sum(counts.values())}")
    print(f"Output file: {OUTPUT_FILE}")

    print("Classification summary:")
    for label, count in sorted(counts.items()):
        print(f"{label}: {count}")


if __name__ == "__main__":
    main()