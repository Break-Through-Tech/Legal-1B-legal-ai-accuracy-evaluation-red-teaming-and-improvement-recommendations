"""Batch-extract all benchmark .docx documents into a single clean JSONL file.

Produces data/processed/documents.jsonl, one line per document: {"doc_id": ..., "text": ...}.
See plans/task-4-clean-standardize-documents.md for scope/rationale.

Run from the repo root:  python scripts/extract_all_documents.py
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extraction import extract_document_text  # noqa: E402

DOCUMENTS_DIR = REPO_ROOT / "data" / "benchmark" / "documents"
MANIFEST_PATH = REPO_ROOT / "data" / "benchmark" / "manifest.json"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "documents.jsonl"


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for entry in manifest["documents"]:
            doc_id = entry["doc_id"]
            docx_path = DOCUMENTS_DIR / f"{doc_id}.docx"
            text = extract_document_text(docx_path)
            out.write(json.dumps({"doc_id": doc_id, "text": text}) + "\n")
            count += 1

    print(f"Wrote {count} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
