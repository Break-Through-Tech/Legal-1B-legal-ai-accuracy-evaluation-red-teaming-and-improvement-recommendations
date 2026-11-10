"""Document-level evaluation of the risk score: does it separate clean from corrupt documents?

Two ground truths are reported:

  corrupt    — the document had errors planted (answer-key `condition`). This
               is the benchmark's primary clean-vs-corrupt question.
  any_error  — the document contains any labeled error: a fabricated citation
               (excluding the known out-of-corpus statute) or any altered quote,
               planted or natural. 23 "clean" documents carry natural misquotes,
               so a detector that finds them is right under this target and
               "wrong" under `corrupt`.
"""
from __future__ import annotations

from src.evaluation.existence import EXCLUDED, identity
from src.evaluation.metrics import prf, roc_auc
from src.risk import DOCUMENT_FLAG_LEVEL, LEVEL_THRESHOLDS, LEVELS

TARGETS = ("corrupt", "any_error")


def document_labels(key_rows) -> dict[str, dict]:
    labels = {}
    for doc in key_rows:
        fabricated = any(not c["exists"] and (doc["doc_id"], identity(c)) not in EXCLUDED for c in doc["citations"])
        altered = any(q["quote_status"] == "altered" for q in doc["quotes"])
        labels[doc["doc_id"]] = {"corrupt": doc["condition"] == "corrupt", "any_error": fabricated or altered,
                                 "fabricated_citation": fabricated, "altered_quote": altered}
    return labels


def _score(report) -> float:
    # An unreadable document is treated as the riskiest outcome, not silently as clean.
    score = report["risk"]["score"]
    return 1.0 if score is None else score


def _rows(key_rows, reports, doc_ids=None):
    labels = document_labels(key_rows)
    by_id = {r["doc_id"]: r for r in reports}
    if set(labels) != set(by_id):
        raise ValueError("Reports must cover exactly the answer-key documents")
    ids = sorted(doc_ids if doc_ids is not None else labels)
    return [(i, labels[i], by_id[i]) for i in ids]


def classify_at(score: float, threshold: float) -> bool:
    return score > 0 and score >= threshold


def confusion_at(rows, target: str, threshold: float) -> dict:
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for _, label, report in rows:
        predicted = classify_at(_score(report), threshold)
        positive = label[target]
        counts[("tp" if predicted else "fn") if positive else ("fp" if predicted else "tn")] += 1
    return counts


def evaluate_risk(key_rows, reports, doc_ids=None, thresholds: dict | None = None,
                  flag_level: str = DOCUMENT_FLAG_LEVEL) -> dict:
    """AUC, P/R/F1 at each level cut, the operating point, and misclassified documents."""
    thresholds = thresholds or LEVEL_THRESHOLDS
    rows = _rows(key_rows, reports, doc_ids)
    cuts = {"low": 1e-9, "medium": thresholds["medium"], "high": thresholds["high"]}
    result = {
        "policy": ("Unit = document. Positive = target label true. A document is flagged when its risk "
                   f"level is '{flag_level}' or higher; unreadable documents score 1.0."),
        "documents": len(rows),
        "thresholds": thresholds,
        "flag_level": flag_level,
    }
    for target in TARGETS:
        scores = [_score(r) for _, _, r in rows]
        labels = [label[target] for _, label, _ in rows]
        levels = {lvl: {"positive": 0, "negative": 0} for lvl in [*LEVELS, "unknown"]}
        for (_, label, report) in rows:
            levels[report["risk"]["level"]]["positive" if label[target] else "negative"] += 1
        operating = confusion_at(rows, target, cuts[flag_level])
        result[target] = {
            "positives": sum(labels),
            "negatives": len(labels) - sum(labels),
            "auc": roc_auc(scores, labels),
            "operating_point": prf(operating),
            "at_level": {lvl: prf(confusion_at(rows, target, t)) for lvl, t in cuts.items()},
            "documents_by_level": levels,
            "missed": [_doc_summary(i, label, r) for i, label, r in rows
                       if label[target] and not classify_at(_score(r), cuts[flag_level])],
            "false_alarms": [_doc_summary(i, label, r) for i, label, r in rows
                             if not label[target] and classify_at(_score(r), cuts[flag_level])],
        }
    return result


def _doc_summary(doc_id, label, report) -> dict:
    return {"doc_id": doc_id, "score": report["risk"]["score"], "level": report["risk"]["level"],
            "drivers": report["risk"]["drivers"],
            "labels": {k: v for k, v in label.items() if k not in TARGETS}}


def sweep(key_rows, reports, target: str = "corrupt", doc_ids=None) -> list[dict]:
    """P/R/F1 at every distinct score, for choosing a flag threshold."""
    rows = _rows(key_rows, reports, doc_ids)
    candidates = sorted({_score(r) for _, _, r in rows if _score(r) > 0})
    return [{"threshold": t, **prf(confusion_at(rows, target, t))} for t in candidates]


def split_stability(key_rows, reports, flag_level: str = DOCUMENT_FLAG_LEVEL) -> dict:
    """Operating-point metrics on even- vs odd-numbered documents.

    The thresholds are a policy, not fitted, but a large gap between the
    halves would still show the headline number depends on a few documents.
    """
    ids = sorted(document_labels(key_rows))
    halves = {"even": [i for i in ids if int(i.split("-")[-1]) % 2 == 0],
              "odd": [i for i in ids if int(i.split("-")[-1]) % 2 == 1]}
    return {name: {t: evaluate_risk(key_rows, reports, doc_ids=half, flag_level=flag_level)[t]["operating_point"]
                   for t in TARGETS} for name, half in halves.items()}
