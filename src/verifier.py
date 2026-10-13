"""Corpus existence verifier for extracted citations.

Loads the four corpus files once via load_corpus(), then verify_citation()
looks up each citation extracted by citation_extractor.py and returns
'true', 'false', or 'out_of_scope'.

Matching rules (DATA_DICTIONARY §3, §3.1, §3.2):
  statute  — match base section string (e.g. 'AS 25.24.150') against statutes.jsonl 'citation'
  rule     — match rule NUMBER only, never citation string; civil and evidence in separate namespaces
  case     — match reporter_cite (e.g. '358 P.3d 1284') against cases.jsonl 'reporter_cite'
"""
import json
import re
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"

# Confirmed real Alaska law but outside corpus scope (Title 11, not Title 25/18).
# DATA_DICTIONARY §3.2 says to exclude from scoring rather than count as fabricated.
_OUT_OF_SCOPE = {"AS 11.56.807"}
if not all(s.startswith("AS ") for s in _OUT_OF_SCOPE):
    raise ValueError("Bad entry in _OUT_OF_SCOPE — expected 'AS X.Y.Z' format")


def load_corpus() -> dict:
    """Load all four corpus files into in-memory lookup sets. Call once at startup."""
    for name in ("statutes.jsonl", "rules.jsonl", "rules-evidence.jsonl", "cases.jsonl"):
        if not (CORPUS_DIR / name).exists():
            raise SystemExit(f"Corpus file not found: {CORPUS_DIR / name}")

    statutes: set[str] = set()
    for line in (CORPUS_DIR / "statutes.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("citation"):
            statutes.add(r["citation"].strip())

    civil_rules: set[str] = set()
    for line in (CORPUS_DIR / "rules.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        # Take the last numeric token — avoids both leading digit prefixes and trailing suffixes like "(a)"
        tokens = re.findall(r"\d+(?:\.\d+)?", (r.get("citation") or ""))
        if tokens:
            civil_rules.add(tokens[-1])

    evidence_rules: set[str] = set()
    for line in (CORPUS_DIR / "rules-evidence.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("ruleNumber") is not None:
            evidence_rules.add(str(r["ruleNumber"]).strip())

    cases: set[str] = set()
    for line in (CORPUS_DIR / "cases.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("reporter_cite"):
            cases.add(r["reporter_cite"].strip())

    return {
        "statutes": statutes,
        "civil_rules": civil_rules,
        "evidence_rules": evidence_rules,
        "cases": cases,
    }


def verify_citation(citation: dict, corpus: dict) -> str:
    """Return 'true', 'false', or 'out_of_scope' for one extracted citation.

    citation is one item from citations.jsonl (fields: type, section, number,
    rule_family, reporter_cite, as produced by citation_extractor.py).
    """
    kind = citation.get("type")

    if kind == "statute":
        key = f"AS {(citation.get('section') or '').strip()}"
        if key in _OUT_OF_SCOPE:
            return "out_of_scope"
        return "true" if key in corpus["statutes"] else "false"

    if kind == "rule":
        number = str(citation.get("number") or "").strip()
        # bare Rule N (rule_family=None) treated as civil per DATA_DICTIONARY §3.1
        if citation.get("rule_family") == "evidence":
            return "true" if number in corpus["evidence_rules"] else "false"
        return "true" if number in corpus["civil_rules"] else "false"

    if kind == "case":
        rc = (citation.get("reporter_cite") or "").strip()
        if not rc:
            return "false"
        return "true" if rc in corpus["cases"] else "false"

    return "false"
