"""Aggregate accuracy scorecard for the detector.

    card = scorecard(answer_key_rows, reports)       # dict, JSON-serializable
    print(render_markdown(card))                     # tables for the README/report
    diff = compare(card_before, card_after)          # before/after regression view

Headline numbers carry 95% bootstrap confidence intervals over documents.
Every number states its counting policy; slices with fewer than LOW_N
items are marked so nobody over-reads them.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from src.evaluation import adapters
from src.evaluation.existence import evaluate_existence
from src.evaluation.extraction import evaluate_extraction
from src.evaluation.metrics import bootstrap_ci, counts_statistic, prf, roc_auc
from src.evaluation.quotes import evaluate_quotes, quote_recall_by_origin
from src.evaluation.risk import classify_at, document_labels, evaluate_risk, split_stability, sweep
from src.evaluation.runtime import runtime_stats
from src.risk import DOCUMENT_FLAG_LEVEL

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSWER_KEY = REPO_ROOT / "data" / "benchmark" / "answer-key.json"
MANIFEST = REPO_ROOT / "data" / "benchmark" / "manifest.json"
# SHA-256 of the frozen answer key (commit b3a8b73) with LF line endings.
# docs/benchmark-freeze-and-label-schema.md records 8ce6f0bc..., the hash of
# the same file checked out with CRLF line endings on Windows.
FROZEN_ANSWER_KEY_SHA256 = "7829926799fccd1e2d6ad4a2546ea28f3609a1888f1132110161c5304aa16f96"
LOW_N = 20

# Facts about the benchmark a reader needs before trusting the numbers.
CAVEATS = [
    "Document-level separation is easier on this benchmark than in real use: 102 of 103 corrupt documents "
    "had two or more fabricated citations planted, so a perfect AUC mostly reflects the planting recipe. "
    "The risk thresholds are a policy (one fabricated citation = high risk), not fitted to this benchmark.",
    "The detector was developed on these 200 documents; there is no untouched test set, so all numbers are "
    "in-sample. The even/odd stability table is a sanity check, not a held-out evaluation.",
    "Fabricated-citation existence is checked against a fixed corpus of Alaska family-law authorities. "
    "Real law outside the corpus would be flagged as fabricated (two known cases are excluded from scoring).",
    "Quote labels are a sample: many passages have no answer-key row, so quote precision counts every "
    "unlabeled flagged passage as a false positive and may understate it.",
    "Bootstrap intervals collapse to a single point at 0% or 100%. With n items and none missed, the "
    "one-sided 95% lower bound is about 1 - 3/n (273 fabricated citations: about 98.9%).",
    "Clean documents can contain natural misquotes; some document 'false alarms' under the corrupt target "
    "are correct catches under the any_error target.",
]
BOOTSTRAP_SAMPLES = 1000


def _metric(id_, label, value, n, policy, ci=None):
    return {"id": id_, "label": label, "value": value, "ci95": ci, "n": n, "policy": policy}


def _per_doc_quote_counts(key_rows, quote_rows) -> list[dict]:
    """Quote TP/FP/FN/TN per document, so the quote metrics can be bootstrapped by document."""
    rows = {r["doc_id"]: r for r in quote_rows}
    counts = []
    for doc in key_rows:
        m = evaluate_quotes([doc], [rows[doc["doc_id"]]])["metrics"]
        counts.append({k: m.get(k, 0) for k in ("tp", "fp", "fn", "tn")})
    return counts


def _slice(name, counts, metric="recall"):
    n = counts.get("tp", 0) + counts.get("fn", 0) if metric == "recall" else sum(
        counts.get(k, 0) for k in ("tp", "fp", "fn", "tn"))
    return {"slice": name, **prf(counts), "n": n, "low_n": n < LOW_N}


def scorecard(key_rows, reports, meta: dict | None = None, bootstrap: int = BOOTSTRAP_SAMPLES) -> dict:
    """Run every evaluator on detector reports and aggregate the results."""
    ci = (lambda units, stat: bootstrap_ci(units, stat, n=bootstrap)) if bootstrap else (lambda *_: None)

    extraction = evaluate_extraction(key_rows, adapters.to_citation_rows(reports), adapters.to_document_rows(reports))
    existence = evaluate_existence(key_rows, adapters.to_verification_rows(reports), expected_documents=len(key_rows))
    quote_rows = adapters.to_quote_rows(reports)
    quotes = evaluate_quotes(key_rows, quote_rows)
    quotes_origin = quote_recall_by_origin(key_rows, quote_rows)
    risk = evaluate_risk(key_rows, reports)
    runtime = runtime_stats(reports)

    # Per-document counts for bootstrap CIs.
    ext_docs = [{"tp": d["matched"], "fn": d["expected"] - d["matched"]} for d in extraction["documents"]]
    exist_docs = [d["end_to_end"] for d in existence["documents"]]
    quote_docs = _per_doc_quote_counts(key_rows, quote_rows)
    labels = document_labels(key_rows)
    risk_units = [(r["risk"]["score"] if r["risk"]["score"] is not None else 1.0, labels[r["doc_id"]])
                  for r in reports]

    e2e = existence["metrics"]["end_to_end"]["overall"]
    verifier = existence["metrics"]["verifier_only"]["overall"]
    q = prf(quotes["metrics"])
    corrupt, any_error = risk["corrupt"], risk["any_error"]
    n_docs = len(reports)

    def risk_auc(target):
        return lambda sample: roc_auc([s for s, _ in sample], [lab[target] for _, lab in sample])

    flag_cut = {"low": 1e-9, **risk["thresholds"]}[DOCUMENT_FLAG_LEVEL]

    def risk_stat(target, name):
        def stat(sample):
            c = Counter()
            for score, lab in sample:
                flagged = classify_at(score, flag_cut)
                c[("tp" if flagged else "fn") if lab[target] else ("fp" if flagged else "tn")] += 1
            return prf(c)[name]
        return stat

    headline = [
        _metric("fabricated_citation_recall", "Fabricated citations caught (recall, end-to-end)",
                e2e["recall"], e2e["tp"] + e2e["fn"],
                "Unique fabricated authority per document; unextracted fabrications count as misses.",
                ci(exist_docs, counts_statistic("recall"))),
        _metric("fabricated_citation_precision", "Fabricated-citation flags that were right (precision)",
                e2e["precision"], e2e["tp"] + e2e["fp"], "Unique authority per document.",
                ci(exist_docs, counts_statistic("precision"))),
        _metric("fabricated_citation_f1", "Fabricated citations F1", e2e["f1"], e2e["tp"] + e2e["fp"] + e2e["fn"],
                "Unique authority per document.", ci(exist_docs, counts_statistic("f1"))),
        _metric("verifier_only_recall", "Fabricated citations caught, given they were extracted",
                verifier["recall"], verifier["tp"] + verifier["fn"],
                "Isolates the existence check from extraction misses."),
        _metric("altered_quote_recall", "Altered quotes caught (recall)", q["recall"], q["tp"] + q["fn"],
                quotes["policy"] + " Planted and natural alterations both count.",
                ci(quote_docs, counts_statistic("recall"))),
        _metric("altered_quote_precision", "Quote flags that were right (precision)", q["precision"],
                q["tp"] + q["fp"], quotes["policy"], ci(quote_docs, counts_statistic("precision"))),
        _metric("altered_quote_f1", "Altered quotes F1", q["f1"], q["tp"] + q["fp"] + q["fn"], quotes["policy"],
                ci(quote_docs, counts_statistic("f1"))),
        _metric("document_recall_corrupt", f"Corrupt documents flagged (risk >= {DOCUMENT_FLAG_LEVEL})",
                corrupt["operating_point"]["recall"], corrupt["positives"], risk["policy"],
                ci(risk_units, risk_stat("corrupt", "recall"))),
        _metric("document_precision_corrupt", "Flagged documents that were corrupt (precision)",
                corrupt["operating_point"]["precision"], corrupt["operating_point"]["tp"] + corrupt["operating_point"]["fp"],
                risk["policy"], ci(risk_units, risk_stat("corrupt", "precision"))),
        _metric("document_f1_corrupt", "Document-level F1 (clean vs corrupt)", corrupt["operating_point"]["f1"],
                n_docs, risk["policy"], ci(risk_units, risk_stat("corrupt", "f1"))),
        _metric("document_auc_corrupt", "Risk score ROC-AUC (clean vs corrupt)", corrupt["auc"], n_docs,
                "Ranking quality of the score, independent of thresholds.", ci(risk_units, risk_auc("corrupt"))),
        _metric("document_f1_any_error", "Document-level F1 (any labeled error, incl. natural misquotes)",
                any_error["operating_point"]["f1"], n_docs, risk["policy"],
                ci(risk_units, risk_stat("any_error", "f1"))),
        _metric("extraction_recall", "Citations extracted (recall)", extraction["metrics"]["overall"]["recall"],
                extraction["metrics"]["overall"]["expected"], extraction["matching_policy"],
                ci(ext_docs, counts_statistic("recall"))),
        _metric("runtime_median_ms", "Median time per document (ms)", runtime["per_doc_ms"]["median"], n_docs,
                "Wall time of Detector.check, corpus already loaded."),
        _metric("runtime_p95_ms", "95th percentile time per document (ms)", runtime["per_doc_ms"]["p95"], n_docs,
                "Wall time of Detector.check, corpus already loaded."),
        _metric("error_rate", "Documents with a pipeline error", runtime["error_rate"], n_docs,
                "Share of documents where any stage raised."),
    ]

    slices = {
        "existence_by_type": [_slice(g.split(":", 1)[1], c) for g, c in sorted(existence["metrics"]["end_to_end"].items())
                              if g.startswith("type:")],
        "existence_by_fabrication": [_slice(g.split(":", 1)[1], c) for g, c in
                                     sorted(existence["metrics"]["end_to_end"].items()) if g.startswith("fabrication:")],
        "quotes_by_alteration": [{"slice": k, "recall": quotes["recall_by_alteration_type"][k], "n": n,
                                  "low_n": n < LOW_N} for k, n in sorted(quotes["altered_by_type"].items())],
        "quotes_by_origin": [{"slice": k, **v, "n": v["tp"] + v["fn"], "low_n": v["tp"] + v["fn"] < LOW_N}
                             for k, v in quotes_origin.items()],
        "quotes_high_severity_only": quotes["metrics_high_severity_only"],
        "extraction_by_type": [{"slice": g.split(":", 1)[1], "recall": c["recall"], "n": c["expected"],
                                "low_n": c["expected"] < LOW_N}
                               for g, c in sorted(extraction["metrics"].items()) if g.startswith("type:")],
        "risk_at_level": {t: risk[t]["at_level"] for t in ("corrupt", "any_error")},
        "risk_documents_by_level": {t: risk[t]["documents_by_level"] for t in ("corrupt", "any_error")},
        "risk_split_stability": split_stability(key_rows, reports),
    }

    failures = {
        "missed_fabrications": dict(Counter(m["reason"] for m in existence["missed_fabrications"])),
        "false_fabrication_flags": dict(Counter(m["reason"] for m in existence["false_positives"])),
        "missed_altered_quotes": dict(Counter(m["reason"] for m in quotes["misses"])),
        "false_quote_flags_by_status": quotes["false_positive_status"],
        "false_quote_flags_by_kind": quotes["false_positives_by_kind"],
        "extraction_misses": extraction["miss_reasons"],
        "missed_corrupt_documents": [d["doc_id"] for d in corrupt["missed"]],
        "false_alarm_documents": [d["doc_id"] for d in corrupt["false_alarms"]],
    }

    return {
        "meta": {**(meta or {}), "documents": n_docs, "bootstrap_samples": bootstrap,
                 "document_flag_level": DOCUMENT_FLAG_LEVEL, "low_n": LOW_N},
        "caveats": CAVEATS,
        "headline": headline,
        "slices": slices,
        "failures": failures,
        "details": {"extraction": extraction, "existence": existence, "quotes": quotes,
                    "quotes_by_origin": quotes_origin, "risk": risk,
                    "risk_sweep": {t: sweep(key_rows, reports, t) for t in ("corrupt", "any_error")},
                    "runtime": runtime},
    }


# --------------------------------------------------------------------------- #
# Rendering and comparison
# --------------------------------------------------------------------------- #

def _fmt(value, pct=True):
    if value is None:
        return "n/a"
    if isinstance(value, float) and pct and 0 <= value <= 1:
        return f"{value:.1%}"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return str(value)


def _is_rate(metric_id):
    return not metric_id.startswith("runtime")


def render_markdown(card: dict) -> str:
    meta = card["meta"]
    lines = ["# Detector accuracy scorecard", ""]
    lines.append(f"Documents: {meta['documents']}. Git commit: `{meta.get('git', {}).get('commit') or 'n/a'}`"
                 f"{' (uncommitted changes)' if meta.get('git', {}).get('dirty') else ''}. "
                 f"Answer key matches frozen hash: {meta.get('answer_key_frozen', 'n/a')}. "
                 f"Confidence intervals: {meta['bootstrap_samples']} document-level bootstrap resamples.")
    lines += ["", "## Headline", "", "| Metric | Value | 95% CI | n |", "|---|---|---|---|"]
    for m in card["headline"]:
        rate = _is_rate(m["id"])
        ci = f"{_fmt(m['ci95'][0], rate)} – {_fmt(m['ci95'][1], rate)}" if m["ci95"] else ""
        lines.append(f"| {m['label']} | {_fmt(m['value'], rate)} | {ci} | {m['n']} |")

    def table(title, rows, cols):
        out = ["", f"### {title}", "", "| " + " | ".join(c for c, _ in cols) + " |", "|" + "---|" * len(cols)]
        for row in rows:
            cells = [_fmt(row.get(k)) if k != "slice" else row["slice"] + (" *(low n)*" if row.get("low_n") else "")
                     for _, k in cols]
            out.append("| " + " | ".join(cells) + " |")
        return out

    s = card["slices"]
    lines += ["", "## Slices"]
    lines += table("Fabricated citations by citation type", s["existence_by_type"],
                   [("Type", "slice"), ("Recall", "recall"), ("Precision", "precision"), ("n fabricated", "n")])
    lines += table("Fabricated citations by injection type", s["existence_by_fabrication"],
                   [("Injection", "slice"), ("Recall", "recall"), ("n", "n")])
    lines += table("Altered quotes by alteration type", s["quotes_by_alteration"],
                   [("Alteration", "slice"), ("Recall", "recall"), ("n", "n")])
    lines += table("Altered quotes by origin", s["quotes_by_origin"],
                   [("Origin", "slice"), ("Recall", "recall"), ("n", "n")])
    lines += table("Citation extraction by type", s["extraction_by_type"],
                   [("Type", "slice"), ("Recall", "recall"), ("n", "n")])
    for target in ("corrupt", "any_error"):
        rows = [{"slice": lvl, **v} for lvl, v in s["risk_at_level"][target].items()]
        lines += table(f"Document flagging by minimum risk level (target: {target})", rows,
                       [("Flag at", "slice"), ("Recall", "recall"), ("Precision", "precision"), ("F1", "f1")])
    rows = [{"slice": half, **v["corrupt"]} for half, v in s["risk_split_stability"].items()]
    lines += table("Stability: even vs odd documents (target: corrupt)", rows,
                   [("Half", "slice"), ("Recall", "recall"), ("Precision", "precision"), ("F1", "f1")])

    lines += ["", "## Failures", ""]
    for name, value in card["failures"].items():
        if isinstance(value, list):
            value = f"{len(value)}" + (f": {', '.join(value[:15])}{' …' if len(value) > 15 else ''}" if value else "")
        elif isinstance(value, dict):
            value = ", ".join(f"{k}: {v}" for k, v in value.items()) or "none"
        lines.append(f"- **{name.replace('_', ' ')}**: {value}")
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in CAVEATS]
    lines += ["", "## Counting policies", ""]
    seen = set()
    for m in card["headline"]:
        if m["policy"] not in seen:
            seen.add(m["policy"])
            lines.append(f"- {m['policy']}")
    return "\n".join(lines) + "\n"


def compare(before: dict, after: dict) -> dict:
    """Headline metrics side by side with the change, for before/after regression runs."""
    old = {m["id"]: m for m in before["headline"]}
    rows = []
    for m in after["headline"]:
        prev = old.get(m["id"], {}).get("value")
        delta = m["value"] - prev if isinstance(m["value"], (int, float)) and isinstance(prev, (int, float)) else None
        rows.append({"id": m["id"], "label": m["label"], "before": prev, "after": m["value"], "delta": delta})
    return {"before": before["meta"], "after": after["meta"], "metrics": rows}


def render_compare_markdown(diff: dict) -> str:
    lines = ["# Detector before/after", "", "| Metric | Before | After | Change |", "|---|---|---|---|"]
    for r in diff["metrics"]:
        rate = _is_rate(r["id"])
        delta = "" if r["delta"] is None else (f"{r['delta']:+.1%}" if rate else f"{r['delta']:+,.1f}")
        lines.append(f"| {r['label']} | {_fmt(r['before'], rate)} | {_fmt(r['after'], rate)} | {delta} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# File I/O wrapper
# --------------------------------------------------------------------------- #

def load_answer_key(path: Path = ANSWER_KEY) -> tuple[list[dict], dict]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()  # line-ending independent
    return json.loads(raw), {"answer_key_sha256": digest, "answer_key_frozen": digest == FROZEN_ANSWER_KEY_SHA256}


def match_benchmark_reports(reports, manifest: Path = MANIFEST) -> tuple[list[dict], list[str]]:
    """Split reports into benchmark documents (by file hash) and everything else.

    Matching on the .docx SHA-256 rather than the file name means an unrelated
    file called doc-0001.docx is never scored against doc-0001's answer key,
    and a renamed benchmark copy is still recognised. Matched reports are
    returned under their benchmark doc_id; a document seen twice is scored once.
    """
    documents = json.loads(Path(manifest).read_text(encoding="utf-8"))["documents"]
    by_hash = {d["docx_sha256"]: d["doc_id"] for d in documents}
    matched, unscored, seen = [], [], set()
    for report in reports:
        doc_id = by_hash.get(report.get("source_sha256"))
        if doc_id is None or doc_id in seen:
            unscored.append(report["doc_id"])
            continue
        seen.add(doc_id)
        matched.append(report if report["doc_id"] == doc_id else {**report, "doc_id": doc_id})
    return matched, unscored


def write_scorecard(reports, out: Path, run_log: dict | None = None, answer_key: Path = ANSWER_KEY,
                    manifest: Path = MANIFEST) -> dict | None:
    """Score reports and write scorecard.json, scorecard.md and per-evaluator detail files to `out`.

    Only benchmark documents are scored (see match_benchmark_reports); returns
    None and writes nothing when the run contains none.
    """
    out = Path(out)
    key_rows, key_meta = load_answer_key(answer_key)
    reports, unscored = match_benchmark_reports(reports, manifest)
    if not reports:
        return None
    report_ids = {r["doc_id"] for r in reports}
    full = len(report_ids) == len(key_rows)
    key_rows = [row for row in key_rows if row["doc_id"] in report_ids]
    meta = {**key_meta, "full_benchmark": full, "unscored_documents": unscored}
    if run_log:
        meta.update({"run_id": run_log.get("run_id"), "git": run_log.get("git")})
    card = scorecard(key_rows, reports, meta=meta)
    details = card.pop("details")
    for name, payload in details.items():
        (out / f"{name.replace('_', '-')}-evaluation.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "scorecard.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "scorecard.md").write_text(render_markdown(card), encoding="utf-8")
    card["details"] = details
    return card
