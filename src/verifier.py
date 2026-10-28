"""Corpus existence verifier for extracted citations.

Loads the four corpus files once via load_corpus(), then lookup_citation()
looks up each citation extracted by citation_extractor.py. Matches retain
their corpus IDs so later stages can retrieve the authoritative source text.

Matching rules (DATA_DICTIONARY §3, §3.1, §3.2):
  statute  — match base section string (e.g. 'AS 25.24.150') against statutes.jsonl 'citation'
  rule     — match rule NUMBER only, never citation string; civil and evidence in separate namespaces
  case     — match reporter_cite (e.g. '358 P.3d 1284') against cases.jsonl 'reporter_cite'
"""
import json
import re
from pathlib import Path
from typing import TypedDict

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"

# Confirmed real Alaska law but outside corpus scope (Title 11, not Title 25/18).
# DATA_DICTIONARY §3.2 says to exclude from scoring rather than count as fabricated.
_OUT_OF_SCOPE = {"AS 11.56.807"}
if not all(s.startswith("AS ") for s in _OUT_OF_SCOPE):
    raise ValueError("Bad entry in _OUT_OF_SCOPE — expected 'AS X.Y.Z' format")


class CorpusIndex(TypedDict):
    statutes: dict[str, list[dict]]
    civil_rules: dict[str, list[dict]]
    evidence_rules: dict[str, list[dict]]
    cases: dict[str, list[dict]]
    by_id: dict[str, dict]


def _append(index: dict[str, list[dict]], key: str, record: dict) -> None:
    index.setdefault(key, []).append(record)


def _remember(by_id: dict[str, dict], record: dict) -> None:
    if record.get("id"):
        by_id[record["id"]] = record


def load_corpus() -> CorpusIndex:
    """Load matchable corpus records into citation and stable-ID indexes."""
    for name in ("statutes.jsonl", "rules.jsonl", "rules-evidence.jsonl", "cases.jsonl"):
        if not (CORPUS_DIR / name).exists():
            raise SystemExit(f"Corpus file not found: {CORPUS_DIR / name}")

    by_id: dict[str, dict] = {}
    statutes: dict[str, list[dict]] = {}
    for line in (CORPUS_DIR / "statutes.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("citation"):
            _append(statutes, r["citation"].strip(), r)
            _remember(by_id, r)

    civil_rules: dict[str, list[dict]] = {}
    for line in (CORPUS_DIR / "rules.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("type") == "rule_commentary":
            continue
        # Take the last numeric token — avoids both leading digit prefixes and trailing suffixes like "(a)"
        tokens = re.findall(r"\d+(?:\.\d+)?", (r.get("citation") or ""))
        if tokens:
            _append(civil_rules, tokens[-1], r)
            _remember(by_id, r)

    evidence_rules: dict[str, list[dict]] = {}
    for line in (CORPUS_DIR / "rules-evidence.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("type") == "rule_commentary":
            continue
        if r.get("ruleNumber") is not None:
            _append(evidence_rules, str(r["ruleNumber"]).strip(), r)
            _remember(by_id, r)

    cases: dict[str, list[dict]] = {}
    for line in (CORPUS_DIR / "cases.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("reporter_cite"):
            _append(cases, r["reporter_cite"].strip(), r)
            _remember(by_id, r)

    return {
        "statutes": statutes,
        "civil_rules": civil_rules,
        "evidence_rules": evidence_rules,
        "cases": cases,
        "by_id": by_id,
    }


def matching_corpus_records(citation: dict, corpus: CorpusIndex) -> list[dict]:
    """Resolve an extracted citation to authoritative corpus records."""
    kind = citation.get("type")

    if kind == "statute":
        key = f"AS {(citation.get('section') or '').strip()}"
        return corpus["statutes"].get(key, [])

    if kind == "rule":
        number = str(citation.get("number") or "").strip()
        # bare Rule N (rule_family=None) treated as civil per DATA_DICTIONARY §3.1
        if citation.get("rule_family") == "evidence":
            records = corpus["evidence_rules"].get(number, [])
        else:
            records = corpus["civil_rules"].get(number, [])

        subsection = re.match(r"\(([^)]+)\)", citation.get("subsection") or "")
        if subsection:
            matching_subrule = [
                record for record in records
                if str(record.get("subrule") or "").strip("()").lower()
                == subsection.group(1).lower()
            ]
            if matching_subrule:
                return matching_subrule
        return records

    if kind == "case":
        rc = (citation.get("reporter_cite") or "").strip()
        return corpus["cases"].get(rc, [])

    return []


def corpus_record(corpus: CorpusIndex, record_id: str) -> dict | None:
    """Return a corpus record previously referenced by its stable ID."""
    return corpus["by_id"].get(record_id)


def corpus_source_text(record: dict) -> str | None:
    """Return authoritative text across the corpus's two source-text schemas."""
    return record.get("text") if record.get("ruleset") == "evidence" else record.get("source_text")


def _canonical_citation(record: dict) -> str:
    if record.get("citation"):
        citation = record["citation"]
    elif record.get("ruleset") == "evidence":
        citation = f"Alaska R. Evid. {record['ruleNumber']}"
    else:
        return ""

    if record.get("type") == "court_rule" and record.get("subrule"):
        return f"{citation}({record['subrule']})"
    return citation


def lookup_citation(citation: dict, corpus: CorpusIndex) -> dict:
    """Return existence status and stable corpus references for a citation."""
    if citation.get("type") == "statute":
        key = f"AS {(citation.get('section') or '').strip()}"
        if key in _OUT_OF_SCOPE:
            return {
                "exists": "out_of_scope",
                "corpus_ids": [],
                "matched_citations": [],
            }

    records = matching_corpus_records(citation, corpus)
    return {
        "exists": "true" if records else "false",
        "corpus_ids": [record["id"] for record in records if record.get("id")],
        "matched_citations": list(dict.fromkeys(
            citation_text
            for record in records
            if (citation_text := _canonical_citation(record))
        )),
    }


def verify_citation(citation: dict, corpus: CorpusIndex) -> str:
    """Return 'true', 'false', or 'out_of_scope' for one extracted citation."""
    return lookup_citation(citation, corpus)["exists"]
