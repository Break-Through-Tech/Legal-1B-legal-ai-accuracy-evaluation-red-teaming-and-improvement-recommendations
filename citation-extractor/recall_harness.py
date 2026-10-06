"""Measure citation-extraction recall against the benchmark answer key.

Usage
  python recall_harness.py --key answer-key.json --docs path/to/benchmark/documents
  python recall_harness.py --key answer-key.json --proxy      # no .docx available

Scoring rules (from benchmark-exploration.md §3.4, §3.5, §7.1, §7.6):
  * The key lists each citation string once per document, so extractor output is
    deduplicated per document before scoring.
  * Alignment is by canonical citation key (extractors.canonical), never by position.
  * Cases align on the reporter core ("451 P.3d 375"), so the 19 key strings that
    over-captured prose ("The Nelson v. Nelson, ...") still align with a clean extraction.
  * Statute/rule subsections are kept: (a) and (b) are different authorities. A
    "lenient" hit is also reported where only the subsection differs (the 3 key
    entries in §7.6 record a subsection the text does not carry).

--proxy builds one synthetic document per answer-key record by placing each key
string in a sentence that uses the benchmark's own signal phrases (§2.5). It
measures whether the extractor recognizes the citation *formats*; it is not a
substitute for running on the real documents.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from extractors import EXTRACTORS, base_section, canonical, truncate

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx(path: Path) -> str:
    """Body text of a .docx, one paragraph per line (footnotes are empty in this benchmark, §2.1)."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(f"{W}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{W}t" and el.text:
                parts.append(el.text)
            elif el.tag == f"{W}tab":
                parts.append("\t")
            elif el.tag == f"{W}br":
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)


PROXY_TEMPLATES = {
    "statute": [
        "Under {c}, the court must consider the best interests of the child.",
        "Consistent with {c}, the Petitioner requests that relief be granted.",
        "The court should act pursuant to {c} and enter the proposed order.",
        "In accordance with {c}, the Respondent was properly served.",
        "See {c}.",
        "This filing is made as required by {c}.",
    ],
    "rule": [
        "Under {c}, child support is calculated from adjusted annual income.",
        "Consistent with {c}, the Petitioner has filed the required affidavit.",
        "Pursuant to {c}, the parties exchanged financial disclosures.",
        "See {c}.",
    ],
    "case": [
        "{c}. The Alaska Supreme Court held that the trial court must make findings.",
        "The court explained the standard in {c}, and that standard applies here.",
        "See {c} (affirming a custody award).",
    ],
}


def proxy_text(record: dict) -> str:
    sents = [f"IN THE SUPERIOR COURT FOR THE STATE OF ALASKA ({record['doc_id']})", "IV. ARGUMENT"]
    for i, c in enumerate(record["citations"]):
        t = PROXY_TEMPLATES[c["type"]]
        sents.append(t[i % len(t)].format(c=c["cite"]))
    return "\n".join(sents)


# Key case strings that carry leading prose ("In Nelson v. Nelson, ...", "See ...", "The ...").
PROSE_PREFIX_RE = re.compile(r"^(?:[^,]*?\.\s+)?(?:In|See|The|As)\s+(?!re\b)")


def find_verbatim(text: str, cite: str) -> tuple[int, int] | None:
    i = text.find(cite)
    return (i, i + len(cite)) if i >= 0 else None


def score_doc(record: dict, text: str, extractor, depth: int | None = 1) -> dict:
    mentions = extractor(text)
    pred = collections.defaultdict(list)            # canonical -> [mention]
    for m in mentions:
        k = truncate(canonical(m.raw, m.type), depth)
        if k:
            pred[k].append(m)
    pred_base = {base_section(k) for k in pred}

    entries = []
    gold_keys = set()
    for c in record["citations"]:
        key = truncate(canonical(c["cite"], c["type"]), depth)
        gold_keys.add(key)
        span = find_verbatim(text, c["cite"])
        overcaptured = c["type"] == "case" and PROSE_PREFIX_RE.match(c["cite"]) is not None
        if key in pred:
            outcome, reason = "hit", ""
        elif key and base_section(key) in pred_base:
            outcome, reason = "lenient_hit", "subsection differs"
        else:
            outcome = "miss"
            if span is None and not (key and _core_in_text(key, c["type"], text)):
                reason = "key string not in document"
            elif span and any(m.start < span[1] and span[0] < m.end for m in mentions):
                reason = "detected but normalized differently"
            elif c["type"] in ("statute", "rule"):
                reason = f"{c['type']} format not recognized"
            else:
                reason = "case not detected"
        entries.append({
            "doc_id": record["doc_id"], "cite": c["cite"], "type": c["type"], "canonical": key,
            "exists": c["exists"], "injected": c["injected"] or "genuine",
            "overcaptured_key_string": overcaptured, "outcome": outcome, "reason": reason,
            "context": _context(text, span) if outcome == "miss" and span else "",
        })

    gold_base = {base_section(k) for k in gold_keys if k}
    false_pos = [
        {"doc_id": record["doc_id"], "canonical": k, "raw": ms[0].raw, "type": ms[0].type, "mentions": len(ms),
         "kind": "same section keyed with a different subsection" if base_section(k) in gold_base else "authority not in key for this document",
         "context": _context(text, (ms[0].start, ms[0].end))}
        for k, ms in pred.items() if k not in gold_keys
    ]
    return {"entries": entries, "false_positives": false_pos,
            "n_mentions": len(mentions), "n_pred_unique": len(pred), "n_gold_unique": len(gold_keys)}


CORE_RE = re.compile(r"\d{1,4}\s+P\.\s?[23]d\s+\d{1,5}|AS\s+\d+\.\d+\.\d+(?:\([a-z0-9]+\))*|"
                     r"(?:Alaska\s+R\.\s*Evid\.|Civil\s+Rule|Rule)\s+\d+(?:\.\d+)?(?:\([a-z0-9]+\))*")


def _core_in_text(key: str, type_: str, text: str) -> bool:
    """Is the citation's canonical core anywhere in the text, even if the key's exact string is not?"""
    return key in {canonical(t, type_) for t in CORE_RE.findall(text)}


def _context(text: str, span, width: int = 60) -> str:
    s, e = span
    return re.sub(r"\s+", " ", text[max(0, s - width):e + width])


def summarize(results: list[dict]) -> dict:
    entries = [e for r in results for e in r["entries"]]
    fps = [f for r in results for f in r["false_positives"]]

    def rate(rows, lenient=False):
        ok = sum(r["outcome"] == "hit" or (lenient and r["outcome"] == "lenient_hit") for r in rows)
        return {"n": len(rows), "recalled": ok, "recall": round(ok / len(rows), 4) if rows else None}

    by = lambda field: {k: rate([e for e in entries if e[field] == k]) for k in sorted({e[field] for e in entries}, key=str)}
    n_pred = sum(r["n_pred_unique"] for r in results)
    tp_pred = n_pred - len(fps)
    return {
        "documents": len(results),
        "answer_key_entries": len(entries),
        "raw_mentions_extracted": sum(r["n_mentions"] for r in results),
        "unique_predictions_after_per_doc_dedupe": n_pred,
        "recall_strict": rate(entries),
        "recall_lenient_subsection": rate(entries, lenient=True),
        "precision_after_dedupe": round(tp_pred / n_pred, 4) if n_pred else None,
        "false_positive_predictions": len(fps),
        "recall_by_type": by("type"),
        "recall_by_injected": by("injected"),
        "recall_by_exists": by("exists"),
        "overcaptured_key_strings": rate([e for e in entries if e["overcaptured_key_string"]]),
        "miss_reasons": dict(collections.Counter(e["reason"] for e in entries if e["outcome"] == "miss").most_common()),
        "top_missed_strings": collections.Counter(e["cite"] for e in entries if e["outcome"] == "miss").most_common(15),
        "false_positive_kinds": dict(collections.Counter(f["kind"] for f in fps)),
        "top_false_positives": collections.Counter(f["canonical"] for f in fps).most_common(15),
    }


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True, type=Path)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--docs", type=Path, help="folder containing doc-NNNN.docx")
    src.add_argument("--proxy", action="store_true", help="synthetic documents built from the key strings")
    ap.add_argument("--extractors", default=",".join(EXTRACTORS), help="comma-separated: " + ", ".join(EXTRACTORS))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--depth", type=int, default=1,
                    help="subsection levels kept when aligning (answer key uses 1); 0 = section only, -1 = keep all")
    args = ap.parse_args(argv)

    key = json.loads(args.key.read_text())
    mode = "proxy" if args.proxy else "documents"
    texts = {}
    for rec in key:
        if args.proxy:
            texts[rec["doc_id"]] = proxy_text(rec)
        else:
            p = args.docs / f"{rec['doc_id']}.docx"
            if p.exists():
                texts[rec["doc_id"]] = read_docx(p)
    if not args.proxy:
        missing = len(key) - len(texts)
        if not texts:
            sys.exit(f"no doc-NNNN.docx files found in {args.docs}")
        if missing:
            print(f"scoring {len(texts)} documents; {missing} answer-key documents have no .docx in {args.docs}")
        key = [rec for rec in key if rec["doc_id"] in texts]

    all_summaries = {}
    for name in args.extractors.split(","):
        depth = None if args.depth < 0 else args.depth
        results = [score_doc(rec, texts[rec["doc_id"]], EXTRACTORS[name], depth) for rec in key]
        summary = {"mode": mode, "extractor": name, "subsection_depth": args.depth, **summarize(results)}
        out = args.out / mode / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        entries = [e for r in results for e in r["entries"]]
        write_csv(out / "entries.csv", entries)
        write_csv(out / "misses.csv", [e for e in entries if e["outcome"] != "hit"])
        write_csv(out / "false_positives.csv", [f for r in results for f in r["false_positives"]])
        all_summaries[name] = summary
        s = summary
        print(f"[{mode}] {name:13} recall {s['recall_strict']['recall']:.3f} "
              f"(lenient {s['recall_lenient_subsection']['recall']:.3f})  "
              f"precision {s['precision_after_dedupe']}  mentions {s['raw_mentions_extracted']} -> unique {s['unique_predictions_after_per_doc_dedupe']}")
    (args.out / mode / "all_summaries.json").write_text(json.dumps(all_summaries, indent=2))


if __name__ == "__main__":
    main()
