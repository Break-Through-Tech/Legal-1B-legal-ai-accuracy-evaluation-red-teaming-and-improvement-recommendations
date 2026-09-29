"""Extract doc-0001 only for review: python scripts/preview_citations.py."""
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.citation_extractor import extract_citations


def main():
    input_path = REPO_ROOT / "data/processed/documents.jsonl"
    with input_path.open(encoding="utf-8") as source:
        document = next(
            (record for line in source if (record := json.loads(line))["doc_id"] == "doc-0001"),
            None,
        )
    if document is None:
        raise SystemExit("doc-0001 not found in data/processed/documents.jsonl")

    citations = extract_citations(document["text"])
    result = {
        "doc_id": document["doc_id"],
        "offset_basis": "Zero-based character offsets in cleaned text; end is exclusive.",
        "summary": {
            "total_mentions": len(citations),
            "by_type": dict(Counter(citation["type"] for citation in citations)),
        },
        "citations": citations,
    }
    output_path = REPO_ROOT / "data/processed/doc-0001.citations.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"Preview: {output_path}")


if __name__ == "__main__":
    main()
