"""Citation extractors and normalization for the Alaska family-law benchmark.

Two detectors, combinable:
  - eyecite: generic US parser. Finds reporter cites (P.2d / P.3d) well, but
    does not recognize Alaska statute ("AS 25.24.150") or Alaska rule
    ("Civil Rule 90.3(a)", "Alaska R. Evid. 505") formats at all.
  - alaska: regexes for the three forms the benchmark uses (§6.1 of
    benchmark-exploration.md).

Every extractor returns a list of Mention(raw, start, end, type). Scoring
happens on canonical keys (see `canonical`), never on position.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logging.getLogger("eyecite").setLevel(logging.ERROR)


@dataclass(frozen=True)
class Mention:
    raw: str
    start: int
    end: int
    type: str  # statute | rule | case


# ---------------------------------------------------------------- normalization

SUBSEC = r"(?:\([a-z0-9]{1,4}\))"

STATUTE_RE = re.compile(rf"\bAS\s+(\d{{1,2}})\.(\d{{2}})\.(\d{{3}})({SUBSEC}*)")
RULE_RE = re.compile(
    rf"\b(?P<family>Alaska\s+R\.\s*Evid\.|Alaska\s+R\.\s*Civ\.\s*P\.|Evidence\s+Rule|Civil\s+Rule|Rule)"
    rf"\s+(?P<num>\d{{1,3}}(?:\.\d{{1,2}})?)(?P<sub>{SUBSEC}*)"
)
REPORTER_RE = re.compile(r"\b(\d{1,4})\s+(P\.\s?[23]d)\s+(\d{1,5})\b")
# Case name + reporter + (Alaska YEAR). Name: capitalized words up to " v. ".
CASE_RE = re.compile(
    r"(?P<name>(?:[A-Z][\w.'&-]*\s+){1,6}v\.\s+(?:[A-Z][\w.'&,-]*\s+){0,6}?[A-Z][\w.'&-]*\.?),\s+"
    r"(?P<vol>\d{1,4})\s+(?P<rep>P\.\s?[23]d)\s+(?P<page>\d{1,5})"
    r"(?:,\s*\d{1,5}(?:[-–]\d{1,5})?)?"          # optional pin cite
    r"\s+\((?:Alaska\s+)?(?P<year>\d{4})\)"
)

EVID_FAMILIES = {"alaska r. evid.", "evidence rule"}


def _family(raw_family: str) -> str:
    f = re.sub(r"\s+", " ", raw_family.lower())
    return "evid" if f in EVID_FAMILIES else "civ"   # bare "Rule N" is a civil rule in this benchmark


def canonical(cite: str, type_: str | None = None) -> str | None:
    """Canonical key used to align extractor output with the answer key.

    statute -> 'AS 25.24.150(c)'   (subsections kept: (a) and (b) are different authorities)
    rule    -> 'civ 90.3(a)' / 'evid 505'
    case    -> '451 P.3d 375'      (reporter core; strips over-captured prose and name variants)
    """
    s = re.sub(r"\s+", " ", cite).strip()
    if type_ in (None, "case"):
        m = REPORTER_RE.search(s)
        if m:
            return f"{m.group(1)} {m.group(2).replace(' ', '')} {m.group(3)}"
    if type_ in (None, "statute"):
        m = STATUTE_RE.search(s)
        if m:
            return f"AS {m.group(1)}.{m.group(2)}.{m.group(3)}{m.group(4)}"
    if type_ in (None, "rule"):
        m = RULE_RE.search(s)
        if m:
            return f"{_family(m.group('family'))} {m.group('num')}{m.group('sub')}"
    return None


def truncate(key: str | None, depth: int | None) -> str | None:
    """Keep the first `depth` subsection levels: truncate('AS 25.24.150(c)(5)', 1) -> 'AS 25.24.150(c)'.

    The answer key records statutes and rules to one subsection level even where the text
    cites deeper ('AS 25.20.090(6)(E)' is keyed as 'AS 25.20.090(6)'), so scoring uses depth 1.
    """
    if key is None or depth is None:
        return key
    m = re.match(r"^(.*?\d)((?:\([a-z0-9]+\))*)$", key)
    if not m:
        return key
    subs = re.findall(r"\([a-z0-9]+\)", m.group(2))
    return m.group(1) + "".join(subs[:depth])


def base_section(key: str) -> str:
    """'AS 25.24.170(a)' -> 'AS 25.24.170'; 'civ 90.3(a)' -> 'civ 90.3'."""
    return re.sub(r"(\([a-z0-9]+\))+$", "", key)


# ---------------------------------------------------------------- extractors

def extract_alaska(text: str) -> list[Mention]:
    out = []
    for m in STATUTE_RE.finditer(text):
        out.append(Mention(m.group(0), m.start(), m.end(), "statute"))
    for m in RULE_RE.finditer(text):
        # "Civil Rule 90.3" also contains "Rule 90.3"; the regex alternation prefers the
        # longer family, so each position yields one match.
        out.append(Mention(m.group(0), m.start(), m.end(), "rule"))
    for m in CASE_RE.finditer(text):
        out.append(Mention(m.group(0), m.start(), m.end(), "case"))
    return out


def extract_eyecite(text: str) -> list[Mention]:
    from eyecite import get_citations
    from eyecite.models import FullCaseCitation, FullLawCitation, ShortCaseCitation

    out = []
    for c in get_citations(text):
        if isinstance(c, (FullCaseCitation, ShortCaseCitation)):
            s, e = c.span()
            out.append(Mention(text[s:e], s, e, "case"))
        elif isinstance(c, FullLawCitation):
            s, e = c.span()
            out.append(Mention(text[s:e], s, e, "statute"))
    return out


def extract_hybrid(text: str) -> list[Mention]:
    """eyecite for cases (it is the stronger reporter parser), regexes for Alaska statutes/rules,
    plus any regex case eyecite did not overlap."""
    ey = extract_eyecite(text)
    al = extract_alaska(text)
    out = list(ey)
    for m in al:
        if not any(m.start < e.end and e.start < m.end for e in ey):
            out.append(m)
    return out


EXTRACTORS = {
    "eyecite": extract_eyecite,
    "alaska_regex": extract_alaska,
    "hybrid": extract_hybrid,
}
