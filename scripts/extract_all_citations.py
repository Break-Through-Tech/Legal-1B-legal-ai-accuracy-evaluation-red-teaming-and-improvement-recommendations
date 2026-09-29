"""Extract all cleaned documents: python scripts/extract_all_citations.py.

Writes citations.jsonl plus an indented citations-summary.json in data/processed.
Also writes readable per-document JSON files in data/processed/citations/.
No answer-key labels or corpus lookups are used during extraction.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.citation_extractor import extract_citations


def main():
    processed = REPO_ROOT / "data/processed"
    with (processed / "documents.jsonl").open(encoding="utf-8") as source:
        documents = [json.loads(line) for line in source if line.strip()]
    manifest = json.loads((REPO_ROOT / "data/benchmark/manifest.json").read_text(encoding="utf-8"))
    expected_ids = {item["doc_id"] for item in manifest["documents"]}
    actual_ids = [item["doc_id"] for item in documents]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise SystemExit("Cleaned document IDs must match the manifest exactly, without duplicates.")

    results = []
    totals = Counter()
    for document in documents:
        text = document["text"]
        citations = extract_citations(text)
        for citation in citations:
            start, end = citation["start"], citation["end"]
            if not (0 <= start < end <= len(text)) or text[start:end] != citation["raw_text"]:
                raise ValueError(f"Invalid citation position in {document['doc_id']}")
        counts = Counter(item["type"] for item in citations)
        totals.update(counts)
        results.append({
            "doc_id": document["doc_id"],
            "offset_basis": "Zero-based character offsets in cleaned text; end is exclusive.",
            "summary": {"total_mentions": len(citations), "by_type": dict(counts)},
            "citations": citations,
        })

    output = processed / "citations.jsonl"
    individual_outputs = processed / "citations"
    individual_outputs.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as destination:
        for result in results:
            destination.write(json.dumps(result, ensure_ascii=False) + "\n")
            (individual_outputs / f"{result['doc_id']}.citations.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    summary = {
        "total_documents": len(results),
        "total_mentions": sum(totals.values()),
        "by_type": dict(totals),
        "documents_without_citations": [item["doc_id"] for item in results if not item["citations"]],
        "validation": "Document IDs match manifest; all citation text offsets verified.",
        "limitations": "Counts include repeats. Extraction accuracy and citation existence are not evaluated here. Short-form cases, lowercase party-name connectors, and other reporters are not supported.",
        "documents": [{"doc_id": item["doc_id"], **item["summary"]} for item in results],
    }
    (processed / "citations-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: summary[key] for key in ("total_documents", "total_mentions", "by_type")}, indent=2))
    print(f"Results: {output}")
    print(f"Readable files: {individual_outputs}")
    print(f"Summary: {processed / 'citations-summary.json'}")


if __name__ == "__main__":
    main()
