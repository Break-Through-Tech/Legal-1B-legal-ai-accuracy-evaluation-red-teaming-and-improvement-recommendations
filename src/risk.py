"""Per-document hallucination risk score.

Each flagged problem contributes a weight by severity, and the weights combine
as independent chances that the document contains an error:

    score = 1 - prod(1 - weight)        over distinct flagged problems

So the score is 0 for a document with no flags, never decreases as problems
are added, and approaches 1. A fabricated authority mentioned several times
in one document counts once (benchmark rule: each distinct normalized
authority is scored once per document); every mention is still flagged.

The weights and thresholds are a policy, not fitted to the benchmark: a
single high-severity problem (one fabricated citation, or one quote whose
change alters the law) already puts a document at "high". The benchmark
could be separated perfectly with a higher threshold (0.84, i.e. two
fabricated citations), but only because 102 of its 103 corrupt documents had
two or more fabrications planted. Real documents with one fake citation are
just as dangerous, so that threshold is deliberately not used. The
evaluation reports the full threshold sweep (src/evaluation/risk.py).
"""
from __future__ import annotations

import math

SEVERITY_WEIGHTS = {"high": 0.6, "medium": 0.3, "low": 0.1}
SEVERITY_ORDER = ["high", "medium", "low"]

# score >= threshold gives that level; anything above 0 is at least "low".
LEVEL_THRESHOLDS = {"medium": 0.3, "high": 0.6}
LEVELS = ["none", "low", "medium", "high"]

# Levels at or above this one count as "flagged document" when the
# risk score is evaluated as a clean/corrupt classifier.
DOCUMENT_FLAG_LEVEL = "medium"

# Plain-English label per (stage, status) for the drivers summary.
_DRIVER_LABELS = {
    ("existence", "Hallucinated"): ("fabricated citation", "fabricated citations"),
    ("quote_fidelity", "material_difference", "quoted"): ("altered quote", "altered quotes"),
    ("quote_fidelity", "material_difference", "unquoted"): ("altered copied passage", "altered copied passages"),
    ("quote_fidelity", "misattributed"): ("quote attributed to the wrong authority",
                                         "quotes attributed to the wrong authority"),
    ("quote_fidelity", "not_found"): ("quote not found in its cited source", "quotes not found in their cited source"),
}


def level_for(score: float | None, thresholds: dict | None = None) -> str:
    thresholds = thresholds or LEVEL_THRESHOLDS
    if score is None:
        return "unknown"
    if score <= 0:
        return "none"
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def problem_key(flag: dict) -> tuple:
    """Flags sharing a key are one problem: the same fabricated authority, or one passage."""
    if flag["stage"] == "existence":
        return ("existence", flag["evidence"].get("authority") or flag["text"].lower())
    return ("quote_fidelity", flag["flag_id"])


def _driver_label(flag: dict) -> tuple[str, str]:
    for key in ((flag["stage"], flag["status"], flag["item_type"]), (flag["stage"], flag["status"])):
        if key in _DRIVER_LABELS:
            return _DRIVER_LABELS[key]
    return ("other issue", "other issues")


def score_document(flags: list[dict], errors: list[dict] | None = None,
                   weights: dict | None = None, thresholds: dict | None = None) -> dict:
    """Risk summary for one document from its flags.

    Returns {score, level, drivers, problems, incomplete}. If text extraction
    failed there is nothing to score: score is None and level is "unknown".
    """
    weights = weights or SEVERITY_WEIGHTS
    errors = errors or []
    if any(e["stage"] == "extract" for e in errors):
        return {"score": None, "level": "unknown", "drivers": ["The document could not be read."],
                "problems": 0, "incomplete": True}

    problems: dict[tuple, dict] = {}
    for flag in flags:
        if not flag["flagged"]:
            continue
        key = problem_key(flag)
        current = problems.get(key)
        if current is None or weights[flag["severity"]] > weights[current["severity"]]:
            problems[key] = flag

    score = 1 - math.prod(1 - weights[f["severity"]] for f in problems.values())

    # Drivers: one line per kind of problem, most severe kind first.
    groups: dict[tuple[str, str], list[dict]] = {}
    for flag in problems.values():
        groups.setdefault(_driver_label(flag), []).append(flag)
    ranked = sorted(groups.items(), key=lambda item: (
        min(SEVERITY_ORDER.index(f["severity"]) for f in item[1]), -len(item[1])))
    drivers = [f"{len(fs)} {single if len(fs) == 1 else plural}" for (single, plural), fs in ranked]
    if errors:
        drivers.append("Some checks could not run; the score may be too low.")

    return {
        "score": round(score, 4),
        "level": level_for(score, thresholds),
        "drivers": drivers,
        "problems": len(problems),
        "incomplete": bool(errors),
    }
