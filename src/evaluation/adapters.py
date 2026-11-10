"""Convert detector reports (src/detect.py) into the row shapes the evaluators read.

These are the same shapes the stage scripts write to data/processed/*.jsonl,
so evaluating detector output and evaluating the old per-stage files give
the same numbers.
"""
from __future__ import annotations

_QUOTE_TOP_LEVEL = ("kind", "quote", "start", "end", "context", "status", "flagged", "severity")


def _existence(report):
    return [f for f in report["flags"] if f["stage"] == "existence"]


def to_citation_rows(reports) -> dict:
    """{doc_id: {doc_id, citations}}: extractor output (scripts/extract_all_citations.py)."""
    return {r["doc_id"]: {"doc_id": r["doc_id"], "citations": [f["evidence"]["citation"] for f in _existence(r)]}
            for r in reports}


def to_verification_rows(reports) -> list[dict]:
    """[{doc_id, citations}]: verifier output (scripts/verify_citations.py)."""
    return [{"doc_id": r["doc_id"], "citations": [
        {**f["evidence"]["citation"], "exists": f["evidence"]["exists"],
         "corpus_ids": f["evidence"]["corpus_ids"], "matched_citations": f["evidence"]["matched_citations"]}
        for f in _existence(r)]} for r in reports]


def to_quote_rows(reports) -> list[dict]:
    """[{doc_id, quotes}]: quote checker output (scripts/check_quotes.py)."""
    rows = []
    for r in reports:
        quotes = []
        for f in r["flags"]:
            if f["stage"] != "quote_fidelity":
                continue
            evidence = {k: v for k, v in f["evidence"].items() if k != "related_flag"}
            quotes.append({"kind": f["item_type"], "quote": f["text"], "start": f["start"], "end": f["end"],
                           "context": f["context"], **evidence, "status": f["status"],
                           "flagged": f["flagged"], "severity": f["severity"]})
        rows.append({"doc_id": r["doc_id"], "quotes": quotes})
    return rows


def to_document_rows(reports) -> dict:
    """{doc_id: {doc_id, text}}: extracted text (scripts/extract_all_documents.py). Needs include_text."""
    missing = [r["doc_id"] for r in reports if r.get("text") is None]
    if missing:
        raise ValueError(f"Reports lack extracted text (run with include_text=True): {missing[:3]}")
    return {r["doc_id"]: {"doc_id": r["doc_id"], "text": r["text"]} for r in reports}
