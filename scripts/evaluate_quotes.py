"""Score quote-fidelity flags against the answer key: python scripts/evaluate_quotes.py

Reads  data/processed/quote-fidelity.jsonl  (produced by scripts/check_quotes.py)
Writes data/processed/quote-evaluation.json

The answer key stores the wording only for altered quotes, so scoring is at
the extracted-quote level: an extracted quote is a positive when it contains
an answer-key `altered_text`; every other extracted quote is a negative
(DATA_DICTIONARY §1 — no other quote was altered). Altered quotes the
extractor never captured count as misses.
"""
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(text: str) -> str:
    text = text.translate(str.maketrans({"“": '"', "”": '"', "’": "'", "‘": "'"}))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def alteration_type(quote: dict) -> str:
    """How the planted edit changed the text: words_added / words_omitted / words_changed."""
    a, b = quote["original_text"].split(), quote["altered_text"].split()
    tags = {tag for tag, *_ in difflib.SequenceMatcher(None, a, b).get_opcodes() if tag != "equal"}
    return {"insert": "words_added", "delete": "words_omitted"}.get(tags.pop(), "words_changed") if len(tags) == 1 else "mixed"


def prf(c: Counter) -> dict:
    p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    return {**c, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def main() -> None:
    key = {d["doc_id"]: d for d in json.loads((ROOT / "data/benchmark/answer-key.json").read_text())}
    path = ROOT / "data/processed/quote-fidelity.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found — run  python scripts/check_quotes.py  first.")
    results = {r["doc_id"]: r["quotes"] for r in map(json.loads, path.read_text().splitlines()) if r}
    if set(results) != set(key):
        raise SystemExit("quote-fidelity.jsonl must cover every answer-key document")

    # Counters per slice: overall, by passage kind, and high severity only.
    slices: defaultdict[str, Counter] = defaultdict(Counter)
    by_alteration: defaultdict[str, Counter] = defaultdict(Counter)
    misses, false_positives = [], []
    fp_status: Counter[str] = Counter()
    for doc_id, doc in key.items():
        altered = [q for q in doc["quotes"] if q["quote_status"] == "altered"]
        hit = {}
        for r in results[doc_id]:
            match = next((i for i, q in enumerate(altered) if norm(q["altered_text"]) in norm(r["quote"])), None)
            groups = ("overall", f"kind:{r['kind']}")
            if match is not None:
                # Several passages can cover one altered quote; it counts once, as caught if any flags it.
                hit[match] = hit.get(match, False) or r["flagged"]
                if r["flagged"] and r["severity"] == "high":
                    hit[(match, "high")] = True
                continue
            outcome = "fp" if r["flagged"] else "tn"
            for g in groups:
                slices[g][outcome] += 1
            if r["flagged"] and r["severity"] == "high":
                slices["severity:high"]["fp"] += 1
            if r["flagged"]:
                fp_status[r["status"]] += 1
                false_positives.append({"doc_id": doc_id, "condition": doc["condition"], **{
                    k: r[k] for k in ("kind", "status", "severity", "cited_raw", "quote", "matched_text", "diffs")}})
        kinds = {i: {r["kind"] for r in results[doc_id]
                     if norm(q["altered_text"]) in norm(r["quote"]) and r["flagged"]} for i, q in enumerate(altered)}
        for i, q in enumerate(altered):
            caught = hit.get(i, False)
            slices["overall"]["tp" if caught else "fn"] += 1
            slices["severity:high"]["tp" if hit.get((i, "high")) else "fn"] += 1
            by_alteration[alteration_type(q)]["tp" if caught else "fn"] += 1
            for kind in kinds[i] or {"none"}:
                slices[f"caught_by:{kind}"]["tp" if caught else "fn"] += 1
            if not caught:
                reason = "not_extracted" if i not in hit else "extracted_not_flagged"
                misses.append({"doc_id": doc_id, "reason": reason, "altered_text": q["altered_text"]})

    statuses = Counter(r["status"] for quotes in results.values() for r in quotes)
    report = {
        "policy": "Positive = extracted quote containing an answer-key altered_text; all other extracted quotes are negatives.",
        "altered_quotes_in_key": sum(q["quote_status"] == "altered" for d in key.values() for q in d["quotes"]),
        "extracted_quotes": sum(statuses.values()),
        "by_status": dict(statuses),
        "metrics": prf(slices["overall"]),
        "metrics_high_severity_only": prf(slices["severity:high"]),
        "false_positives_by_kind": {k.split(":")[1]: slices[k]["fp"] for k in slices if k.startswith("kind:")},
        "caught_by_kind": {k.split(":")[1]: slices[k]["tp"] for k in slices if k.startswith("caught_by:")},
        "recall_by_alteration_type": {k: prf(c)["recall"] for k, c in by_alteration.items()},
        "altered_by_type": {k: c["tp"] + c["fn"] for k, c in by_alteration.items()},
        "false_positive_status": dict(fp_status),
        "misses": misses,
        "false_positives": false_positives,
    }
    out = ROOT / "data/processed/quote-evaluation.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("misses", "false_positives", "policy")},
                     indent=2))
    print(f"Detailed results: {out}")


if __name__ == "__main__":
    main()
