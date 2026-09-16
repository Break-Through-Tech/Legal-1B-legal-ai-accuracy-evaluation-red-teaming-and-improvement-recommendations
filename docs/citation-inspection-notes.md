# Task #3 — Citation Inspection Notes

**Purpose:** Findings from manually inspecting a representative sample of benchmark documents
against `data/benchmark/answer-key.json`, to inform the citation extractor (Task #5) and
cleaning step (Task #4).

## Sample set (11 of 200 documents)

One clean + one corrupt per `doc_type`, plus an extra corrupt doc to cover all five
corruption types (`fabricated_statute`, `fabricated_rule`, `fabricated_case`, `wrong_reporter`,
`altered_quote`):

| Doc Type | Clean | Corrupt (injected error types) |
|---|---|---|
| married_divorcing_with_children | doc-0002 | doc-0001 (fabricated_rule ×2, fabricated_statute, altered_quote) |
| unmarried_custody | doc-0003 | doc-0043 (fabricated_statute ×2, altered_quote) |
| modify_custody_visitation | doc-0006 | doc-0083 (fabricated_rule ×2, fabricated_statute, altered_quote) |
| domestic_violence | doc-0007 | doc-0130 (fabricated_rule, fabricated_statute ×2, altered_quote) |
| child_support | doc-0165 | doc-0169 (fabricated_rule, wrong_reporter, altered_quote) |
| unmarried_custody (extra) | — | doc-0047 (fabricated_statute, wrong_reporter, fabricated_case) |

## Method

1. Extracted plain text from each `.docx` via `python-docx`, reading `paragraph.text`
   (per the DATA_DICTIONARY's extraction guidance).
2. Loaded each document's record from `answer-key.json`.
3. For every `citations[]` and `quotes[]` entry, searched for the exact string in the
   extracted text and captured surrounding context.

## Finding 1 — Citations appear verbatim, 100% of the time

All 188 citation strings across the 11 sampled documents were found **exactly** in the
extracted paragraph text (0 unmatched). Citations are not split across runs/paragraphs and
require no fuzzy matching to *locate* — a regex/rule-based extractor should be able to achieve
very high extraction recall if its patterns cover the formats below.

## Finding 2 — Citation formats observed

**Statutes:** `AS <title>.<chapter>.<section>` with optional nested subsections, e.g.
`AS 25.24.160`, `AS 25.24.160(a)`, `AS 18.66.100(c)(14)`. The same base section is often
cited repeatedly with different subsection suffixes within one document.

**Rules — two competing formats for the same rule, sometimes within the same document:**
- Informal: `Civil Rule 90.3(a)(2)(B)`
- Formal/short: `Alaska R. Civ. P. 90.3` / `Rule 90.3`
- Evidence rules: `Alaska R. Evid. 505(a)`

An extractor must recognize `Civil Rule`, `Alaska R. Civ. P.`, `Rule`, and `Alaska R. Evid.`
as equivalent lead-ins to the same rule-citation pattern.

**Cases:** `Name v. Name, Vol Reporter Page (Alaska Year)`, e.g.
`Bunn v. House, 934 P.2d 753 (Alaska 1997)`. A leading signal word **"In "** frequently
precedes the case name in-text and is *included* in the answer key's `cite` string
(e.g. `"In Ruppe v. Ruppe, 358 P.3d 1284 (Alaska 2015)"`) — extractor logic should decide
whether to normalize/strip this signal word or keep it, but must at least tolerate its presence.

## Finding 3 — How fabrications look in context

Fabricated citations are embedded in fluent, grammatically natural legal prose with no
formatting tell — they are indistinguishable from real citations without a corpus lookup.
Examples pulled directly from the sample:

| Type | Fake cite in text | Real cite replaced | Note |
|---|---|---|---|
| fabricated_statute | `AS 25.24.946` | `AS 25.24.200` | same title/chapter, invented section |
| fabricated_rule | `Civil Rule 913(b)` | `Civil Rule 90.3(b)` | plausible 3-digit rule number vs. real `90.3` |
| fabricated_rule | `Alaska R. Evid. 986(b)` | `Alaska R. Evid. 505(b)` | same pattern for evidence rules |
| wrong_reporter | `Berkbigler v. Berkbigler, 787 P.2d 329 (Alaska 1996)` | `..., 921 P.2d 628 (Alaska 1996)` | case name + year identical; only volume/page changed |
| wrong_reporter | `Mendel-Gleason v. Harris, 714 P.3d 266 (Alaska 2011)` | `..., 261 P.3d 397 (Alaska 2011)` | digits altered, name untouched |
| fabricated_case | `Restol v. Manshen, 351 P.3d 100 (Alaska 2021)` | `Smith v. Weekley, 73 P.3d 1219 (Alaska 2003)` | entirely invented name/citation in the same rhetorical slot |

**Implication:** name-only matching is insufficient for cases — `wrong_reporter` errors keep
a real, correctly-spelled case name, so the detector must verify the full citation
(name **and** reporter volume/page/year) against the corpus, not just the party names.

## Finding 4 — Altered quotes are subtle, small edits

Both altered-quote examples found were **small insertions**, not full rewrites, e.g. a real
Rule 90.3(a) quote had "...under all circumstances" appended at the end, otherwise verbatim.
This means the fidelity checker needs to be sensitive to minor textual drift, not just gross
paraphrase — pure semantic similarity alone may be too lenient for such small edits; a
combined string-similarity + semantic-similarity approach is likely needed.

**Faithful quotes have no stored quote text in the answer key** (only `source_cite` +
`"faithful"` status) — to validate faithful quotes ourselves, we must locate the quoted span
in the document text directly and diff it against the corpus's `source_text`, since the
answer key does not supply the "before" text for faithful cases.

## Implications for later tasks

- **Task #4 (cleaning):** encoding artifacts observed in raw source text (e.g. `â€™` for
  curly apostrophes in `cases.jsonl` `source_text`) should be normalized; extracted document
  text itself was clean in this sample, but corpus text needs Unicode normalization for
  reliable string/semantic comparison.
- **Task #5 (extractor):** build separate regex families for statutes (`AS \d+\.\d+\.\d+`),
  rules (multiple lead-in phrases mapping to one rule-number pattern), and cases (name-pair +
  reporter pattern, tolerant of a leading "In "). Extraction recall should be measurable
  against 100% verbatim-match baseline shown here.
- **Task #6 (recall report):** since citations were 100% locatable as plain text in this
  sample, any recall shortfall in the full 200-doc run is likely a **pattern-coverage** gap
  (missed format variant) rather than a text-extraction/OCR problem — worth distinguishing
  the two failure modes in the accuracy report.
