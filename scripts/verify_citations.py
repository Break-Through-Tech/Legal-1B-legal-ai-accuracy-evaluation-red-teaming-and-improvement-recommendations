"""Verify extracted citations against the corpus: python scripts/verify_citations.py

Reads  data/processed/citations.jsonl  (produced by scripts/extract_all_citations.py)
Writes data/processed/verification.jsonl — one record per document:
  {
    "doc_id": "doc-0001",
    "citations": [
      { ...all original extractor fields..., "exists": "true" | "false" | "out_of_scope" }
    ]
  }
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.verifier import load_corpus, verify_citation

INPUT = REPO_ROOT / "data" / "processed" / "citations.jsonl"
OUTPUT = REPO_ROOT / "data" / "processed" / "verification.jsonl"


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(
            f"Input file not found: {INPUT}\n"
            "Run  python scripts/extract_all_citations.py  first."
        )

    corpus = load_corpus()

    counts: defaultdict[str, int] = defaultdict(int)
    n_docs = 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with INPUT.open(encoding="utf-8") as src, OUTPUT.open("w", encoding="utf-8") as dst:
        for line_no, line in enumerate(src, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            doc_id = record.get("doc_id")
            if not doc_id:
                raise SystemExit(f"Missing 'doc_id' in citations.jsonl at line {line_no}")
            verified = []
            for citation in record.get("citations", []):
                exists = verify_citation(citation, corpus)
                counts[exists] += 1
                verified.append({**citation, "exists": exists})
            dst.write(json.dumps({"doc_id": doc_id, "citations": verified}, ensure_ascii=False) + "\n")
            n_docs += 1

    print(json.dumps({
        "documents": n_docs,
        "citations_verified": sum(counts.values()),
        "exists_true": counts["true"],
        "exists_false": counts["false"],
        "out_of_scope": counts["out_of_scope"],
    }, indent=2))
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
