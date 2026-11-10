"""Runtime and reliability statistics over detector reports."""
from __future__ import annotations

import statistics

from src.detect import STAGES


def _pct(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))] if ordered else None


def _describe(values):
    if not values:
        return None
    return {"mean": round(statistics.mean(values), 2), "median": round(statistics.median(values), 2),
            "p95": round(_pct(values, 95), 2), "max": round(max(values), 2)}


def runtime_stats(reports) -> dict:
    """Per-document and per-stage runtime (ms), plus the share of documents with an error."""
    failed = [r["doc_id"] for r in reports if r["errors"]]
    return {
        "documents": len(reports),
        "per_doc_ms": _describe([r["runtime"]["total_ms"] for r in reports]),
        "per_stage_ms": {s: _describe([r["runtime"][f"{s}_ms"] for r in reports]) for s in STAGES},
        "error_rate": len(failed) / len(reports) if reports else None,
        "failed_documents": failed,
    }
