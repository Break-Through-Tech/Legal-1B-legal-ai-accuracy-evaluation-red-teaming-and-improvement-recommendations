"""Check quoted passages against corpus source text:
    python scripts/check_quotes.py [--quoted-only] [doc-0001 ...]

--quoted-only skips unquoted (borrowed) passage detection.

Reads  data/benchmark/documents/*.docx  (or only the doc ids given)
Writes data/processed/quote-fidelity.jsonl — one record per document:
  {"doc_id": "doc-0001", "quotes": [ {quote, cited_raw, status, flagged, diffs, ...} ]}
Prints a status summary and every flagged quote.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extraction import extract_document_text
from src.quote_fidelity import QuoteSourceIndex, check_document

DOCUMENTS = REPO_ROOT / "data" / "benchmark" / "documents"
OUTPUT = REPO_ROOT / "data" / "processed" / "quote-fidelity.jsonl"


def main() -> None:
    args = sys.argv[1:]
    quoted_only = "--quoted-only" in args
    wanted = [a for a in args if a != "--quoted-only"]
    paths = [DOCUMENTS / f"{d}.docx" for d in wanted] if wanted else sorted(DOCUMENTS.glob("doc-*.docx"))
    index = QuoteSourceIndex()

    statuses: Counter[str] = Counter()
    flagged = []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as dst:
        for path in paths:
            results = check_document(extract_document_text(path), index, include_unquoted=not quoted_only)
            for r in results:
                statuses[r["status"]] += 1
                if r["flagged"]:
                    flagged.append((path.stem, r))
            dst.write(json.dumps({"doc_id": path.stem, "quotes": results}, ensure_ascii=False) + "\n")

    for doc_id, r in flagged:
        print(f"[{r['severity']}] {doc_id} {r['kind']} {r['status']} — cited {r['cited_raw']}")
        print(f"    quote:  {r['quote']}")
        if r["matched_text"]:
            print(f"    source: {r['matched_text']}  ({r['matched_source']['citation']})")
        for d in r["diffs"]:
            if d["material"]:
                print(f"    {d['type']}: quote '{d['quote_text']}' vs source '{d['source_text']}'")
    print(json.dumps({"documents": len(paths), "quotes": sum(statuses.values()),
                      "flagged": len(flagged), "by_status": dict(statuses)}, indent=2))
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
