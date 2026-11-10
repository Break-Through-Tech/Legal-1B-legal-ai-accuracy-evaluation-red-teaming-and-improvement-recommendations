"""End-to-end hallucination detector: extract -> verify -> classify -> quote check.

Single-document API (what a frontend upload handler calls):

    from src.detect import Detector
    detector = Detector()                      # loads the corpus once
    report = detector.check(upload_bytes, filename="brief.docx")

`check` accepts a path, raw bytes or a binary file-like object, never raises
for a bad document, and returns a JSON-serializable report:

    {doc_id, source_sha256, risk, summary, flags, errors, runtime, text?}

Each citation and each quoted or copied passage gets exactly one flag,
including clean ones (flagged=False). See docs/detector.md for the schema.

Batch run over the benchmark (or any folder of .docx files):

    python scripts/detect.py [doc-0001 ...] [--input DIR] [--out DIR] [--evaluate]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import platform
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.citation_extractor import extract_citations
from src.classify import HALLUCINATED, WRONG_CASE_NAME, WRONG_YEAR, classify, explain_reason
from src.extraction import extract_document_text
from src.quote_fidelity import QuoteSourceIndex, check_document
from src.risk import score_document
from src.verifier import case_detail_mismatches, load_corpus, lookup_citation

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "data" / "benchmark"
DEFAULT_OUT = REPO_ROOT / "data" / "processed" / "detect"
LOG_DIR = REPO_ROOT / "logs"

STAGES = ("extract", "verify", "classify", "quote_check")
CONTEXT_BEFORE, CONTEXT_AFTER = 120, 60

log = logging.getLogger("detect")

_TYPE_NAMES = {"statute": "statute", "rule": "court rule", "case": "case"}

# Quote statuses from src/quote_fidelity.py, in plain English for the user.
_QUOTE_MESSAGES = {
    "verified": "Matches the source word for word.",
    "minor_differences": "Matches the source apart from minor punctuation or formatting.",
    "paraphrased": "Paraphrases the source without changing what it says.",
    "material_difference": "The wording differs from the source in a way that changes its meaning.",
    "misattributed": "This text is not in the cited authority; it comes from {source}.",
    "found_elsewhere": "The cited authority could not be found, but this text appears in {source}.",
    "not_found": "This quote could not be found in the cited authority; it may be altered or invented.",
    "source_unavailable": "The source text for the cited authority is not available, so this quote was not checked.",
    "no_source_match": "Not matched to any legal source (usually testimony or a party's own words).",
}


def authority_key(citation: dict) -> str:
    """Normalized authority identity, so repeated mentions count as one problem."""
    from src.evaluation.existence import identity
    try:
        return "|".join(str(part) for part in identity(citation))
    except (ValueError, KeyError):
        return citation.get("raw_text", "").strip().lower()


def _citation_message(citation: dict, label: str) -> str:
    name = _TYPE_NAMES.get(citation.get("type"), "authority")
    if label == HALLUCINATED:
        return (f"This {name} was not found in the Alaska law corpus. It may be fabricated; "
                "check it before relying on it.")
    if citation.get("exists") == "out_of_scope":
        return f"This {name} is real Alaska law outside this tool's corpus, so it was not checked."
    return f"This {name} was found in the Alaska law corpus."


def _quote_message(result: dict) -> str:
    source = (result.get("matched_source") or {}).get("citation") or "another authority"
    message = _QUOTE_MESSAGES.get(result["status"], "Checked against the cited source.")
    if result["kind"] == "unquoted" and result["status"] == "material_difference":
        message = f"Text copied from {source} was changed in a way that alters what the law says."
    return message.format(source=source)


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - CONTEXT_BEFORE):end + CONTEXT_AFTER]


def _read_bytes(file) -> bytes:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    if isinstance(file, (str, Path)):
        return Path(file).read_bytes()
    if hasattr(file, "read"):
        data = file.read()
        return data if isinstance(data, bytes) else data.encode()
    raise TypeError(f"Unsupported input: {type(file).__name__}")


class Detector:
    """Loads the corpus and quote index once; `check` is then stateless per document."""

    def __init__(self, corpus=None):
        start = time.perf_counter()
        self.corpus = corpus if corpus is not None else load_corpus()
        corpus_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        self.quote_index = QuoteSourceIndex(self.corpus)
        self.setup_ms = {"corpus_load_ms": round(corpus_ms, 1),
                         "quote_index_ms": round((time.perf_counter() - start) * 1000, 1)}

    def check(self, file, filename: str | None = None, doc_id: str | None = None,
              include_text: bool = True, include_unquoted: bool = True) -> dict:
        """Run every stage on one .docx and return its report. Never raises for bad input."""
        total_start = time.perf_counter()
        runtime: dict[str, float] = {}
        errors: list[dict] = []
        name = filename or (str(file) if isinstance(file, (str, Path)) else None)
        doc_id = doc_id or (Path(name).stem if name else "upload")

        def run(stage, fn, timer=None):
            # `timer` lets a sub-step report its own error stage while its time
            # still counts toward a parent stage in `runtime`.
            timer = timer or stage
            start = time.perf_counter()
            try:
                return fn()
            except Exception as error:  # noqa: BLE001 - every stage failure is reported, not raised
                # The traceback goes to the log only; reports may be shown to end users.
                errors.append({"stage": stage, "type": type(error).__name__, "message": str(error)})
                log.debug("%s failed at %s:\n%s", doc_id, stage, traceback.format_exc())
                return None
            finally:
                runtime[f"{timer}_ms"] = round(runtime.get(f"{timer}_ms", 0)
                                               + (time.perf_counter() - start) * 1000, 2)

        raw = run("extract", lambda: _read_bytes(file))
        sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
        text = run("extract", lambda: extract_document_text(io.BytesIO(raw))) if raw is not None else None
        # Its own error stage: the text was read, so a failure here must not
        # make the whole document "unknown" (src/risk.py keys that on "extract").
        citations = (run("extract_citations", lambda: extract_citations(text), timer="extract")
                     if text is not None else None)

        citation_flags: list[dict] = []
        if citations is not None:
            verified = run("verify", lambda: [{**c, **lookup_citation(c, self.corpus)} for c in citations])
            if verified is not None:
                citation_flags = run("classify", lambda: self._citation_flags(verified, text, self.corpus)) or []

        quote_flags: list[dict] = []
        if text is not None:
            results = run("quote_check", lambda: check_document(text, self.quote_index, include_unquoted))
            if results is not None:
                quote_flags = run("quote_check",
                                  lambda: self._quote_flags(results, text, citation_flags)) or []

        flags = sorted(citation_flags + quote_flags, key=lambda f: (f["start"], f["stage"]))
        report = {
            "doc_id": doc_id,
            "filename": name,
            "source_sha256": sha,
            "risk": score_document(flags, errors),
            "summary": _summary(flags),
            "flags": flags,
            "errors": errors,
            "runtime": {"total_ms": round((time.perf_counter() - total_start) * 1000, 2),
                        **{f"{s}_ms": runtime.get(f"{s}_ms", 0.0) for s in STAGES}},
        }
        if include_text:
            report["text"] = text
        return report

    @staticmethod
    def _citation_flags(verified: list[dict], text: str, corpus=None) -> list[dict]:
        flags = []
        for n, c in enumerate(verified, 1):
            label = classify(c["exists"])
            flagged = label == HALLUCINATED
            severity = "high" if flagged else None
            message, reason = _citation_message(c, label), explain_reason(c["exists"], label)
            # A real reporter cite under another case's name is still a fabrication.
            records = [corpus["by_id"][i] for i in c["corpus_ids"] if i in corpus["by_id"]] if corpus else []
            mismatches = case_detail_mismatches(c, records) if c["exists"] == "true" else []
            fields_wrong = {m["field"]: m for m in mismatches}
            if "case_name" in fields_wrong:
                m = fields_wrong["case_name"]
                label, flagged, severity = WRONG_CASE_NAME, True, "high"
                message = (f"{c.get('reporter_cite')} is {m['corpus']}, not {m['cited']}. The case name may be "
                           "fabricated or attached to the wrong citation; check it before relying on it.")
                reason = "Reporter citation exists in the corpus but belongs to a differently named case."
            elif "year" in fields_wrong:
                m = fields_wrong["year"]
                label, flagged, severity = WRONG_YEAR, True, "low"
                message = f"This case was decided in {m['corpus']}, not {m['cited']}."
                reason = "Case found in the corpus, but the cited year does not match."
            fields = {k: v for k, v in c.items() if k not in ("exists", "corpus_ids", "matched_citations")}
            flags.append({
                "flag_id": f"c{n}",
                "stage": "existence",
                "item_type": "citation",
                "citation_type": c["type"],
                "text": c["raw_text"],
                "start": c["start"],
                "end": c["end"],
                "context": _context(text, c["start"], c["end"]),
                "status": label,
                "flagged": flagged,
                "severity": severity,
                "message": message,
                "reason": reason,
                "evidence": {
                    "exists": c["exists"],
                    "corpus_ids": c["corpus_ids"],
                    "matched_citations": c["matched_citations"],
                    "mismatches": mismatches,
                    "authority": authority_key(c),
                    "citation": fields,
                },
            })
        return flags

    @staticmethod
    def _quote_flags(results: list[dict], text: str, citation_flags: list[dict]) -> list[dict]:
        flags = []
        top_level = {"kind", "quote", "start", "end", "context", "status", "flagged", "severity"}
        for n, r in enumerate(results, 1):
            evidence = {k: v for k, v in r.items() if k not in top_level}
            if r["status"] == "found_elsewhere":
                # The citation itself is flagged by the existence stage; link to it, don't count twice.
                related = [f for f in citation_flags if f["flagged"] and f["text"] == r.get("cited_raw")
                           and f["start"] <= r["end"]]
                evidence["related_flag"] = related[-1]["flag_id"] if related else None
            flags.append({
                "flag_id": f"q{n}",
                "stage": "quote_fidelity",
                "item_type": r["kind"],
                "text": r["quote"],
                "start": r["start"],
                "end": r["end"],
                "context": r.get("context") or _context(text, r["start"], r["end"]),
                "status": r["status"],
                "flagged": r["flagged"],
                "severity": r["severity"],
                "message": _quote_message(r),
                "reason": r["status"].replace("_", " "),
                "evidence": evidence,
            })
        return flags


def _summary(flags: list[dict]) -> dict:
    citations = [f for f in flags if f["stage"] == "existence"]
    quotes = [f for f in flags if f["stage"] == "quote_fidelity"]
    severity = Counter(f["severity"] for f in flags if f["flagged"])
    return {
        "citations": len(citations),
        "citations_flagged": sum(f["flagged"] for f in citations),
        "quotes": len(quotes),
        "quotes_flagged": sum(f["flagged"] for f in quotes),
        "by_severity": {s: severity.get(s, 0) for s in ("high", "medium", "low")},
    }


# --------------------------------------------------------------------------- #
# Batch run
# --------------------------------------------------------------------------- #

def _git_state() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def _documents(args) -> list[tuple[str, Path]]:
    # Positional .docx paths: check those files directly (a brand-new document).
    files = [Path(a) for a in args.doc_ids if a.lower().endswith(".docx")]
    if files:
        if len(files) != len(args.doc_ids) or args.input:
            raise SystemExit("Give either .docx paths or benchmark document ids (with optional --input), not both.")
        missing = [str(p) for p in files if not p.is_file()]
        if missing:
            raise SystemExit(f"File not found: {', '.join(missing)}")
        return [(p.stem, p) for p in files]
    if args.input:
        folder = Path(args.input)
        if not folder.is_dir():
            raise SystemExit(f"Input folder not found: {folder}")
        # Any capitalisation of .docx; skip Word's "~$" lock files.
        paths = sorted(p for p in folder.iterdir()
                       if p.is_file() and p.suffix.lower() == ".docx" and not p.name.startswith("~$"))
        if not paths:
            raise SystemExit(f"No .docx files in {folder}")
        docs = [(p.stem, p) for p in paths]
    else:
        manifest = json.loads((BENCHMARK_DIR / "manifest.json").read_text(encoding="utf-8"))
        docs = [(d["doc_id"], BENCHMARK_DIR / d["file"]) for d in manifest["documents"]]
    if args.doc_ids:
        wanted = set(args.doc_ids)
        unknown = wanted - {doc_id for doc_id, _ in docs}
        if unknown:
            raise SystemExit(f"Unknown document ids: {', '.join(sorted(unknown))}")
        docs = [d for d in docs if d[0] in wanted]
    return docs


def _setup_logging(run_id: str) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"detect-{run_id}.log"
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logfile = logging.FileHandler(log_path, encoding="utf-8")
    logfile.setLevel(logging.DEBUG)
    logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(console)
    log.addHandler(logfile)
    return log_path


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def run_batch(args) -> dict:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    log_path = _setup_logging(run_id)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    docs = _documents(args)
    log.info("run %s: %d documents -> %s", run_id, len(docs), out)
    detector = Detector()
    log.info("corpus loaded in %.0f ms, quote index built in %.0f ms",
             detector.setup_ms["corpus_load_ms"], detector.setup_ms["quote_index_ms"])

    wall_start = time.perf_counter()
    reports = []
    with (out / "reports.jsonl").open("w", encoding="utf-8") as report_file, \
            (out / "flags.jsonl").open("w", encoding="utf-8") as flag_file:
        for i, (doc_id, path) in enumerate(docs, 1):
            report = detector.check(path, doc_id=doc_id, include_unquoted=not args.quoted_only)
            reports.append(report)
            report_file.write(json.dumps(report, ensure_ascii=False) + "\n")
            for flag in report["flags"]:
                flag_file.write(json.dumps({"doc_id": doc_id, **flag}, ensure_ascii=False) + "\n")
            s, risk = report["summary"], report["risk"]
            log.info("[%d/%d] %s risk=%s (%s) %.0f ms cites %d/%d quotes %d/%d%s",
                     i, len(docs), doc_id, risk["level"], risk["score"], report["runtime"]["total_ms"],
                     s["citations_flagged"], s["citations"], s["quotes_flagged"], s["quotes"],
                     f" ERRORS: {[e['stage'] for e in report['errors']]}" if report["errors"] else "")
            if args.show:
                for flag in report["flags"]:
                    if flag["flagged"]:
                        log.info("    %-6s %s: %s", flag["severity"], flag["text"][:80], flag["message"])
    wall_s = time.perf_counter() - wall_start

    run_log = _run_log(run_id, started, args, detector, reports, wall_s, log_path)
    (out / "run-log.json").write_text(json.dumps(run_log, indent=2) + "\n", encoding="utf-8")
    log.info("done: %d docs in %.1f s, %d failed. Run log: %s",
             len(reports), wall_s, run_log["documents"]["failed"], out / "run-log.json")

    if args.evaluate:
        from src.evaluation.scorecard import write_scorecard
        card = write_scorecard(reports, out, run_log=run_log)
        if card is None:
            log.warning("--evaluate: no benchmark documents in this run (matched by file hash); "
                        "no scorecard written.")
        else:
            skipped = card["meta"]["unscored_documents"]
            log.info("scorecard: %d benchmark documents scored%s -> %s", card["meta"]["documents"],
                     f", {len(skipped)} other documents not scored" if skipped else "", out / "scorecard.md")
    return run_log


def _run_log(run_id, started, args, detector, reports, wall_s, log_path) -> dict:
    per_doc = [r["runtime"]["total_ms"] for r in reports]
    failed = [r for r in reports if r["errors"]]
    flag_counts = Counter((f["stage"], f["severity"]) for r in reports for f in r["flags"] if f["flagged"])
    return {
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "git": _git_state(),
        "python": platform.python_version(),
        "args": {k: v for k, v in vars(args).items()},
        "setup": detector.setup_ms,
        "documents": {"total": len(reports), "ok": len(reports) - len(failed), "failed": len(failed)},
        "runtime": {
            "wall_s": round(wall_s, 2),
            "per_doc_ms": {"mean": round(statistics.mean(per_doc), 1) if per_doc else None,
                           "median": round(statistics.median(per_doc), 1) if per_doc else None,
                           "p95": _percentile(per_doc, 95), "max": max(per_doc, default=None)},
            "stage_total_ms": {s: round(sum(r["runtime"][f"{s}_ms"] for r in reports), 1) for s in STAGES},
        },
        "items": {"citations": sum(r["summary"]["citations"] for r in reports),
                  "quotes": sum(r["summary"]["quotes"] for r in reports)},
        "flags": {f"{stage}:{severity}": n for (stage, severity), n in sorted(flag_counts.items())},
        "risk_levels": dict(Counter(r["risk"]["level"] for r in reports)),
        "errors": [{"doc_id": r["doc_id"], **{k: e[k] for k in ("stage", "type", "message")}}
                   for r in failed for e in r["errors"]],
        "log_file": str(log_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the hallucination detector over many documents.")
    parser.add_argument("doc_ids", nargs="*",
                        help="benchmark document ids, or paths to any .docx files to check (default: all benchmark docs)")
    parser.add_argument("--show", action="store_true", help="print every flagged item under its document")
    parser.add_argument("--input", help="folder of .docx files (default: the benchmark manifest)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output folder")
    parser.add_argument("--quoted-only", action="store_true", help="skip unquoted (copied) passage detection")
    parser.add_argument("--evaluate", action="store_true", help="score the run against the answer key")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any document had an error")
    args = parser.parse_args(argv)
    run_log = run_batch(args)
    return 1 if args.strict and run_log["documents"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
