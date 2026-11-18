"""Unified detection metrics: one matching rule from detector flags to answer-key errors.

The stage evaluators (existence.py, quotes.py) each score their own stage's
intermediate output. This module scores what a user actually sees, the
`flagged` items in a detector report, against every labeled error in the
answer key, so citations and quotes are counted under one rule:

Targets (positives), one per error:
  fabricated_citation  one per distinct authority per document with answer-key
                       `exists: false` (excluding the known real out-of-corpus
                       statutes, existence.EXCLUDED). Error type = `injected`.
  altered_quote        one per answer-key quote with `quote_status: altered`.
                       Error type = planted_altered_quote / natural_misquote.

Matching:
  A fabricated citation is caught when the same document has a flagged
  existence flag that claims fabrication (status in FABRICATION_STATUSES) with
  the same authority identity (existence.identity: statute section, rule
  family + number, or case reporter cite; repeated mentions count once).
  An altered quote is caught when a flagged passage's normalized text contains
  its normalized `altered_text` (the rule quotes.evaluate_quotes uses).

False positives:
  Every flagged item that matches no labeled error: a fabrication flag on an
  authority labeled real or absent from the key (one per distinct authority),
  or a flagged passage containing no altered_text (one per passage).
  Flags outside the scored statuses (e.g. Wrong Year) are reported in
  `unscored_flags`, never counted as either.

Quote labels are a sample, so quote false positives can include real but
unlabeled changes: precision is a lower bound.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src.classify import HALLUCINATED, WRONG_CASE_NAME
from src.evaluation.existence import EXCLUDED, identity
from src.evaluation.metrics import prf
from src.evaluation.quotes import norm
from src.evaluation.risk import classify_at, document_labels
from src.risk import DOCUMENT_FLAG_LEVEL, LEVEL_THRESHOLDS

FABRICATION_STATUSES = {HALLUCINATED, WRONG_CASE_NAME}
CLASSES = ("fabricated_citation", "altered_quote")

MATCHING_RULE = (
    "Targets: one per distinct fabricated authority per document (answer-key exists=false, known out-of-corpus "
    "real law excluded) and one per labeled altered quote. A fabricated citation is caught by a flagged "
    "existence flag with status Hallucinated or Wrong Case Name on the same authority (statute section, rule "
    "family and number, or case reporter cite). An altered quote is caught by a flagged passage containing its "
    "altered text. Every other flagged item is a false positive (one per distinct authority or passage); "
    "Wrong Year flags are reported but not scored."
)


def _identity(citation: dict):
    try:
        return identity(citation)
    except (ValueError, KeyError, TypeError):
        return ("unparsed", (citation.get("raw_text") or "").strip().lower())


def _citation_targets(doc: dict) -> dict:
    """{identity: error_type} for the document's scored fabricated authorities."""
    targets = {}
    for c in doc["citations"]:
        ident = identity(c)
        if c["exists"] or (doc["doc_id"], ident) in EXCLUDED:
            continue
        targets.setdefault(ident, c.get("injected") or "fabricated_unlabeled")
    return targets


def match_document(doc: dict, report: dict) -> dict:
    """Match one report's flags to one answer-key document. Returns targets, false positives and other flags."""
    doc_id = doc["doc_id"]
    flags = [f for f in report["flags"] if f["flagged"]]
    targets, false_positives, unscored = [], [], []

    # Citations: fabrication-claiming flags grouped by authority.
    claimed = defaultdict(list)
    for f in flags:
        if f["stage"] != "existence":
            continue
        if f["status"] in FABRICATION_STATUSES:
            claimed[_identity(f["evidence"]["citation"])].append(f)
        else:
            unscored.append({"doc_id": doc_id, "flag_id": f["flag_id"], "status": f["status"], "text": f["text"]})
    expected = _citation_targets(doc)
    for ident, error_type in expected.items():
        hits = claimed.get(ident, [])
        targets.append({"doc_id": doc_id, "class": "fabricated_citation", "error_type": error_type,
                        "identity": list(ident), "caught": bool(hits),
                        "flag_ids": [f["flag_id"] for f in hits]})
    for ident, hits in claimed.items():
        if ident in expected or (doc_id, ident) in EXCLUDED:
            continue
        labeled_real = any(_identity(c) == ident for c in doc["citations"])
        false_positives.append({"doc_id": doc_id, "class": "fabricated_citation", "identity": list(ident),
                                "status": hits[0]["status"], "item_type": "citation",
                                "reason": "labeled_real" if labeled_real else "not_in_answer_key",
                                "flag_ids": [f["flag_id"] for f in hits], "text": hits[0]["text"]})

    # Quotes: flagged passages against labeled altered text.
    altered = [q for q in doc["quotes"] if q["quote_status"] == "altered"]
    altered_norm = [norm(q["altered_text"]) for q in altered]
    passages = [f for f in flags if f["stage"] == "quote_fidelity"]
    caught_by = defaultdict(list)
    for f in passages:
        text = norm(f["text"])
        matched = [i for i, a in enumerate(altered_norm) if a in text]
        for i in matched:
            caught_by[i].append(f["flag_id"])
        if not matched:
            false_positives.append({"doc_id": doc_id, "class": "altered_quote", "status": f["status"],
                                    "item_type": f["item_type"], "severity": f["severity"],
                                    "reason": "no_labeled_alteration", "flag_ids": [f["flag_id"]],
                                    "text": f["text"]})
    for i, q in enumerate(altered):
        targets.append({"doc_id": doc_id, "class": "altered_quote",
                        "error_type": "planted_altered_quote" if q.get("planted") else "natural_misquote",
                        "caught": bool(caught_by.get(i)), "flag_ids": caught_by.get(i, []),
                        "altered_text": q["altered_text"]})
    return {"targets": targets, "false_positives": false_positives, "unscored_flags": unscored}


def _prf(counts) -> dict:
    """Precision/recall/F1 without tn/accuracy: error matching has no true negatives."""
    return {k: v for k, v in prf(counts).items() if k not in ("tn", "accuracy")}


def _counts(targets, false_positives) -> dict[str, Counter]:
    """TP/FN/FP per class and overall."""
    counts = {name: Counter() for name in ("overall", *CLASSES)}
    for t in targets:
        outcome = "tp" if t["caught"] else "fn"
        counts[t["class"]][outcome] += 1
        counts["overall"][outcome] += 1
    for fp in false_positives:
        counts[fp["class"]]["fp"] += 1
        counts["overall"]["fp"] += 1
    return counts


def clean_false_alarms(key_rows, reports, flag_level: str = DOCUMENT_FLAG_LEVEL,
                       thresholds: dict | None = None) -> dict:
    """Share of clean documents the risk score flags at `flag_level` or higher.

    `clean` is the benchmark condition (nothing planted). `error_free` is the
    stricter subset with no labeled error at all: clean documents can carry
    natural misquotes, and flagging those is a correct catch, not a false alarm.
    """
    thresholds = thresholds or LEVEL_THRESHOLDS
    cut = {"low": 1e-9, **thresholds}[flag_level]
    labels = document_labels(key_rows)
    by_id = {r["doc_id"]: r for r in reports}
    result = {"flag_level": flag_level,
              "policy": (f"Unit = document. A document is flagged when its risk level is '{flag_level}' or higher "
                         "(unreadable documents count as flagged).")}
    for name, keep in (("clean", lambda lab: not lab["corrupt"]), ("error_free", lambda lab: not lab["any_error"])):
        ids = sorted(i for i, lab in labels.items() if keep(lab))
        units = []
        for i in ids:
            score = by_id[i]["risk"]["score"]
            units.append({"doc_id": i, "flagged": classify_at(1.0 if score is None else score, cut)})
        alarms = [u["doc_id"] for u in units if u["flagged"]]
        result[name] = {"documents": len(ids), "false_alarms": len(alarms),
                        "rate": len(alarms) / len(ids) if ids else None, "false_alarm_documents": alarms,
                        "units": units}
    return result


def false_alarm_rate(units: list[dict]) -> float | None:
    """Bootstrap statistic over clean_false_alarms()[...]['units']."""
    return sum(u["flagged"] for u in units) / len(units) if units else None


def evaluate_unified(key_rows, reports) -> dict:
    """Precision/recall/F1 overall, per error class and per error type, plus clean-document false alarms."""
    key = {d["doc_id"]: d for d in key_rows}
    by_id = {r["doc_id"]: r for r in reports}
    if set(key) != set(by_id):
        raise ValueError("Reports must cover exactly the answer-key documents")

    targets, false_positives, unscored, per_doc = [], [], [], []
    for doc_id in sorted(key):
        m = match_document(key[doc_id], by_id[doc_id])
        targets += m["targets"]
        false_positives += m["false_positives"]
        unscored += m["unscored_flags"]
        per_doc.append({"doc_id": doc_id, **{name: dict(c) for name, c in
                                              _counts(m["targets"], m["false_positives"]).items()}})

    counts = _counts(targets, false_positives)
    by_type = defaultdict(Counter)
    for t in targets:
        by_type[(t["class"], t["error_type"])]["tp" if t["caught"] else "fn"] += 1
    fp_by_kind = Counter(f"{fp['class']}:{fp['status']}:{fp['item_type']}" for fp in false_positives)

    return {
        "policy": MATCHING_RULE,
        "metrics": {name: _prf(c) for name, c in counts.items()},
        "by_error_type": [{"class": cls, "error_type": et, **_prf(c), "n": c["tp"] + c["fn"]}
                          for (cls, et), c in sorted(by_type.items())],
        "false_positives_by_kind": dict(fp_by_kind.most_common()),
        "false_positive_reasons": dict(Counter(fp["reason"] for fp in false_positives)),
        "clean_false_alarms": clean_false_alarms(key_rows, reports),
        "documents": per_doc,
        "missed": [t for t in targets if not t["caught"]],
        "false_positives": false_positives,
        "unscored_flags": unscored,
    }
