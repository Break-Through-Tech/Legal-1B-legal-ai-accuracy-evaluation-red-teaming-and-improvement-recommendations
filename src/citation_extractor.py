"""Pattern-based citation extraction; initially reviewed on doc-0001 only.

Offsets index the supplied cleaned text. Repeated mentions are retained. This
module detects citation syntax, including fabricated references, not existence.
"""
import re


# Preserve nested subsections, ranges, and shorthand lists as written. Resolving
# ranges/list members into individual legal provisions is a separate operation.
SUBSECTION = r"(?:\([A-Za-z0-9]+\))"
SUFFIX = rf"{SUBSECTION}*(?:\s*[-–]\s*{SUBSECTION}+)?(?:,\s*{SUBSECTION}+)*"
STATUTE = re.compile(
    rf"\bAS\s+(?P<section>\d+\.\d+\.\d+)(?P<subsection>{SUFFIX})",
    re.IGNORECASE,
)
RULE = re.compile(
    rf"\b(?P<prefix>(?:Alaska\s+)?(?:Civil\s+Rule|Evidence\s+Rule|"
    rf"R\.\s*Civ\.\s*P\.|R\.\s*Evid\.)|Rule)\s+"
    rf"(?P<number>\d+(?:\.\d+)?)(?P<subsection>{SUFFIX})",
    re.IGNORECASE,
)
# Capitalized words and initials cover the party names in the preview. Keeping
# lowercase prose out prevents 'recognized in Bunn' from becoming a case name.
NAME_WORD = r"[A-Z][A-Za-z'’\-]*(?:\.)?"
PARTY = rf"{NAME_WORD}(?:[ \t]+{NAME_WORD})*"
CASE = re.compile(
    rf"\b(?P<case_name>{PARTY}\s+v\.\s+{PARTY}),\s*"
    r"(?P<volume>\d+)\s+(?P<reporter>P\.(?:2d|3d))\s+(?P<page>\d+)"
    r"(?:,\s*(?P<pinpoint>\d+(?:[-–]\d+)?))?"
    r"\s*\((?P<court>Alaska(?:\s+App\.)?)\s+(?P<year>\d{4})\)"
)


def extract_citations(text: str) -> list[dict]:
    """Return statute, rule, and full case mentions in document order.

    Bare rules have an unknown family (None). Short-form cases such as Id.,
    lowercase party-name connectors, and other reporters are not yet supported.
    """
    citations = []
    for kind, pattern in (("statute", STATUTE), ("rule", RULE), ("case", CASE)):
        for match in pattern.finditer(text):
            start, end = match.span()
            fields = match.groupdict()
            if kind == "case":
                # Common introductory signals are prose, not party names.
                signal = re.match(r"(?:(?:See|In|Under|Compare)\s+)+", fields["case_name"])
                if signal:
                    start += signal.end()
                    fields["case_name"] = fields["case_name"][signal.end():]
                fields["year"] = int(fields["year"])
                fields["reporter_cite"] = (
                    f"{fields['volume']} {fields['reporter']} {fields['page']}"
                )
            elif kind == "rule":
                prefix = fields.pop("prefix").lower()
                fields["rule_family"] = (
                    "civil" if "civil" in prefix or "civ." in prefix
                    else "evidence" if "evid" in prefix else None
                )
            citations.append({
                "type": kind,
                "raw_text": text[start:end],
                "start": start,
                "end": end,
                **fields,
            })
    return sorted(citations, key=lambda citation: citation["start"])
