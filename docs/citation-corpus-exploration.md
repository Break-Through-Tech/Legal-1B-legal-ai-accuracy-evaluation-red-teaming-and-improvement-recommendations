# Citation Corpus Exploration

Exploration of `data/corpus/` — document structure, citation patterns, and statute-vs-case-law reference behavior. Generated 2026-09-08.

Note: this is distinct from `data/benchmark/` (200 synthetic client `.docx` documents, clean/corrupt, used for the accuracy-evaluation task). The corpus is the underlying legal reference source those documents are checked against.

## 0. What this corpus is for, and what the underlying legal materials are

The four JSONL files in `data/corpus/` together simulate a legal research database — the kind of system a lawyer or an AI legal assistant would query to check whether a citation in a document is real, current, and says what the document claims it says. Each line in each file is one JSON object representing a single "document" in that research database: one court opinion, one statute section, one procedural rule, or one evidence rule. The purpose of having this corpus at all is to give the accuracy-evaluation pipeline (in `data/benchmark/`) something concrete to check citations against — if a benchmark document cites "AS 25.24.150(c)," the evaluation logic looks that citation up in `statutes.jsonl` to see whether it exists, is still active law, and whether the text actually supports what the document says it supports.

Because legal writing (briefs, memos, motions, opinions) relies on four different *kinds* of authority, the corpus is split into four files, one per kind. Below is a plain-language explanation of what each kind of authority is, since the rest of this document assumes familiarity with them:

- **Case law (`cases.jsonl`)**: written opinions issued by courts (here, Alaska's appellate courts) deciding real disputes. When a court decides a case, its written reasoning becomes "precedent" — a rule that later courts and lawyers are expected to follow or distinguish in similar disputes. Lawyers cite cases to show how a court has previously interpreted a law or resolved a similar fact pattern. Case law is *binding* precedent only within its jurisdiction and only to the extent a later court must follow it (higher courts bind lower courts; a court is not strictly bound by its own past decisions but usually follows them).
- **Statutes (`statutes.jsonl`)**: laws enacted by a legislature (here, the Alaska Legislature). A statute is the codified, written text of a law — e.g., "a court must consider the best interests of the child when awarding custody." Statutes are organized hierarchically into Titles, Chapters, and Sections; "AS" stands for "Alaska Statutes," the official compilation of Alaska's enacted laws, analogous to the "U.S. Code" at the federal level. Statutes are the primary source of substantive legal rules; case law then interprets and applies them to specific facts.
- **Rules of Civil/Appellate Procedure (`rules.jsonl`)**: these are not laws passed by the legislature but procedural rules adopted by the court system (typically the state supreme court) that govern *how* litigation is conducted — deadlines, filing requirements, how motions are made, how appeals proceed, and so on. They answer "how do I do this in court," not "what is the substantive law."
- **Rules of Evidence (`rules-evidence.jsonl`)**: a specialized subset of court rules that govern what evidence (testimony, documents, exhibits) is admissible at trial or in a hearing — e.g., rules about hearsay, relevance, expert testimony, and privilege. They are procedural in nature but are commonly organized and cited as their own separate body of rules (distinct from general civil/appellate procedure rules), which is why the corpus keeps them in a separate file with a different schema (see 2.4).

All four files are scoped to a single U.S. state (Alaska) and a single practice area (family law — divorce, custody, child support, domestic violence protective orders, and related Child-in-Need-of-Aid/CINA proceedings) so that the corpus is realistic in scale and internally coherent, rather than an unrealistically broad slice of all law everywhere.

## 1. Overview

The corpus is a single-jurisdiction, single-practice-area reference set: **Alaska, family law**, split across four JSONL files.

| File | Records | Content |
|---|---|---|
| `cases.jsonl` | 1,255 | Full-text Alaska appellate opinions |
| `statutes.jsonl` | 500 | Alaska Statutes (AS) titles relevant to family law |
| `rules.jsonl` | 155 | Alaska Rules of Civil/Appellate Procedure |
| `rules-evidence.jsonl` | 302 | Alaska Rules of Evidence |
| **Total** | **2,212** | |

Every record across all four files is tagged `jurisdiction: "Alaska"` and (where applicable) `case_type` / `practice_area: "family_law"` — there is no cross-jurisdiction or cross-practice-area content in this corpus. (`jurisdiction` identifies which state's/country's legal system a document belongs to — important because a citation that's valid law in one state may be meaningless or non-binding in another. `practice_area`/`case_type` tags which substantive legal specialty the document belongs to, e.g. "family_law" versus "criminal" or "contracts" — useful for filtering a retrieval system down to relevant authority instead of searching all of Alaska law.)

## 2. Per-file schema and field population

This section lists every field present in each file (a "field" is one key in the JSON object for each record — i.e., one column if you think of the JSONL file as a table) and explains, for each one, what real-world information it's meant to hold and why a retrieval or citation-checking system would care about it.

### 2.1 `cases.jsonl`

Fields: `id`, `type`, `citation`, `case_name`, `reporter_cite`, `year`, `court`, `jurisdiction`, `practice_area`, `binding`, `citable_in_brief`, `retrievable`, `precedential_status`, `holding`, `pinpoint`, `source_url`, `source_id`, `cluster_id`, `match_signals`, `source_text`.

- `id`: a unique internal identifier for the record within this corpus (a database primary key). Used to reference the record programmatically without relying on the human-readable citation string, which can vary in formatting.
- `type`: a tag identifying what kind of legal document this record is (here, always a case-law opinion) — lets code that mixes records from multiple files tell them apart without inspecting the filename.
- `citation`: human-readable form, e.g. `"Vanessa Emery v. Jason Stone (Alaska 2026)"`. This is the informal "case name and year" citation format most people recognize — the way a case gets referred to in conversation or in a case caption, as opposed to the formal library/reporter citation (see `reporter_cite` below).
- `case_name`: the formal name of the lawsuit as captioned by the court — typically "Plaintiff/Petitioner v. Defendant/Respondent" (e.g., "Emery v. Stone"). This is the same underlying information as the first part of `citation` but stored separately so it can be used on its own (e.g., for display or matching) without the year/jurisdiction parenthetical attached.
- `reporter_cite`: formal reporter citation, e.g. `"449 P.3d 700"`. Populated on 1,232/1,255 (98.2%). A "reporter" is the official/unofficial printed (and now digital) case-law compilation series a court's opinions are published in — here, the "Pacific Reporter" (P.2d = 2nd series, P.3d = 3rd series), the standard reporter for Alaska and other Western-state appellate decisions. The format is "[volume] [reporter abbreviation] [starting page]" — e.g. "449 P.3d 700" means volume 449 of the Pacific Reporter, 3rd series, starting at page 700. This is the precise, unambiguous citation lawyers are expected to use in formal filings, as opposed to the looser `citation` field above.
- `year`: spans **1962–2026**. The year the opinion was decided/issued by the court — used to check how old a precedent is and whether newer case law may have superseded it.
- `court`: which specific court issued the opinion (e.g., the Alaska Supreme Court versus the Alaska Court of Appeals) — matters because different courts carry different binding weight (see `binding` below).
- `jurisdiction`: see Section 1 above — always "Alaska" in this corpus.
- `practice_area`: see Section 1 above — always "family_law" in this corpus.
- `binding`: `true` for all 1,255 records. "Binding" means the precedent is legally authoritative and must be followed by lower courts within the same jurisdiction, as opposed to merely "persuasive" (a court may consider it but isn't obligated to follow it, e.g. an opinion from a different state). All records here being `true` means the corpus contains only mandatory Alaska authority, not out-of-state or advisory opinions.
- `citable_in_brief`: `"yes"` for all 1,255 — corpus is pre-filtered to citable precedent only. Some jurisdictions restrict certain opinions (e.g. unpublished or memorandum decisions) from being formally cited in a legal brief; this field flags whether a case is permitted to be cited at all. Every record being "yes" means the corpus is pre-filtered to only citable opinions. <b>(Might be an issue in the future. May need citable dataset to test citable vs non-citable)</b>
- `retrievable`: `true` for all 1,255. Flags whether the record actually has full text available to pull up (as opposed to being a stub entry known to exist but with no text on file) — a retrieval system should not surface a document as a source if `retrievable` is false, because there's nothing behind it to verify.
- `precedential_status`: `"Published"` for all 1,255. Indicates whether the court designated the opinion as "published" (creates binding precedent, appears in the official reporter) versus "unpublished"/memorandum (often not citable, or citable only in limited circumstances) — related to, but a distinct field from, `citable_in_brief`.
- `holding`: **empty in every record (0/1,255)**. Field exists in schema but is unused/dead. A "holding" is the specific legal rule or conclusion the court actually decided in the case — the narrow, precise answer to the legal question presented (as distinct from background facts or the court's broader reasoning/dicta). It's normally a short, extractable summary meant to let a reader know at a glance what the case stands for without reading the full opinion. <b>(What does it mean?)</b>
- `pinpoint`: **empty in every record (0/1,255)**. Same as above. A "pinpoint citation" (or "pincite") is a reference to the *exact page* within a reporter volume where a specific quoted or relied-upon passage appears (e.g., "449 P.3d 700, 705" cites page 705 specifically, not just the case's starting page 700). Pinpoint cites are what let a reader/verifier check a precise quoted proposition rather than having to read an entire opinion to confirm it. <b>(Need to add pinpoint to the corpus for more accurate results)</b>
- `source_url`: a link to where the original document can be found/verified online (e.g. a court website or legal database) — provides external provenance for the record.
- `source_id`: an identifier tying this record back to whatever original upstream data source it was pulled from (e.g. a legal database's own internal ID) — distinct from `id` (this corpus's own key) so the record's origin can still be traced.
- `cluster_id`: an identifier grouping related records together (for example, multiple database entries or citation variants that all refer to the same underlying opinion) — used for deduplication or for linking a case to related proceedings.
- `source_text`: full opinion text, populated on all 1,255. This is the actual body of the court's written decision — the raw text a retrieval system would search, quote from, or extract a holding from.
- `match_signals`: array of topical/statute-family tags per case. Every case has at least one (avg 2.38/case, max 9). These are short topic/subject-matter labels (some are legal-topic phrases like "child custody," others are statute citation prefixes like "AS 25.24") attached to a case to make it easier for a retrieval system to find cases relevant to a given legal issue without having to search the full opinion text. Top tags:

  | Tag | Count |
  |---|---|
  | child custody | 549 |
  | AS 25.24 | 450 |
  | best interests of the child | 348 |
  | marital property | 318 |
  | AS 25.20 | 257 |
  | Rule 90.3 | 251 |
  | child support obligation | 226 |
  | spousal support | 116 |
  | AS 25.27 | 85 |
  | AS 25.23 | 84 |
  | AS 25.30 | 77 |
  | AS 18.66 | 58 |
  | dissolution of marriage | 53 |
  | AS 25.25 | 29 |
  | AS 18.65 | 23 |

  (Each "AS ##.##" tag refers to an Alaska Statutes title/chapter — see 2.2 below for what these mean. "Rule 90.3" refers to Alaska's Civil Rule 90.3, the rule governing child support calculations — see 2.3.)

### 2.2 `statutes.jsonl`

Fields: `id`, `type`, `citation`, `title`, `jurisdiction`, `case_type`, `source_text`, `binding`, `retrievable`, `status`, `source_url`, `cross_refs`.

- `id`, `type`, `jurisdiction`, `source_url`: same purpose as described for `cases.jsonl` above (unique key, document-kind tag, jurisdiction, external link).
- `citation` format: `"AS 25.05.010"` (Title.Chapter.Section). Alaska Statutes are organized in a three-level hierarchy: Title (a broad subject area — Title 25 covers "Marital and Domestic Relations," i.e. family law), Chapter (a subdivision within the title — Chapter 25.24 covers divorce and dissolution), and Section (a specific numbered provision within the chapter — e.g. .150 is the specific section on custody factors). This numbering scheme is how a specific rule of law is precisely located and cited.
- `title`: the descriptive name/heading of the statute section (what the provision is actually about, in plain words) — distinct from the "Title" level of the citation hierarchy described above; this field is the section's own short title/caption (e.g. "Award of custody").
- `case_type`: here doubling as the practice-area tag for statutes (analogous to `practice_area` in `cases.jsonl`) — always "family_law."
- `source_text`: the actual enacted text of the statute — the operative legal language itself, as opposed to a summary of it.
- `binding`: whether the statute is currently valid, enforceable law within the jurisdiction (as opposed to, e.g., a proposed-but-not-enacted provision) — for enacted statutes generally `true`.
- `retrievable`: whether full text is actually available for this record, same concept as in `cases.jsonl`.
- `status`: `active` 430, `repealed` 64, `renumbered` 6. Tracks the statute's current legal lifecycle status: "active" means it is presently in force and applicable law; "repealed" means the legislature has formally removed/revoked it and it is no longer valid law (citing it as current authority would be an error); "renumbered" means the substantive provision still exists but has been moved to a different section number (so the old citation no longer points to the current location of that rule, even though the underlying rule may still be good law elsewhere).
- `retrievable`: `true` for 430, **`false` for 70** — these are the repealed/renumbered entries with no `source_text`. A retriever that cites one of these without checking `retrievable`/`status` would surface dead law as if current.
- `source_text`: populated on 430/500 (matches `retrievable: true` count exactly).
- `cross_refs`: populated on 248/500 (49.6%). A structured, machine-readable list of *other* citations that this statute references or is related to (as distinct from citations that merely appear inline within the statute's free-form text — see Section 4 for how these two citation surfaces differ and where this field breaks down).

### 2.3 `rules.jsonl` (procedural — Civil/Appellate)

Fields: `id`, `type`, `citation`, `title`, `jurisdiction`, `case_type`, `source_text`, `binding`, `retrievable`, `status`, `part`, `subrule`, `source_url`, `cross_refs`.

- Fields shared with the other files (`id`, `type`, `title`, `jurisdiction`, `case_type`, `source_text`, `binding`, `retrievable`, `status`, `source_url`, `cross_refs`) carry the same meaning described above, applied to procedural rules instead of cases or statutes: `status` again distinguishes currently-in-force rules from repealed/superseded ones; `retrievable` again flags whether text actually exists for the record; `cross_refs` is again the structured (but partially broken, see Section 4) reference list.
- `citation` format: `"Alaska R. Civ. P. 12"`. "R. Civ. P." stands for "Rules of Civil Procedure" — the standard abbreviation used when citing this body of rules in legal writing, analogous to the Federal Rules of Civil Procedure (FRCP) at the federal level, but adopted by the Alaska court system to govern Alaska state civil litigation. "Rule 12," for example, is the rule governing motions to dismiss a case for various defects.
- `part`: Roman-numeral grouping (e.g., "Part XII"). Court rule sets are typically organized into numbered/lettered "Parts," each covering a stage or category of litigation (e.g., commencement of an action, pleadings, trials, appeals). This field records which structural part of the rules a given rule belongs to, which is useful for understanding a rule's role/context within the overall procedural scheme.
- `subrule`: identifies a specific subdivision within a rule (e.g., Rule 12(b)(6) — the "(b)(6)" portion) when a citation or cross-reference points to a sub-part of a rule rather than the rule as a whole.
- `part` distribution (Roman numerals, procedural rule "parts"): Part XII dominates (80/155), followed by XI (19), VI (12), IX (10), XIII (9), III (8), X (6), VII (4), VIII (4), V (3).
- `source_text`: populated on all 155.
- `cross_refs`: populated on 59/155 (38.1%).

### 2.4 `rules-evidence.jsonl`

Fields: `id`, `ruleNumber`, `subrule`, `ruleTitle`, `text`, `type`, `ruleset`, `binding`, `familySalient`, `retrievable`, `status`, `part`, `edition`, `history`, `cross_refs`.

Notably different shape from the other three files: uses `text` instead of `source_text`, `ruleTitle` instead of `title`, and adds `edition` (publisher/creationDate/sourceFile metadata) and `history` (amendment history strings, e.g. `"(Added by SCO 364 effective August 1, 1979; and amended by SCO 1829 effective October 15, 2014)"`).

- `id`, `type`, `binding`, `retrievable`, `status`, `part`, `cross_refs`: same underlying meaning as the equivalent fields in `rules.jsonl` above — unique key, document-kind tag, whether the rule is currently valid binding authority, whether full text is available, whether the rule is currently active law, which structural part of the rule set it belongs to, and the structured (partially broken, see Section 4) cross-reference list.
- `ruleNumber` / `subrule`: the rule's number (e.g. "404") and, if applicable, its subdivision (e.g. "(b)" for the specific exception clause within Rule 404) — split into two fields here rather than folded entirely into a single `citation` string as in the other files.
- `ruleTitle`: the descriptive caption of the rule (e.g. "Character Evidence; Crimes or Other Acts") — equivalent in purpose to `title` in the other files, just differently named because this file's schema was built independently (see note below on the differing shape).
- `text`: the actual rule language — equivalent in purpose to `source_text` in the other three files.
- `ruleset`: identifies which body of rules the record belongs to — here always "evidence," distinguishing it from the civil/appellate procedural rules in `rules.jsonl`.
- `familySalient`: `true`/`false` flag indicating whether a rule of evidence is specifically relevant to family-law practice (as opposed to being a general evidence rule that would apply in any type of case, e.g. criminal or commercial litigation) — a convenience filter for retrieval within this practice-area-focused corpus.
- `edition`: metadata about the published source this rule text was drawn from (e.g. publisher name, the date the record was created/compiled, and the source file it came from) — provenance/version information, not part of the legal citation itself.
- `history`: a free-text string recording the rule's amendment history — when the rule was originally adopted and each subsequent amendment, each tied to a "Supreme Court Order" ("SCO") number and effective date. A Supreme Court Order is the formal mechanism by which the Alaska Supreme Court adopts or amends court rules (distinct from a statute, which is enacted by the legislature) — so `history` is itself a citation trail, just to a different kind of authority (SCO numbers) than any other field in the corpus.
- `ruleset`: `"evidence"` for all 302.
- `status`: `active` for all 302.
- `familySalient`: `true` for 82/302 (27.2%) — flags rules specifically relevant to family-law practice within the broader evidence rules.
- `history`: populated on 154/302 (51.0%) — separate citation layer (Supreme Court Order numbers) not present elsewhere in the corpus.
- `cross_refs`: populated on 107/302 (35.4%).

## 3. Citation patterns

This section looks at citations that appear as free-running text *inside* each record's own body text (`source_text`/`text`) — i.e., citations to other authorities that a court, statute, or rule mentions while writing itself — as opposed to the structured `cross_refs` metadata field discussed separately in Section 4.

### 3.1 Case-law citation style (inside `cases.jsonl` opinion text)

- **Case self-citation**: formal reporter format `### P.2d/P.3d ###, ### (Alaska YEAR)`. Follows classic state-appellate footnote convention — inline superscript markers (¹²³) in body text, full citation given in a numbered footnote block at point of first use, shortened on repeat (e.g. `Id. at 65.`, `Hodari, 407 P.3d at 472.`). ("Id." is Latin shorthand meaning "the same source as the immediately preceding citation," used to avoid re-typing a full citation every time the same case is referenced again in a row; "at 65" is a pinpoint page reference, see 2.1 above.)
- 1,230/1,255 cases (98.0%) contain at least one P.2d/P.3d reporter citation in body text.
- **Statute citation**: `AS Title.Chapter.Section(subsection)(sub-subsection)`, e.g. `AS 18.66.100(c)(14)`. As described in 2.2, statute citations get more specific by adding parenthetical subsection letters/numbers — "(c)" narrows to subsection c of the section, and "(14)" further narrows to the 14th item within that subsection, letting a citation point to one precise clause of a longer statute.
- 1,000/1,255 cases (79.7%) cite at least one AS provision.
- Most-cited statutes across the case corpus (raw occurrence count in opinion text):

  | Statute | Hits | Subject |
  |---|---|---|
  | AS 25.24.150(c) | 329 | Custody — best-interest factors |
  | AS 25.24.150(g) | 290 | Custody — factors, cont. |
  | AS 25.24.160(a)(4) | 238 | Property division |
  | AS 47.10.010(a)(2)(A) | 149 | Child in Need of Aid (CINA) |
  | AS 25.24.150 | 129 | Custody (general) |
  | AS 47.10.010(a)(2) | 115 | CINA |
  | AS 25.24.150(h) | 106 | Custody |
  | AS 47.10.080(c)(3) | 103 | CINA disposition |
  | AS 25.20.110(a) | 100 | Custody/visitation modification |
  | AS 25.24.150(c)(6) | 93 | Custody factor (domestic violence) |

  ("CINA," Child in Need of Aid, is Alaska's legal category — and the name of the associated court proceedings — for cases where a child requires state intervention or protection, roughly analogous to what other states call "dependency" or "child welfare" proceedings; AS Title 47 is the title of the Alaska Statutes covering welfare, social services, and CINA.)

- **Court-rule citation**: `Civil Rule ##`, `Alaska R. Civ. P. ##`, `R. Evid. ##`, `R. App. P. ##`. 3,698 total hits across the case corpus — frequently interleaved with statute citations in the same footnote (e.g. a fee-shifting opinion citing `AS 18.66.100(c)(14)` alongside `Alaska R. Civ. P. 68` and `Civil Rule 82` in adjacent footnotes). ("R. Evid." = Rules of Evidence, see 2.4; "R. App. P." = Rules of Appellate Procedure, the subset of `rules.jsonl` governing how appeals are conducted; "fee-shifting" refers to rules like Civil Rule 82, which lets a prevailing party recover some attorney's fees from the losing party — an exception to the default American rule that each side pays its own fees.)
- **Recursive case-to-case citation**: cases cite other cases in the corpus repeatedly (e.g. `Marron v. Stromstad`, `Hodari v. State, Dep't of Corr.` each cited and re-cited across multiple independent opinions). This means the case corpus has genuine precedent-chain structure — not a flat, independent list of documents. (This reflects how real case law works: courts build on earlier decisions rather than deciding every case from a blank slate, so a realistic case corpus should show the same recurring, interlinked citation pattern rather than each opinion citing only statutes and never other cases.)

### 3.2 Statute-to-statute and statute-to-other citation (inside `statutes.jsonl` `source_text`)

- 252/430 statutes with text (58.6%) cite at least one other AS provision inline, totaling 820 statute-citation hits — a real statute-to-statute citation web exists within the corpus, not just in the `cross_refs` metadata field. (Statutes commonly cross-reference each other — e.g., a custody statute might say "as defined in AS 47.10.990" to borrow a definition from elsewhere in the code rather than repeating it — so this inline web mirrors how real statutory codes are drafted.)
- **Zero** statutes cite case law inline (0 P.2d/P.3d hits). (This is expected: statutes are enacted by the legislature before any court has interpreted them, so the original statutory text itself never references a court decision — it's case law that later cites back to the statute, not the reverse.)
- Near-zero rule citations from statute text (7/430) — statutes largely stay within their own citation lane and don't reference procedural/evidence rules directly.

### 3.3 Procedural-rule citation (inside `rules.jsonl` `source_text`)

- 54/155 (34.8%) cite other procedural rules — rules mostly self-reference within the rule set.
- 21/155 (13.5%) cite AS statutes (37 hits total).
- 8/155 (5.2%) cite case law.

### 3.4 Evidence-rule citation (inside `rules-evidence.jsonl` `text`)

The most cross-referential of the three non-case sources:

- 130/302 (43.0%) cite other rules.
- 47/302 (15.6%) cite case law inline.
- 30/302 (9.9%) cite AS statutes (63 hits total).
- Plus the separate `history` field (154/302 populated) carrying Supreme Court Order citations (SCO ###) — a citation layer not present anywhere else in the corpus. (See 2.4 above for what an SCO is.)

### 3.5 Citation direction summary

| Source type | Cites cases | Cites statutes | Cites rules |
|---|---|---|---|
| Cases | ✅ heavy (recursive) | ✅ heavy (80% of cases) | ✅ heavy (3,698 hits) |
| Statutes | ❌ (0%) | ✅ moderate (59% of records w/ text) | ❌ (~2%) |
| Procedural rules | minor (5%) | minor (14%) | ✅ moderate (35%) |
| Evidence rules | moderate (16%) | minor (10%) | ✅ heavy (43%) |

Cases are the hub of the citation graph — they're the only source type that cites densely into all three other categories. Statutes are the most citation-insular category (cite only each other, rarely). Evidence rules are the most cross-referential of the non-case sources.

## 4. `cross_refs` field — a broken-link problem

`cross_refs` is a structured metadata field (separate from the citations embedded in body text) meant to give a direct machine-readable link graph — i.e., rather than making a retrieval system regex-scan an entire opinion or statute's free text to find what it cites (as Section 3 does), `cross_refs` is supposed to be a ready-made list of citation strings pointing directly at other records in the corpus, the way a database foreign key would. It is present on:

- 248/500 statutes (49.6%)
- 59/155 procedural rules (38.1%)
- 107/302 evidence rules (35.4%)
- **695 total `cross_refs` entries** across statutes + procedural rules.

**Resolvability check** — testing whether each `cross_refs` string entry matches an exact `citation` value elsewhere in the corpus (i.e., can this reference actually be "resolved" — looked up and matched — against another record's own `citation` field, the way a foreign key should match a primary key):

- **405/695 (58.3%) resolve.** The remaining 41.7% are dangling references — pointers that don't match any record's `citation` field exactly, effectively broken links in the citation graph.

**Root cause identified:** a citation-format mismatch between how rules store their own `citation` field versus how they're referenced in `cross_refs`.

- A procedural rule's own `citation` field is formatted with full prefix: `"Alaska R. Civ. P. 4"`.
- But `cross_refs` entries pointing at that same rule use the bare form: `"Rule 4"`, `"Rule 90.1"`, `"Rule 4(e)"` (sometimes with a subrule suffix, sometimes without).
- A naive exact-string lookup of `cross_refs` values against the `citation` index will silently fail to resolve **any** procedural-rule cross-reference, because the two representations never match verbatim.
- Statute `cross_refs` do **not** have this problem — both sides use the same `"AS ##.##.###"` format, so statute→statute links resolve cleanly. Most of the 405 successful resolutions come from statute cross-refs.

Most frequently cross-referenced targets (raw string counts, regardless of resolvability):

| Target | References |
|---|---|
| AS 18.66.100 | 13 |
| AS 25.30.300 | 12 |
| AS 25.25.702 | 9 |
| AS 25.24.200 | 8 |
| AS 25.27.120 | 8 |
| AS 18.65.400 | 8 |
| AS 25.30.400 | 8 |
| AS 47.27 | 7 |
| AS 25.24.150 | 7 |
| AS 20.20.060 | 7 |

## 5. Implications for downstream work

1. **`holding` / `pinpoint` fields are dead weight** — 0% populated across 1,255 case records. Any accuracy-evaluation or retrieval logic that expects to read a holding summary from this field will always get nothing; the holding must be extracted from `source_text` instead, or the field should be flagged as not implemented. (See 2.1 for what `holding` and `pinpoint` are supposed to represent.)
2. **70 statutes are `retrievable: false`** (repealed/renumbered, no `source_text`). A citation-checking or retrieval pipeline must gate on `retrievable`/`status` before treating a statute hit as current, live law — otherwise it risks validating a brief's citation to repealed statutory text as correct. (See 2.2 for what "repealed" and "renumbered" mean legally, and why citing a repealed statute as current law would be a substantive error in a legal document.)
3. **`cross_refs` needs a normalizer before it's usable as a graph.** Rule-to-rule cross-references (`"Rule N"` vs. `"Alaska R. Civ. P. N"`) require regex extraction of the rule number and prefix-agnostic matching, or ~42% of rule cross-reference edges will silently fail to resolve in any graph-based retrieval or citation-validation build on top of this field. Statute cross-refs don't have this issue and can be joined directly on the `citation` string.
4. **Cases are the right anchor for citation-graph traversal.** They're the only record type citing densely into all three other categories (statutes, procedural rules, evidence rules) plus other cases recursively — a citation graph built case-first will have far better coverage than one built statute-first or rule-first.
5. **Two separate citation surfaces exist per record**: the citations embedded in free text (`source_text`/`text`, requires regex extraction, more complete) and the structured `cross_refs` metadata field (only ~40–50% coverage, direct but incomplete, and broken for rules per point 3). Don't rely on `cross_refs` alone as "the" citation graph — it under-represents what's actually cited in the text.
