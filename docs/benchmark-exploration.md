# Benchmark Exploration

Exploration of `data/benchmark/` — document structure, label schema, corruption patterns, and answer-key reliability. Generated 2026-09-15.

Note: this is distinct from `data/corpus/` (the four JSONL files of real Alaska legal authority, explored in [citation-corpus-exploration.md](citation-corpus-exploration.md)). The benchmark is the set of 200 synthetic client `.docx` documents that get *checked against* that corpus, plus the labels saying which of their citations and quotes were deliberately corrupted.

Every count in this document was measured directly from the frozen files rather than taken from `DATA_DICTIONARY.md`; where a measurement disagrees with the data dictionary, that is called out explicitly. Where a question cannot be answered from the files alone, it is marked **[RESEARCH]**.

---

## 0. What this benchmark is for, and what the underlying materials are

The benchmark simulates the output of a legal-document generator — the kind of AI tool that drafts a court filing for a self-represented litigant — and labels where that output went wrong. Its purpose is to let a detector be *measured*: you run your citation checker over the 200 documents, compare what it flags against the answer key, and get precision/recall numbers.

The three artifacts play distinct roles:

- **The documents (`documents/*.docx`)** are the *input* — what the detector reads. Each is a complete, formatted Alaska family-law court filing: a caption naming the court, a recitation of facts, a statement of the governing law, a legal argument, and a request for relief. They are written the way a real motion or petition is written, with legal authority cited inline in the prose.
- **The answer key (`answer-key.json`)** is the *scoring target* — the ground truth. For each document it lists every citation with a true/false label for whether that authority actually exists, and every quoted passage with a faithful/altered label for whether the quotation matches its source.
- **The manifest (`manifest.json`)** is the *freeze fingerprint* — an inventory with a per-document hash, so anyone can confirm the benchmark hasn't drifted since ProSe AI generated it.

Two kinds of error are planted, corresponding to the two things that can go wrong when an AI cites law:

- **A non-existent citation.** The document points at an authority that isn't real — a statute section that was never enacted, a court rule that doesn't exist, an invented case name, or a real case attached to the wrong reporter volume and page. In practice this is the more dangerous failure: a litigant who cites fake law in a filing can have their motion denied or face sanctions (the *Mata v. Avianca* scenario that motivates the project).
- **An altered quotation.** The document quotes a real authority that genuinely exists, but the quoted words have been changed so they no longer say what the source says. This is subtler — an existence check passes, because the citation is fine; only comparing the quoted text against the true source catches it.

Because the errors were planted programmatically — each document was first drafted citing only authorities retrieved from the corpus, then some of those were swapped out or reworded — the labels are ground truth *by construction*. No legal judgment is required to use the benchmark. That is the design intent, and §7 documents where it partially breaks down in practice.

The five document types (§2.2) correspond to the most common filing categories in Alaska family law: dividing a marriage with children involved, establishing custody for parents who were never married, changing an existing custody order, obtaining a protective order against domestic violence, and setting or modifying child support. Each type pulls on a different region of the corpus, which is why the benchmark exercises the statutes and rules it does (§9).

---

## 1. Overview

| File / folder | Count | Contents |
|---|---|---|
| `documents/doc-NNNN.docx` | 200 | The generated filings — the detector's input |
| `answer-key.json` | 200 records | Per-document citation and quote labels — the scoring target |
| `manifest.json` | 1 file, 200 entries | Inventory, per-document hash, clean/corrupt counts |

| Unit of measurement | Count |
|---|---|
| Documents | 200 (`doc-0001` … `doc-0200`, contiguous, no gaps) |
| Clean documents | 97 |
| Corrupt documents | 103 |
| Citation entries in the answer key | 3,490 |
| Quote entries in the answer key | 163 |
| Planted errors | 318 (278 citation errors + 40 altered quotes) |

Document ids are consistent across all three surfaces: the set of `.docx` filenames, the answer-key `doc_id` values, and the manifest `doc_id` values are identical, and every manifest `file` field points at the correct path. The `condition` and `doc_type` fields agree between manifest and answer key on all 200 documents.

---

## 2. The documents (`benchmark/documents/*.docx`)

### 2.1 File format and internal structure

A `.docx` file is a ZIP archive of XML parts, not a single text file — which is why it has to be read with a library rather than opened directly. All 200 documents share **one identical part layout** (18 parts), so any extraction code that works on one works on all:

```
[Content_Types].xml   word/document.xml     word/styles.xml      word/settings.xml
_rels/.rels           word/footnotes.xml    word/numbering.xml   word/fontTable.xml
docProps/app.xml      word/endnotes.xml     word/comments.xml
docProps/core.xml     docProps/custom.xml   (+ 5 _rels files)
```

**All document text lives in `word/document.xml`.** The `footnotes.xml`, `endnotes.xml`, and `comments.xml` parts are present in all 200 files but contain **zero characters of text** in every one — they are empty Word scaffolding. This matters because real legal writing conventionally puts citations in footnotes (the corpus's own case opinions do exactly that, per citation-corpus-exploration.md §3.1). These documents do not: every citation is inline in body prose. An extractor that reads only body paragraphs loses nothing here.

Measured confirmation: of 3,490 answer-key citation strings, **0 were found in footnote text** and 3,485 were found verbatim in body text (the 5 exceptions are analyzed in §7.6).

File sizes are tight: 12,383 – 19,174 bytes (median 14,970).

### 2.2 Length and distribution by document type

| Measure | Min | Median | Mean | Max |
|---|---|---|---|---|
| Non-empty paragraphs | 28 | 50 | 50 | 83 |
| Characters | 9,621 | 17,051 | 17,258 | 28,763 |
| Words | 1,463 | 2,556 | 2,596 | 4,272 |

| `doc_type` | Docs | Median words | Min | Max |
|---|---|---|---|---|
| `married_divorcing_with_children` | 32 | 3,082 | 2,552 | 4,272 |
| `unmarried_custody` | 42 | 2,731 | 2,165 | 3,458 |
| `modify_custody_visitation` | 42 | 2,558 | 1,945 | 3,429 |
| `domestic_violence` | 42 | 2,384 | 1,913 | 2,976 |
| `child_support` | 42 | 2,148 | 1,463 | 2,743 |

The distribution is **not** even across the five types, contrary to DATA_DICTIONARY.md §6 ("distributed roughly evenly"): four types have exactly 42 documents and `married_divorcing_with_children` has 32. It is also the longest type by median words, which is consistent with it covering the most legal ground (divorce, custody, support, and property division in one filing).

### 2.3 Section skeleton

Every document follows the **same five-section skeleton, with no variation across all 200 files**:

```
I. INTRODUCTION → II. STATEMENT OF FACTS → III. LEGAL STANDARD → IV. ARGUMENT → V. CONCLUSION
```

Headings are all-caps with Roman numerals (`I. INTRODUCTION`). There is exactly one distinct heading sequence across the benchmark, so section detection is a solved problem here — a simple regex on `^[IVX]+\.\s+[A-Z ]+$` segments any document reliably.

Above the first heading sits a caption block, identical in structure across all 200:

```
IN THE SUPERIOR COURT FOR THE STATE OF ALASKA
THIRD JUDICIAL DISTRICT
PETITIONER, Petitioner, vs. RESPONDENT, Respondent.
<DOCUMENT TYPE IN CAPS>
(doc-NNNN)
```

Two observations. First, the caption's party line is **unpopulated placeholder text** — the literal words `PETITIONER` and `RESPONDENT` appear in all 200 documents rather than the party names, even though the body prose does use invented names (e.g. "on the petition of Ashley Colby"). This looks like a generator artifact rather than a deliberate choice. Worth noting down that if the production system emits unfilled captions (has placeholder names as aforementioned), that is itself a finding worth reporting under Part C, separate from citation accuracy.

Second, **the document id is printed in the body text of all 200 documents** (`(doc-0001)`). This is benign for extraction but worth knowing: it means the documents are not blind — any model reading one can see its identifier.

Party names in the body are invented and vary per document; no real-person identifiers were observed, consistent with the no-PII claim in DATA_DICTIONARY.md §7.

### 2.4 Where citations appear

Counting every verbatim mention of every answer-key citation string, grouped by the section it falls in (11,355 mentions total — see §3.4 on why this exceeds the 3,490 answer-key entries):

| Section | Mentions | Statute | Rule | Case |
|---|---|---|---|---|
| ARGUMENT | 7,060 | 3,361 | 2,541 | 1,158 |
| LEGAL STANDARD | 2,660 | 1,315 | 801 | 544 |
| CONCLUSION | 1,238 | 767 | 467 | 4 |
| INTRODUCTION | 245 | 137 | 108 | 0 |
| STATEMENT OF FACTS | 152 | 30 | 122 | 0 |

Citations concentrate in ARGUMENT and LEGAL STANDARD (86% of mentions), which mirrors how legal briefs are actually structured — the facts section narrates events, the argument section is where authority is marshalled. Case law is almost entirely confined to those two sections (1,702 of 1,706 case mentions); statutes and rules also appear in the introduction and conclusion, where a filing states what relief it wants and under what provision.

**Implication for extraction:** there is no section you can safely skip, but if extraction recall needs debugging, ARGUMENT is where the volume is.

### 2.5 Citation signal phrases

Counts of introductory phrases (the words that precede a citation in legal prose) across all 200 documents, matched on word boundaries:

| Phrase | Occurrences |
|---|---|
| `under` | 2,169 |
| `consistent with` | 520 |
| `pursuant to` | 417 |
| `in accordance with` | 200 |
| `See` | 103 |
| `as required by` | 61 |
| `Id.` | 30 |
| `See also` | 6 |
| `citing` | 3 |
| `In re` | 0 |
| `cf.` | 0 |
| `supra` | 0 |

The generator's register is plain and repetitive: it introduces authority with `under` / `pursuant to` / `in accordance with` rather than the formal signal apparatus of professional briefs. Notably, **`Id.` appears only 30 times and `supra` never**. These are the short-form citation conventions that make real legal citation parsing hard — `Id. at 65` means "the same source as the previous citation, page 65" and requires tracking state across the document to resolve. Their near-absence means **short-form citation resolution is largely not exercised by this benchmark**, even though the corpus's real opinions use it heavily (citation-corpus-exploration.md §3.1). A detector can score well here without handling `Id.` at all, and that capability gap would not show up in the metrics. **[RESEARCH]** — worth asking whether the production system emits `Id.`-style short forms; if it does, this benchmark under-tests the detector.

`In re` never appears, so the benchmark contains no `In re`-style case citations at all — the form used for proceedings without two opposing parties, including the Child-in-Need-of-Aid cases that make up a visible share of the corpus. Every one of the 1,172 case citations is a two-party `X v. Y` form (§6.1).

---

## 3. The answer key (`answer-key.json`)

A JSON array of 200 records, one per document.

### 3.1 Record schema and field population

Measured field presence across the 200 records:

| Field | Present on | Meaning |
|---|---|---|
| `doc_id` | 200 | Document identifier, matches the `.docx` filename |
| `condition` | 200 | `"clean"` or `"corrupt"` — whether errors were planted |
| `doc_type` | 200 | One of the five filing categories |
| `citations` | 200 | Array of citation entries (below) |
| `quotes` | 200 | Array of quote entries (below); empty on 131 documents |
| `hash` | 200 | 16-hex-char freeze fingerprint |
| `n_errors_planted` | **103** | Count of planted errors — present only on corrupt docs |

Citation-entry fields, across 3,490 entries:

| Field | Present on | Notes |
|---|---|---|
| `cite` | 3,490 | The citation string as captured from the document |
| `type` | 3,490 | `statute` \| `rule` \| `case` |
| `exists` | 3,490 | **The Stage-2 label.** `true` = real authority, `false` = fabricated |
| `quote_status` | 3,490 | **Dead field — the value is `"na"` on all 3,490 entries.** |
| `injected` | 3,490 | `false`, or the corruption type that produced this citation |
| `replaced_real` | **278** | The real citation that was swapped out; present on exactly the injected entries |

The `quote_status` field on citation entries carries **no information anywhere in the benchmark** — it is `"na"` in all 3,490 cases. DATA_DICTIONARY.md §4.2 describes it as taking `"na" | "faithful" | "altered"`, but the faithful/altered values are never used at the citation level. This is the direct analogue of the dead `holding` and `pinpoint` fields in the corpus (citation-corpus-exploration.md §5.1). **All quote fidelity information lives in the separate `quotes` array**; code that reads fidelity labels off citation entries will silently get nothing.

Quote-entry fields, across 163 entries:

| Field | Present on | Notes |
|---|---|---|
| `source_cite` | 163 | The authority the passage was quoted from |
| `quote_status` | 163 | **The Stage-3 label.** `"faithful"` (123) or `"altered"` (40) |
| `injected` | 163 | `false` (123) or `"altered_quote"` (40) |
| `original_text` | **40** | The true source wording — **only on altered quotes** |
| `altered_text` | **40** | The corrupted wording as it appears in the document — **only on altered quotes** |

**This asymmetry is the single most consequential schema fact for Stage 3.** An altered quote tells you both the original and corrupted text, so you can find it in the document and verify your checker caught it. A faithful quote gives you only a `source_cite` and the label `"faithful"` — **no quoted text at all**. So for the 123 faithful quotes you cannot look up "which span of this document is the quote"; you must locate quoted passages yourself, attribute each to a cited source, and only then can the label be applied. Measured: the `source_cite` string appears somewhere in its document's text for 122 of the 123 faithful quotes, so the citation is at least locatable — but the quoted span's boundaries are not given.

### 3.2 Label distributions

Citation entries by authority type and existence:

| Type | Entries | `exists: false` | Share |
|---|---|---|---|
| statute | 1,546 | 152 | 9.8% |
| case | 1,172 | 70 | 6.0% |
| rule | 772 | 88 | 11.4% |
| **Total** | **3,490** | **310** | **8.9%** |

Planted corruption types (the `injected` field):

| `injected` value | Count | Applies to |
|---|---|---|
| `false` (genuine) | 3,212 | all types |
| `fabricated_statute` | 139 | statute only |
| `fabricated_rule` | 88 | rule only |
| `wrong_reporter` | 30 | case only |
| `fabricated_case` | 21 | case only |
| **Total planted citation errors** | **278** | |

Quote entries: 123 `faithful`, 40 `altered`.

Per-document counts:

| Measure | Min | Median | Mean | Max |
|---|---|---|---|---|
| Citations per document | 8 | 17 | 17.4 | 32 |
| Quotes per document | 0 | 0 | 0.81 | 7 |

Quotes per document are heavily zero-inflated: **131 of 200 documents have no quote entries at all**; the distribution is {0: 131, 1: 29, 2: 12, 3: 11, 4: 11, 5: 4, 6: 1, 7: 1}.

Clean and corrupt documents carry a similar citation load (clean: 1,688 across 97 docs; corrupt: 1,802 across 103 docs, median 17 each), so **document length and citation count do not leak the label** — a detector can't cheat by noticing that corrupt documents are longer.

### 3.3 Internal consistency

Every check passed:

- Every injected citation has `exists: false` — no contradictions.
- `replaced_real` is present on exactly the 278 injected citations and on none of the 3,212 genuine ones.
- All 40 altered quotes carry both `original_text` and `altered_text`; no faithful quote carries either.
- `n_errors_planted` equals the actual count of injected citations plus altered quotes on **all 103** corrupt documents — zero mismatches. Distribution: 2 errors (20 docs), 3 errors (54 docs), 4 errors (29 docs). Sum = 318, matching 278 + 40 exactly.
- No clean document contains any `injected` citation or quote, and no corrupt document lacks one. The `condition` field is a faithful summary of the `injected` flags.

So the key is self-consistent. Its problems (§7) are not internal contradictions but disagreements with the corpus it is supposed to be checked against.

### 3.4 The key is deduplicated per document — extraction scoring depends on this

Each distinct citation string appears **at most once per document** in the answer key (measured: zero repeated `(doc_id, cite)` pairs). But citations recur throughout the prose. Summing verbatim occurrences of each answer-key string in its own document gives **11,355 mentions against 3,490 entries — a mean of 3.25 mentions per entry**, with a long tail (one string occurs 33 times in a single document).

| Mentions in text | Answer-key entries |
|---|---|
| 0 | 5 |
| 1 | 1,736 |
| 2 | 707 |
| 3 | 287 |
| 4–10 | 496 |
| 11+ | 259 |

**An extractor that emits one record per citation mention will produce roughly 3× more items than the answer key has, and every duplicate will score as a false positive unless it is deduplicated per document first.** This is the most likely cause of an artificially terrible first extraction-accuracy number, and it is a scoring-harness bug rather than a detector bug. Deduplicate on (document, normalized citation string) before comparing.

Only 702 distinct citation strings exist across the whole benchmark's 3,490 entries; the most repeated are `Civil Rule 90.3(a)` (109 entries), `Civil Rule 90.3(b)` (90), and `Civil Rule 90.3` (83).

### 3.5 Answer-key order is not document order

In **0 of 200** documents does the answer key's citation array follow the order of first appearance in the text. Any alignment between extractor output and the key must be done by matching citation strings, never by position or index.

---

## 4. The manifest (`manifest.json`)

A single object:

| Field | Value |
|---|---|
| `generated` | `2026-08-17T02:38:43.722Z` |
| `total` / `target` | 200 / 200 |
| `complete` | `true` |
| `clean` / `corrupt` | 97 / 103 |
| `document_types` | the five `doc_type` values |
| `documents` | 200 entries, keys: `doc_id`, `doc_type`, `condition`, `file`, `hash` |

`clean + corrupt == total`. The manifest's `condition`, `doc_type`, and `hash` agree with the answer key on all 200 documents.

**The hashes are well-formed but their recipe could not be reproduced.** All 200 are unique, 16 lowercase hex characters, consistent between manifest and answer key. DATA_DICTIONARY.md §4.1 describes the value as "SHA-256 (first 16 hex chars) of the final document text." Eight candidate reconstructions were tried against `doc-0001` (target `813d1c3810185235`): raw `.docx` bytes, `document.xml` bytes, and six whitespace-joining variants of the extracted paragraph text (newline-joined with and without empty paragraphs, double-newline, space-joined, unseparated, and with a trailing newline). **None matched.**

The most likely explanation is that the hash was computed over the generator's internal text representation before `.docx` rendering, which cannot be recovered from the shipped files. **[RESEARCH]** — ask ProSe AI for the exact hashing recipe (input string construction, encoding, normalization). Until then the hashes work as stable per-document identifiers and as a check that the *JSON* files agree with each other, but **they cannot currently be used to verify that the `.docx` files are unmodified** — which is the integrity guarantee DATA_DICTIONARY.md §9.5 claims for them. This matters for the project's reusability criterion: re-running in January should be able to prove the benchmark didn't drift.

---

## 5. Corruption taxonomy — measured

### 5.1 Fabricated statutes (139 entries)

A real statute is replaced with a non-existent section in the same title and chapter, using the 900-range: `AS 25.24.200` → `AS 25.24.946`. The citation stays plausible — right title, right chapter, right format — so only a corpus lookup catches it. The chapter prefix is preserved, meaning **you cannot detect these by checking whether the chapter is in scope**; the section number is the only signal.

Caveat: 5 of these 139 are not actually fabrications — see §7.3.

### 5.2 Fabricated rules (88 entries)

A real rule is replaced with a non-existent rule number, again in a high range: `Civil Rule 90.3(b)` → `Civil Rule 913(b)`. Subrule suffixes are carried over from the real citation. Split by rule family: 83 civil rules and 5 evidence rules (`Alaska R. Evid. 930(a)`, `938(a)`, `926(a)`, `986(b)`, `907(a)`). All 5 fabricated evidence-rule numbers are correctly absent from `rules-evidence.jsonl`.

### 5.3 Fabricated cases (21 entries)

An entirely invented case name plus reporter citation, e.g. the pattern `Restol v. Manshen, 512 P.3d 88 (Alaska 2011)` described in the data dictionary. Neither the party names nor the reporter volume/page resolve in the corpus, so these are the easiest planted errors to catch — measured, 0 of 21 reporter citations resolve.

### 5.4 Wrong reporter (30 entries) — the hardest existence case

A **real case name is kept** and only the reporter volume and page are fabricated:

| Fabricated citation | Real citation it replaced |
|---|---|
| `Peter Chapman v. Julia Chapman, 725 P.3d 476 (Alaska 2025)` | `… 563 P.3d 1155 (Alaska 2025)` |
| `Headlough v. Headlough, 534 P.2d 633 (Alaska 1982)` | `… 639 P.2d 1010 (Alaska 1982)` |
| `Shanigan v. Shanigan, 536 P.3d 438 (Alaska 2017)` | `… 386 P.3d 1238 (Alaska 2017)` |
| `Ogden v. Ogden, 898 P.3d 379 (Alaska 2001)` | `… 39 P.3d 513 (Alaska 2001)` |
| `Mahan v. Mahan, 719 P.3d 787 (Alaska 2015)` | `… 347 P.3d 91 (Alaska 2015)` |

Measured on all 30: the **party surname matches a real corpus case name in 30/30 cases, while the reporter citation resolves in 0/30**. The decision year is also preserved from the real citation.

**This is the decisive design constraint on the existence checker: matching on case name alone gives a 0% catch rate on this entire error class. Existence must be decided on the reporter citation (volume, series, page).** A name-based fuzzy matcher — the intuitive approach, and the one `rapidfuzz` makes easiest — will pass all 30 of these.

### 5.5 Altered quotes (40 entries) — dangerously concentrated

Comparing `original_text` to `altered_text` on all 40:

| Operation | Count |
|---|---|
| Text appended to the end of the true quote | **35** |
| Internal word substitution or deletion | 5 |

All 40 `altered_text` values were located verbatim in their documents.

**All 35 appends are the identical phrase `" under all circumstances"`**, appended to a quotation from `Civil Rule 90.3(a)` or a similar support provision. The remaining 5 are the semantically interesting ones:

| Document | Edit |
|---|---|
| doc-0076 | `shall` → `may` |
| doc-0140 | `shall` → `may` |
| doc-0014 | `primary` → `sole` |
| doc-0189 | `primary` → `sole` |
| doc-0149 | deletion of the word `not` |

Length ratios range from 0.98 to 1.51 — no alteration shortens a quote by more than a word.

**This is the most serious measurement limitation in the benchmark.** The fidelity test set is effectively *one template repeated 35 times plus 5 one-off edits*. Consequences:

1. A detector that does nothing but string-match the literal phrase `under all circumstances` would score ~0.875 recall on altered quotes while having no fidelity-checking ability whatsoever. Any reported Stage-3 recall must be accompanied by the breakdown above, or the number is misleading.
2. The 5 substitution cases are the ones that actually test semantic similarity — and they are the legally severe kind. `shall` → `may` converts a mandatory duty into a discretionary option; deleting `not` inverts a rule's meaning; `primary` → `sole` custody is a substantively different order. These are exactly the alterations that would harm a litigant, and **a sample of 5 cannot support a meaningful precision/recall claim.**
3. Appending text and substituting a word are different detection problems. Appended text leaves the original quote intact as a prefix, so a containment or prefix check catches it; embedding-based similarity may actually struggle, since a 1.05× longer quote with a hedging phrase is semantically close to the original. Word substitutions are the reverse: short edit distance, large semantic change. Report them separately.

Note also that `original_text` was found present in the document for 35 of 40 altered quotes — this is not a second copy of the true quote, but an artifact of the append operation: the original is a literal prefix of the altered text. Containment checks against the document will behave counterintuitively here.

---

## 6. Citation-format mismatch between benchmark and corpus

This is the core engineering problem for Stage 2: the citation strings in the documents are written in a different format from the `citation` fields in the corpus. It is the same class of problem as the broken `cross_refs` links in citation-corpus-exploration.md §4, but it affects the *primary* lookup path rather than a secondary metadata field.

### 6.1 Citation string formats in the benchmark

Statutes (1,546 entries) — `AS Title.Chapter.Section` with optional one-level subsection:

| Subsection depth | Entries |
|---|---|
| None (`AS 25.24.150`) | 565 |
| One level (`AS 25.24.150(c)`) | 981 |

Titles cited: Title 25 (1,178), Title 18 (367), Title 11 (1). Deeper forms like the corpus's own `AS 18.66.100(c)(14)` never appear — the benchmark is shallower than real legal writing.

Rules (772 entries), by prefix form:

| Form | Entries |
|---|---|
| `Civil Rule 90.3(a)` | 632 |
| `Rule 90.3` | 83 |
| `Alaska R. Evid. 505` | 57 |

Cases (1,172 entries): **100%** contain a `P.2d`/`P.3d` reporter citation and an `(Alaska YEAR)` parenthetical. Series split: P.3d 987, P.2d 185. 139 use initialized pseudonyms (`Sarah D. v. John D.`), the convention Alaska uses to protect privacy in family cases.

### 6.2 Resolution rates against the corpus

**Statutes** — the corpus stores `AS 25.24.150` with no subsection, so the subsection must be stripped before lookup:

| Outcome | Entries |
|---|---|
| `exists: true`, resolves only after stripping subsection | **981** |
| `exists: true`, resolves on exact string | 413 |
| `exists: false`, resolves nowhere (correct) | 135 |
| `exists: false`, but exact-matches the corpus (see §7.3) | 17 |

All 1,411 resolved statutes are `status: active` and `retrievable: true`, so the repealed/renumbered trap flagged in citation-corpus-exploration.md §5.2 is **not** exercised by this benchmark — no benchmark citation points at dead law. That's a coverage gap, not a convenience: the production system could cite a repealed statute and this benchmark would never reveal it. **[RESEARCH]** — worth confirming whether ProSe AI considers repealed-statute citation in scope for the detector.

**Rules** — **0 of 772 rule citations match a corpus `citation` value verbatim.** The documents write `Civil Rule 90.3(a)`; the corpus writes `Alaska R. Civ. P. 90.3`. After normalizing to a bare rule number:

| Outcome | Entries |
|---|---|
| `exists: true`, civil rule found | 582 |
| `exists: true`, evidence rule found | 52 |
| `exists: true`, **civil rule NOT in corpus** (see §9) | **50** |
| `exists: false`, correctly absent | 88 |

A naive exact-match existence checker flags **all 772 rule citations as fabricated** — an 11.4% base rate turning into a 100% flag rate. This single normalization gap, if missed, dominates every Stage-2 metric.

Note the corpus's `citation` field is also not a unique key for rules: 155 records collapse to 24 distinct `citation` values (23 distinct rule numbers), because subrules are stored as separate records sharing a citation. Key rule lookups on `(citation, subrule)` or on the normalized rule number, and expect multiple records per rule.

**Cases** — resolution requires extracting the reporter citation:

| Outcome | Entries |
|---|---|
| `exists: true`, reporter resolves | 1,102 |
| `exists: false`, reporter absent (`wrong_reporter`) | 30 |
| `exists: false`, reporter absent (`fabricated_case`) | 21 |
| `exists: false`, but reporter **does** resolve (see §7.1) | 19 |

### 6.3 A normalized baseline, and what its errors are made of

Implementing the normalizations above — strip statute subsections, reduce rules to bare numbers across both rule files, match cases on reporter citation — and treating "not found in corpus" as "flag as fabricated", scored against the answer key's `exists` field over all 3,490 entries:

```
TP = 274    FP = 50    TN = 3,130    FN = 36
precision = 0.846    recall = 0.884    F1 = 0.864
```

The error decomposition is exact and is the most useful finding in this document:

- **All 50 false positives** are the citations of Civil Rules 3, 16.2, 86, and 99 — rules the answer key says exist but which are **absent from the corpus** (§9).
- **All 36 false negatives** are answer-key labeling disagreements (§7): 19 case entries with malformed cite strings, 12 genuine statute citations marked non-existent, and 5 "fabricated" statutes that are real.

**Neither error class is a detector defect.** A correct, well-normalized existence checker is capped at roughly F1 0.86 against this answer key as shipped. Any team reporting a higher number should check whether they have inadvertently fitted to these artifacts; any team reporting ~0.86 should report this decomposition rather than treating it as their detector's ceiling. Both numbers — raw agreement with the key, and agreement after excluding the 86 known-artifact entries — belong in the final report.

---

## 7. Answer-key reliability — 36 measured disagreements

The answer key is internally consistent (§3.3), but on 36 of 3,490 citation entries (1.0%) its `exists` label contradicts what a correct corpus lookup returns. These fall into four groups with distinct causes.

### 7.1 Nineteen case entries whose cite string captured stray prose

Ten distinct malformed strings account for 19 entries, all labeled `exists: false` with `injected: false` — i.e. presented as neither genuine nor planted:

| Count | Cite string as recorded in the key |
|---|---|
| 7 | `Child Support Enforcement Division v. Bromley, 987 P.2d 183 (Alaska 1999)` |
| 3 | `Dawn Golden v. Timothy B. Golden, 563 P.3d 1131 (Alaska 2025)` |
| 2 | `Rosario v. Clare, 378 P.3d 380 (Alaska 2016)` |
| 1 each | `Alaska Supreme Court. See Ruppe v. Ruppe, …` · `The Gorton v. Mann, …` · `The Nelson v. Nelson, …` · `The Sheffield v. Sheffield, …` · `Petitioner. In Stephan P. v. Cecilia A., …` · `Ongoing Marriage. In Veronica Louise Hudson v. Daniel Lee Hudson, …` · `As Holmes v. Holmes, …` |

All 19 reporter citations resolve in `cases.jsonl`. The cause is demonstrable: **for 7 reporter citations, the same case is labeled `exists: true` when the cite string is clean and `exists: false` when the string carries leading prose.**

| Reporter | Labeled `exists: true` | Labeled `exists: false` |
|---|---|---|
| 358 P.3d 1284 | `Ruppe v. Ruppe, …` / `In Ruppe v. Ruppe, …` | `Alaska Supreme Court. See Ruppe v. Ruppe, …` |
| 263 P.3d 49 | `Nelson v. Nelson, …` | `The Nelson v. Nelson, …` |
| 414 P.3d 662 | `Holmes v. Holmes, …` | `As Holmes v. Holmes, …` |
| 281 P.3d 81 | `Gorton v. Mann, …` | `The Gorton v. Mann, …` |
| 265 P.3d 332 | `Sheffield v. Sheffield, …` | `The Sheffield v. Sheffield, …` |
| 464 P.3d 266 | `Stephan P. v. Cecilia A., …` | `Petitioner. In Stephan P. v. Cecilia A., …` |
| 532 P.3d 272 | `Veronica Louise Hudson v. Daniel Lee Hudson, …` | `Ongoing Marriage. In Veronica Louise Hudson v. Daniel Lee Hudson, …` |

**Conclusion: the `exists` label was computed by exact-string lookup on the captured citation string, so a citation-boundary bug in the generator's own extractor propagated into the ground truth.** Where the generator's regex over-captured — swallowing a preceding sentence fragment like `The `, `As `, or `Alaska Supreme Court. See ` — the lookup failed and the citation was recorded as non-existent. Two of these strings (`Bromley`, `Dawn Golden`) are instead full-first-name variants of names the corpus stores in short form.

These 19 entries are **unwinnable false negatives**: a detector that correctly resolves the reporter will be scored wrong. A detector could only "pass" them by replicating the generator's bug.

### 7.2 Twelve genuine statute citations labeled non-existent

| Cite | Entries | Corpus status |
|---|---|---|
| `AS 18.66.990` | 7 | present, `active`, `retrievable: true` |
| `AS 18.66.180` | 5 | present, `active`, `retrievable: true` |

Both exact-match the corpus, both are `injected: false`. `AS 18.66.990` is the definitions section for the domestic-violence chapter and `AS 18.66.180` is within the same chapter — both plainly real. `AS 18.66.990` is additionally labeled inconsistently: 7 entries say `false` and 2 say `true`.

**[RESEARCH]** — the cause is not determinable from the files. Plausible explanations: these sections were not in the generator's retrieval list for those documents and "not retrieved" was conflated with "does not exist", or a lookup index was built over a subset of chapters. ProSe AI should be asked directly, since the answer determines whether these 12 entries are label noise to exclude or a real semantic distinction ("cited without being retrieved") the detector is meant to reproduce.

### 7.3 Five "fabricated" statutes that actually exist

| Cite | Entries | `injected` | Corpus status |
|---|---|---|---|
| `AS 25.24.900` | 2 | `fabricated_statute` | present, `active`, `retrievable: true` |
| `AS 25.24.910` | 2 | `fabricated_statute` | present, `active`, `retrievable: true` |
| `AS 25.24.920` | 1 | `fabricated_statute` | present, `active`, `retrievable: true` |

The fabrication strategy (§5.1) generates a fake section number in the 900-range of the real chapter — but **AS 25.24.900, .910, and .920 are real, active sections present in the corpus**, so the "fabrication" collided with genuine law. The generator recorded them as planted errors regardless.

These 5 are the mirror image of §7.1: entries the key calls fabricated that a correct detector will resolve and pass. **[RESEARCH]** — confirm against the Alaska Legislature's published statutes that AS 25.24.900/.910/.920 are genuinely enacted sections (the corpus asserts it, but the corpus is ProSe AI's own build and this is exactly the point where an independent check is warranted). If confirmed, these 5 entries should be excluded from Stage-2 scoring and reported to ProSe AI as a generator defect, since the same collision will recur whenever the benchmark is regenerated.

### 7.4 One genuinely non-existent citation, correctly labeled

`AS 11.56.807` (doc-level `injected: false`, `exists: false`) does not resolve — and correctly so. It is the benchmark's only Title 11 citation; Title 11 is Alaska's criminal code, outside the corpus's family-law scope. The label is right, though the reason is scope rather than fabrication. This is the same class of issue as the Administrative Code exclusion noted in DATA_DICTIONARY.md §3: **`exists: false` in this key sometimes means "outside the corpus" rather than "not real law"**, and those are different claims. A detector should probably report out-of-scope citations as a third category rather than folding them into "fabricated".

### 7.5 "Clean" does not mean "every citation exists"

**17 of the 97 clean documents contain at least one citation labeled `exists: false`** (21 such entries; the remaining 11 non-injected `exists: false` entries sit in corrupt documents). No clean document contains an altered quote.

A natural assumption — that `condition: "clean"` means every citation in the document resolves — is false. Any per-document scoring that derives expected labels from `condition` rather than reading the per-citation `exists` field will be wrong on 17 clean documents. Per-document hallucination-risk scoring (the October milestone) is especially exposed: 17 clean documents will legitimately carry nonzero risk scores.

### 7.6 Five cite strings absent from their own document

Five answer-key entries were never found verbatim in the document they belong to:

| Document | Key records | Document actually contains |
|---|---|---|
| doc-0125 | `AS 18.66.110(a)` | `AS 18.66.110` (no subsection) |
| doc-0179 | `AS 25.24.170(a)` | `AS 25.24.170` (no subsection) |
| doc-0175 | `AS 25.27.062(a)` | `AS 25.27.062` and `AS 25.27.062(g)` — **subsection (g), not (a)** |
| doc-0148 | `Petitioner. In Stephan P. v. Cecilia A., …` | the clean citation without the prose prefix |
| doc-0150 | `Ongoing Marriage. In Veronica Louise Hudson v. …` | the clean citation without the prose prefix |

The first three show the key recording a subsection the text does not carry — and in doc-0175, a *different* subsection than appears. The last two are the §7.1 over-capture cases. **Exact string matching between extractor output and the key will fail on these 5 regardless of extractor quality**; alignment needs normalization (strip signal words, compare on the citation core).

---

## 8. Quote coverage — the answer key labels only a subset

The documents use **only straight ASCII quotation marks** (8,891 `"` and 1,202 `'`); no curly/typographic quotes appear anywhere. So a simple `"([^"]+)"` extraction is safe here — no Unicode normalization needed.

Extracting all double-quoted spans and comparing to the 163 answer-key quote entries:

| Measure | Count |
|---|---|
| All double-quoted spans | 601 |
| — of 1–3 words | 130 |
| — of 4–10 words | 140 |
| — of more than 10 words | **331** |
| Spans ≥20 characters | 519, across 127 documents |
| Answer-key quote entries | **163, across 69 documents** |

The short spans are mostly terms of art and defined terms rather than source quotations — `"household member"` (10), `"domestic violence"` (8), `"home state"` (5), `"crime involving domestic violence"` (7) — plus quoted witness speech from the facts sections (`"make him regret it"`, `"regret"`) and quoted role labels (`"Petitioner"`, `"Mother"`, `"Father"`). Those are correctly not quote-fidelity targets.

The long spans are the problem. **There are 331 quoted passages over 10 words across 99 documents, but the answer key labels only 163 quotes across 69 documents. 47 documents contain long quoted passages yet have no quote entries at all.** (Conversely 17 documents have quote entries but no >10-word span, so some labeled quotes are short.)

**Implication for Stage 3:** the `quotes` array is a *sample* of quoted material, not an inventory. A fidelity checker that flags every quoted passage whose text diverges from its source will surface divergences in passages the key says nothing about — and those will look like false positives even when the checker is right. Two consequences for honest measurement:

1. Restrict Stage-3 scoring to the `(document, source_cite)` pairs the key actually labels. Report the restriction explicitly, along with how many quoted spans were excluded.
2. Divergences found in unlabeled passages should be reported separately as *unverifiable findings* rather than silently dropped or counted as errors. Some may be genuine uncaught alterations, which would be a finding about the benchmark's completeness — relevant to Part C.

Quote entries by source authority:

| Source kind | Faithful | Altered | Total |
|---|---|---|---|
| Statute (`AS …`) | 89 | 29 | 118 |
| Rule (`Civil Rule …`) | 34 | 11 | 45 |

Only 60 distinct `source_cite` values appear; the most quoted are `Civil Rule 90.3(a)` (21), `AS 18.66.100` (12), and `AS 25.24.150(c)` (8). No case law is quoted anywhere — consistent with DATA_DICTIONARY.md §8.1's statement that the generator paraphrases case law by policy and quotes verbatim only from statutes and rules. **Quote fidelity against case-law holdings is therefore entirely untested by this benchmark**, even though misquoted holdings are a documented real-world failure mode. That gap belongs in the Part C recommendations.

---

## 9. What the benchmark exercises, and where the corpus falls short

Distinct authorities cited across the benchmark:

| Authority type | Distinct in benchmark | In corpus | Coverage |
|---|---|---|---|
| Statute sections | 157 | 500 | 31% |
| Case reporter citations | 217 | 1,143 | **19%** |
| Rule citation strings | 121 | 155 records / 23 rule numbers | — |

Most-cited authorities:

| Statute | Entries | | Rule | Entries |
|---|---|---|---|---|
| `AS 25.20.110(a)` | 69 | | `Civil Rule 90.3(a)` | 109 |
| `AS 25.24.150(c)` | 67 | | `Civil Rule 90.3(b)` | 90 |
| `AS 25.20.090` | 42 | | `Civil Rule 90.3` | 83 |
| `AS 18.66.100(b)` | 40 | | `Rule 90.3` | 47 |
| `AS 25.20.070` | 39 | | `Civil Rule 90.3(f)` | 46 |
| `AS 25.24.150(g)` | 37 | | `Civil Rule 65.1` | 36 |

The benchmark is concentrated: it touches under a fifth of the case corpus, and its rule citations are dominated by the Rule 90.3 child-support family. A detector tuned on this benchmark is tuned on a narrow slice of the corpus.

### The corpus is missing four rules the answer key says are real

| Rule | Entries | Present in `rules.jsonl`? |
|---|---|---|
| `Civil Rule 3(h)` | 33 | No |
| `Civil Rule 86(l)` | 8 | No |
| `Civil Rule 16.2(e)` | 6 | No |
| `Civil Rule 99(a)` | 3 | No |

`rules.jsonl` contains only 23 distinct civil rule numbers: 12, 26.1, 40, 41, 52, 53, 58, 59, 60, 65, 65.1, 77, 78, 90, 90.1, 90.2, 90.3, 90.4, 90.5, 90.6, 90.7, 90.8, 100. Rules 3, 16.2, 86, and 99 are absent.

These 50 entries are **the entire false-positive mass** of the §6.3 baseline. The answer key says they exist; the corpus cannot confirm it. **[RESEARCH]** — verify against the Alaska Court System's published Rules of Civil Procedure whether Rules 3 (commencement of action), 16.2, 86, and 99 exist as real rules. They almost certainly do, which would make this a **corpus completeness gap rather than a labeling error** — the opposite diagnosis from §7, and it calls for a different remedy: either ProSe AI extends `rules.jsonl`, or the detector must distinguish "not in corpus" from "not real" and report the former as unverifiable rather than fabricated.

That distinction is worth making regardless, because it is the honest engineering answer: a corpus-backed existence checker can only ever report "I could not verify this," and collapsing that into "this is fabricated" is what produces the 50 false positives.

---

## 10. Implications for downstream work

1. **Deduplicate per document before scoring extraction.** The key holds one entry per distinct citation string per document, while the text averages 3.25 mentions each (11,355 mentions vs. 3,490 entries). Failing to dedupe inflates false positives roughly 3×. Also never align by position — answer-key order matches document order in 0 of 200 documents (§3.4, §3.5).

2. **Normalization is the whole game for Stage 2, and rules are the trap.** Zero of 772 rule citations match the corpus verbatim (`Civil Rule 90.3(a)` vs. `Alaska R. Civ. P. 90.3`), and 981 of 1,546 statute citations resolve only after stripping the subsection. Build the normalizer before the checker, and unit-test it on all three authority types (§6.2).

3. **Case existence must be decided on the reporter citation, not the case name.** The 30 `wrong_reporter` errors keep a real party name and year while faking the volume and page: name matching catches 0 of 30, reporter matching catches 30 of 30 (§5.4). This is the single highest-value design decision in the existence checker, and a name-based fuzzy match — the most natural use of `rapidfuzz` here — fails the entire class.

4. **Expect a ceiling near F1 0.86 against the key as shipped, and report the decomposition rather than the bare number.** A correct normalized checker yields TP 274 / FP 50 / TN 3,130 / FN 36. Every one of the 50 false positives is the missing-rules corpus gap (§9); every one of the 36 false negatives is an answer-key artifact (§7). Report agreement both raw and with the 86 known-artifact entries excluded, and state which is which — the project is graded on honest measurement, and this is precisely the kind of thing that measurement is supposed to surface.

5. **Treat "not in corpus" and "not real law" as different verdicts.** Three separate findings converge on this: the 50 missing rules (§9), the out-of-scope `AS 11.56.807` (§7.4), and the Administrative Code exclusion documented in DATA_DICTIONARY.md §3. A checker with three outcomes — verified real, verified absent, unverifiable — is both more honest and more useful to ProSe AI than a binary flag, and it makes the corpus's own coverage gaps visible instead of charging them to the detector.

6. **Stage-3 metrics rest on a very thin and skewed sample — say so numerically.** 40 altered quotes, of which 35 are the identical appended phrase `" under all circumstances"` and only 5 are internal word substitutions (§5.5). A literal string match on that phrase scores ~0.875 recall with no fidelity capability at all. Always report the two operation types separately, and state the n=5 on the substitution cases. The legally severe alterations (`shall`→`may`, deletion of `not`, `primary`→`sole`) are entirely within that 5.

7. **Faithful quotes give you a label but no text — plan the Stage-3 harness around that.** Only the 40 altered quotes carry `original_text`/`altered_text`; the 123 faithful ones carry just a `source_cite` (§3.1). Locating quoted spans and attributing them to a cited source is work the benchmark does not do for you. Budget for it, and restrict scoring to labeled `(document, source_cite)` pairs — the documents contain 331 long quoted passages against 163 labeled quotes, with 47 documents holding long quotes and no labels at all (§8).

8. **Do not derive expected labels from `condition`.** 17 of 97 clean documents contain citations labeled `exists: false` (§7.5). Read per-citation `exists` and per-quote `quote_status` always. This will also matter for the per-document risk score due in October, where 17 clean documents legitimately carry nonzero risk.

9. **Several real-world failure modes are untested here — name them in Part C rather than implying coverage.** Measured gaps: no quoted case-law holdings anywhere in the benchmark (§8), so paraphrase-fidelity against opinions is unexercised; no citations to repealed or renumbered statutes, despite 70 such records sitting in the corpus (§6.2); `Id.`/`supra` short-form citations essentially absent, 30 and 0 occurrences (§2.5); no `In re` citations at all, so single-party proceedings including CINA cases are unexercised (§2.5); statute subsections never nest deeper than one level (§6.1). DATA_DICTIONARY.md §8.2 makes the general point that planted errors don't cover every hallucination; these are the specific instances, with counts.

10. **The freeze cannot currently be verified against the `.docx` files.** The manifest hashes are internally consistent and unique, but eight reconstruction attempts failed to reproduce them from the documents (§4). Since re-running the detector in January and trusting the comparison is the project's stated top success criterion, getting the hashing recipe from ProSe AI is a prerequisite, not a detail.

11. **Extraction itself is the easy part — don't over-invest.** All 200 documents share one 18-part OOXML layout, one five-section skeleton, empty footnotes/endnotes/comments, straight-ASCII quotes only, and 100% of case citations carrying both a reporter and an `(Alaska YEAR)` parenthetical. Body-paragraph text extraction plus per-type regexes is sufficient; the difficulty in this project is concentrated in normalization (item 2), corpus coverage (item 5), and the answer key's reliability (item 4).

---

## 11. How these numbers were produced

Every figure above was computed from the frozen files with Python standard library only — `zipfile` plus `xml.etree.ElementTree` for `.docx` text (joining all `w:t` descendants per `w:p`, rendering `w:tab`/`w:br`, letting ElementTree handle XML entity unescaping), and `json` for the key, manifest, and corpus. `python-docx` was not available in the environment; a library-based reader should reproduce the same paragraph text, but re-verifying the §3.4 mention counts and §8 span counts after switching to `python-docx` is worth one cell of the evaluation notebook.

Reproduction scripts were written as throwaway analysis and are not checked in. The measurements to re-derive first, because everything else depends on them, are: the 11,355-vs-3,490 mention ratio (§3.4), the 0/772 rule match rate (§6.2), and the TP/FP/TN/FN decomposition (§6.3).

**[RESEARCH] — open questions for ProSe AI, consolidated:**

1. The exact `hash` recipe, so the freeze can be verified against the `.docx` files (§4).
2. Why `AS 18.66.990` and `AS 18.66.180` are labeled non-existent, and why `AS 18.66.990` is labeled inconsistently across documents (§7.2).
3. Whether `AS 25.24.900`/`.910`/`.920` are enacted sections — if so, the 900-range fabrication strategy collides with real law and will recur on regeneration (§7.3, needs independent confirmation against the Alaska Legislature's published statutes).
4. Whether Civil Rules 3, 16.2, 86, and 99 are real rules absent from `rules.jsonl` — i.e. corpus gap vs. document error (§9, needs confirmation against the Alaska Court System's published rules).
5. Whether the `exists` label is meant to assert "exists in real Alaska law" or "present in this corpus" — §7.4 and §9 pull in different directions, and the answer changes the scoring convention.
6. Whether unfilled `PETITIONER`/`RESPONDENT` captions are intended (§2.3).
7. Whether repealed-statute citation and `Id.`/`supra` short forms are in scope for the detector, given neither is exercised here (§2.5, §6.2).
