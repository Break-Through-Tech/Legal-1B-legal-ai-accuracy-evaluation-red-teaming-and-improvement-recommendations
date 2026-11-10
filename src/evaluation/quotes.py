"""Quote-fidelity evaluation against the answer key.

Moved unchanged from scripts/evaluate_quotes.py. The answer key stores the
wording only for altered quotes, so scoring is at the extracted-quote level:
an extracted quote is a positive when it contains an answer-key
`altered_text`; every other extracted quote is a negative. Altered quotes the
extractor never captured count as misses. Both planted (40) and natural (40)
altered rows count as positives; quote_recall_by_origin() splits them.
"""
import difflib
import re
from collections import Counter, defaultdict


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


def evaluate_quotes(key_rows, quote_rows) -> dict:
    """Score quote-fidelity results (rows of {doc_id, quotes}) against the answer key."""
    key = {d["doc_id"]: d for d in key_rows}
    results = {r["doc_id"]: r["quotes"] for r in quote_rows if r}
    if set(results) != set(key):
        raise ValueError("quote results must cover every answer-key document")

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
    return report


def quote_recall_by_origin(key_rows, quote_rows) -> dict:
    """Recall on altered quotes split by origin: planted alterations vs natural misquotes."""
    results = {r["doc_id"]: r["quotes"] for r in quote_rows if r}
    counts = {"planted": Counter(), "natural": Counter()}
    for doc in key_rows:
        found = results.get(doc["doc_id"], [])
        for q in doc["quotes"]:
            if q["quote_status"] != "altered":
                continue
            origin = "planted" if q.get("planted") else "natural"
            caught = any(norm(q["altered_text"]) in norm(r["quote"]) and r["flagged"] for r in found)
            counts[origin]["tp" if caught else "fn"] += 1
    return {origin: {"tp": c["tp"], "fn": c["fn"],
                     "recall": round(c["tp"] / (c["tp"] + c["fn"]), 4) if c["tp"] + c["fn"] else None}
            for origin, c in counts.items()}
