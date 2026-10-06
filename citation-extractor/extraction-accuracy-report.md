# Extraction Accuracy Report

Citation-extraction recall against the benchmark answer key, 2026-09-29.

**Status: partial.** 5 of the 200 benchmark documents (doc-0001 to doc-0005: 3 clean, 2 corrupt, 109 key entries) were scored end to end (§0). The full-key numbers in §1 and §2 come from a **format-coverage proxy**: each of the 3,490 answer-key strings placed in a sentence built from the benchmark's own signal phrases. The proxy shows which citation *formats* an extractor recognizes. It cannot show document reading, boundary errors, or citations the key leaves unlabeled. Re-run on all 200 documents (see [How to run](#how-to-run)) before quoting a benchmark-wide number.

The Claude enrichment stage of the hybrid notebook was **not run** (no API key in this environment). Everything here measures the deterministic extractors only.

---

## 0. Real documents: doc-0001 to doc-0005

| Extractor | Recall (109 entries) | Statutes (48) | Rules (23) | Cases (38) | Planted errors (6) | Precision vs key |
|---|---|---|---|---|---|---|
| eyecite only | **34.9%** | 0% | 0% | 100% | 0 of 6 | 1.00 |
| **Hybrid** | **100%** | 100% | 100% | 100% | 6 of 6 | 0.94 (6 extra) |

Scored with per-document dedupe (274 raw mentions reduced to 105 distinct authorities) and alignment at one subsection level (see below). Every key string appeared verbatim in its document, and none of the 16 prose-prefixed key strings (`In …`, `See …`) caused a miss.

**All 6 of the hybrid's "false positives" are real citations that the key doesn't list.** I read each one in context:

| Doc | Cited in the text | Mentions | Key lists instead |
|---|---|---|---|
| doc-0001 | `AS 25.24.200` ("satisfies the conditions of AS 25.24.200") | 3 | only `AS 25.24.200(a)` |
| doc-0001 | `Civil Rule 90.3(a)` / `(a)(1)`–`(a)(4)` | 14 | `Civil Rule 90.3`, `90.3(f)` |
| doc-0001 | `Civil Rule 90.3(b)` ("retains authority under Civil Rule 90.3(b)") | 2 | none |
| doc-0005 | `AS 25.24.150(c)` ("best interests factors under AS 25.24.150(c)") | 7 | only `AS 25.24.150(d)` |
| doc-0005 | `AS 25.20.090` | 1 | `AS 25.20.090(5)`, `(6)` |
| doc-0005 | `Civil Rule 90.3(b)` | 1 | none |

So the extractor's precision against the *text* is 1.0 on these 5 documents. **The answer key is not an exhaustive inventory of citations**: 6 of the 105 distinct authorities the extractor found in these documents (5.7%) are unlabeled. For Stage 2 this matters because an unlabeled citation that's fabricated would never count against the detector. Report these as "unlabeled" rather than as extractor false positives.

**Key convention: one subsection level.** The documents cite deeper than the key records. **84 of 274 mentions (31%) are two-level** (`AS 25.24.150(c)(5)`, `Civil Rule 90.3(a)(2)`, `AS 25.20.090(6)(E)`), and the key truncates them to one level (`AS 25.24.150(c)`, `AS 25.20.090(6)`). The exploration doc's statement that subsections "never nest deeper than one level" is true of the key strings but not of the text. Aligning at full depth drops the hybrid to 94.5% recall with 0.63 precision, all of it this artifact. The harness therefore aligns at `--depth 1` by default.

Per document:

| Doc | Condition | Type | Key entries | Mentions extracted | Hybrid recall |
|---|---|---|---|---|---|
| doc-0001 | corrupt | married_divorcing_with_children | 19 | 59 | 19/19 |
| doc-0002 | clean | married_divorcing_with_children | 32 | 83 | 32/32 |
| doc-0003 | clean | unmarried_custody | 18 | 39 | 18/18 |
| doc-0004 | clean | unmarried_custody | 24 | 58 | 24/24 |
| doc-0005 | corrupt | modify_custody_visitation | 16 | 35 | 16/16 |

Five documents covering three of the five document types is a small sample. The two missing types, domestic_violence and child_support, carry most of the evidence-rule and `AS 18.66` citations.

## 1. Headline, full key (format proxy)

| Extractor | Recall (3,490 key entries) | Statutes (1,546) | Rules (772) | Cases (1,172) | Planted errors recalled (278) |
|---|---|---|---|---|---|
| eyecite only (stage 1 of the current notebook) | **33.6%** | 0% | 0% | 100% | 51 (18%) |
| Alaska regex only | 100% | 100% | 100% | 100% | 278 |
| **Hybrid (eyecite + Alaska regex)** | **100%** | 100% | 100% | 100% | 278 |

Precision was 1.0 for all three on the proxy, which is expected: the proxy contains no text the key does not label. Real-document precision is still unmeasured.

**The one finding that matters now:** eyecite does not recognize Alaska statute (`AS 25.24.150(c)`) or Alaska rule (`Civil Rule 90.3(a)`, `Alaska R. Evid. 505`) citations at all. Those are 66% of the answer key. An extractor built on eyecite alone never sees **227 of the 278 planted errors** (all 139 fabricated statutes and all 88 fabricated rules), so the downstream existence checker could never flag them no matter how good it is. The Alaska regex layer in `extractors.py` closes that gap and should become stage 1 of the notebook.

## 2. Recall by planted-error class

| `injected` | Entries | eyecite | Hybrid |
|---|---|---|---|
| genuine | 3,212 | 1,121 (34.9%) | 3,212 |
| fabricated_statute | 139 | 0 | 139 |
| fabricated_rule | 88 | 0 | 88 |
| wrong_reporter | 30 | 30 | 30 |
| fabricated_case | 21 | 21 | 21 |

By label: of the 279 `exists: false` entries, eyecite recalls 51 (18.3%) and the hybrid recalls all 279.

## 3. Known failure patterns

From 25 format probes (`results/robustness.csv`). Every row below is a form the benchmark itself does not contain, so **none of these affect the proxy numbers above**. They are what to expect when the extractor meets real briefs or a different generator.

| Pattern | Example | eyecite | Hybrid | Effect |
|---|---|---|---|---|
| Any Alaska statute | `AS 25.24.150(c)` | miss | pass | Fixed by regex layer |
| Any Alaska rule | `Civil Rule 90.3(a)`, `Alaska R. Evid. 505(a)` | miss | pass | Fixed by regex layer |
| Non-breaking space in reporter | `451 P.3d 375` | **miss** | pass | Word often inserts these; eyecite drops the cite |
| Two subsections joined | `AS 25.24.150(c) and (d)` | miss | partial | Second subsection `(d)` lost |
| Section range | `AS 25.24.150-.160` | miss | partial | End of range lost |
| Space before subsection | `AS 25.24.150 (c)` | miss | miss* | Captured as `AS 25.24.150`; subsection lost |
| Bluebook statute form | `Alaska Stat. § 25.24.150` | miss | miss | Not recognized at all |
| Plural rules | `Civil Rules 90.3 and 90.4` | miss | miss | Not recognized at all |
| `In re` caption | `In re Adoption of S.K.L.H., 204 P.3d 320` | pass | pass | Regex alone misses it; hybrid is covered by eyecite |

\* counts as a hit under lenient (subsection-insensitive) scoring.

Passes on both: prose-prefixed cases (`In Dunn v. Jones, …`), pin cites, initialized pseudonyms, State-agency parties, spaced `P. 3d`, string cites, nested subsections, the corpus's `Alaska R. Civ. P.` form, and `Evidence Rule N`.

Out of scope for this extractor and not probed: short forms (`Id.`, `supra`, `451 P.3d at 380`) and case-name-only mentions. The benchmark barely uses them (30 `Id.`, 0 `supra`, per benchmark-exploration §2.5), and the key does not label them.

## 4. Scoring caveats, measured on this answer key

**This key is not the version the benchmark exploration describes.** Checked directly:

| Exploration doc says | This key |
|---|---|
| 310 `exists: false` entries | **279** |
| 19 case strings with over-captured prose (`The Nelson v. Nelson`) labeled `false` | Gone; those cases are labeled `true` |
| `AS 18.66.990` / `.180` labeled `false` 12 times | Labeled `true` on all 14 entries |
| `AS 25.24.900/.910/.920` labeled `fabricated_statute` | **Still labeled fabricated** (5 entries) |
| No repeated `(doc_id, cite)` pairs | 1 repeated pair |
| doc-0125 records `AS 18.66.110(a)` though the text has no `(a)` | Still recorded (not checkable without the document) |

It looks like a corrected version. Confirm which version the team is scoring against, and update the exploration doc's counts before quoting them.

How the harness handles the caveats:

1. **Dedupe per document.** The key lists 3,490 entries but only **3,330 distinct authorities** once citations are normalized. 159 entries are the same authority under a second spelling in the same document, mostly a bare `Rule 90.3…` next to `Civil Rule 90.3…` (60 entries) and `In Shanigan v. Shanigan, …` next to `Shanigan v. Shanigan, …`. Extractor output is deduplicated on the same normalized key before scoring. Without that, every repeated mention counts as a false positive: the benchmark averages 3.25 mentions per key entry.
2. **Align on a normalized key, never on position.** Statutes keep their first subsection level (`AS 25.24.150(c)(5)` aligns as `AS 25.24.150(c)`, the key's convention), because `(a)` and `(b)` are different authorities. Rules become family plus number (`civ 90.3(a)`, `evid 505`, with bare `Rule N` treated as civil). Cases align on the reporter citation (`386 P.3d 1238`).
3. **Prose in key strings.** **247 case strings** in this key carry leading prose: 184 start with `In` and 63 with `See`. Aligning on the reporter core means these score correctly. Exact string matching would score a correct, clean extraction as a miss on all 247, which is 21% of case entries.
4. **Key strings that aren't in the document.** The exploration found 5 such strings. On real documents the harness labels this kind of miss `key string not in document`, separately from extractor misses, and it reports a subsection-insensitive "lenient" recall alongside strict recall.
5. **Over-captured strings** are tracked as their own row (`overcaptured_key_strings` in `summary.json`) so they can't hide inside the case recall number.

## 5. What to read next

- On the 5 real documents the hybrid found every labeled citation. Every disagreement with the key was a key artifact (subsection depth) or a citation the key doesn't label. None was an extractor error.
- Run all 200 documents next. The domestic-violence and child-support documents haven't been seen yet, and they hold the evidence-rule citations and the known key problems (`AS 18.66.x`, the 5 key strings the exploration found absent from their documents).
- In the full run, read `false_positives.csv` by hand (it includes context) before calling anything an extractor error. On this sample, all of them were unlabeled real citations.

## How to run

Files in `citation-extractor/`:

| File | What it is |
|---|---|
| `extractors.py` | eyecite, Alaska regex and hybrid extractors, plus the `canonical()` normalizer |
| `recall_harness.py` | Scores extractors against the key, writes `summary.json`, `entries.csv`, `misses.csv` and `false_positives.csv` for each extractor |
| `robustness.py` | The 25 format probes behind §3 |
| `answer-key.json` | The key used for this report (uploaded 2026-09-29) |
| `documents/` | The 5 uploaded benchmark documents; add the rest here |
| `results/` | Real-document and proxy outputs, plus `robustness.csv` |

```bash
pip install eyecite
# real documents (writes results/documents/<extractor>/); scores whichever doc-NNNN.docx are present
python recall_harness.py --key answer-key.json --docs documents
# same, aligned at full subsection depth instead of the key's one level
python recall_harness.py --key answer-key.json --docs documents --depth -1
# proxy, no documents needed (writes results/proxy/<extractor>/)
python recall_harness.py --key answer-key.json --proxy
python robustness.py
```

To score a new extractor, add a function that returns `Mention`s to `EXTRACTORS` in `extractors.py`. The Claude stage of the notebook can be plugged in the same way.
