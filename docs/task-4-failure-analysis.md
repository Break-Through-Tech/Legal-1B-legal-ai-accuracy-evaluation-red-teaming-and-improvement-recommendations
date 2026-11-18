# Task #4 — Failure analysis and taxonomy

The earlier citation evaluation caught **273 of 278** labeled fabrications. All five misses came from the answer key labeling real statute sections as fabricated. The corrected key scores those five predictions as true negatives, and the unified detector caught **273 of 273** scored fabrications with zero scored citation false positives. The unified run missed **31 of 80** labeled quote alterations, mostly because the full passage never reached the quote checker.

The [review inventory](task-4-failure-inventory.csv) contains 105 rows across the two baselines and their scoring units. Quote and document rows can describe the same underlying event. Document IDs resolve to files under `data/benchmark/documents/`. A key quote number is its one-based position in that document's answer-key quote array. Flag IDs are local to the document and refer to the unified run's `reports.jsonl`, which contains both flagged and unflagged candidates.

## Fabrication recall and reconciliation

| Baseline | Caught | FN | FP | Fabricated recall |
|---|---:|---:|---:|---:|
| Earlier citation existence | 273 | 5 | 0 | 98.20% |
| Unified citation existence | 273 | 0 | 0 | 100.00% |

Both existence evaluators score unique authorities per document. The earlier run excludes `AS 11.56.807` in `doc-0136`. The unified run also excludes `AS 11.56.810` in that document. The benchmark dictionary identifies both as real authorities outside the corpus. The second excluded target had no unified extraction, so it creates no observed false flag. The five relabelings account for the entire change in the scored fabricated denominator.

| Document | Citation in DOCX and exact corpus record | Earlier expected → observed | Unified expected → observed |
|---|---|---|---|
| doc-0059 | AS 25.24.900 · `statute-as-25-24-900` | fabricated → exists | real → exists |
| doc-0110 | AS 25.24.910 · `statute-as-25-24-910` | fabricated → exists | real → exists |
| doc-0152 | AS 25.24.910 · `statute-as-25-24-910` | fabricated → exists | real → exists |
| doc-0182 | AS 25.24.920 · `statute-as-25-24-920` | fabricated → exists | real → exists |
| doc-0198 | AS 25.24.900 · `statute-as-25-24-900` | fabricated → exists | real → exists |

**Rank 1 in the earlier run was benchmark label conflict.** The five cases account for 100% of earlier fabrication misses and **1.80 percentage points** of scored recall loss (5 ÷ 278 × 100). Commit `b3a8b73` changed `exists` from false to true for each row. The citation texts, corpus records, and existence verdicts agree across the two runs. The unified run has zero observed fabrication recall loss to rank.

## Unified quote and document errors

| Scoring unit | TP | FN | FP | Primary causes for scored errors |
|---|---:|---:|---:|---|
| Quote evaluator | 49 | 31 | 24 | FN: 28 extraction misses, 2 lenient fuzzy matches, 1 formatting variant. FP: 10 copied-passage boundaries, 8 paraphrases, 5 source attribution issues, 1 unresolved. |
| Document risk, corrupt-condition target | 103 | 0 | 20 | FP: 11 copied-passage risk aggregation, 9 document target mismatches. |
| Document risk, any-labeled-error target | 112 | 14 | 11 | FN: 13 extraction misses, 1 lenient fuzzy match. FP: 11 copied-passage risk aggregation. |

- All 40 planted quote alterations were caught. The detector caught 9 of 40 natural misquotes. All 31 missed targets were present in the normalized DOCX text. For 28, the evaluator found no candidate spanning the full target, although some candidates covered fragments. Ten of those 28 are condensed versions of Civil Rule 65(b)'s notice and evidence conditions.
- Three missed quote targets reached the checker. In `doc-0073`, the checker treated “when” in place of “only if (1)” as low severity. In `doc-0197`, it treated the added “only” as low severity. In `doc-0112`, the chosen span aligned to an overlapping source fragment and surfaced only a comma omission. The benchmark's broader rewrite was outside that comparison.
- All 24 scored quote false positives are unquoted passages. The evaluator counts a flag as a false positive whenever it has no matching altered label. The unified benchmark dictionary treats unlabeled passages as unadjudicated because the labels are a sample. The inventory preserves the evaluator's outcomes and marks these flags pending adjudication. The 24 flags give the evaluator's reported 67.1% precision (49 ÷ 73).
- All 20 corrupt-target false alarms were driven by copied-passage flags. Nineteen had one flag each. `doc-0056` had two (`q2` and `q11`), correcting the single-flag description in the committed unified scorecard. Nine of these 20 documents have labeled natural misquotes and score as positives under the any-labeled-error target. In five of those nine, a driver actually matched a labeled quote. In the other four, the document received credit through a different passage with no matching altered label. The other 11 documents are false alarms under both targets and remain pending adjudication.
- All 14 missed documents under the any-labeled-error target had zero risk and at least one missed natural misquote. Thirteen had only extraction misses. `doc-0197` had both an extracted passage whose restrictive wording was accepted and a separate extraction miss. Its document row takes the lenient match as primary and retains extraction as a contributing cause. The same 11 false alarms appear under both document targets and have one row for each target.

## Taxonomy and supporting evidence

| Category | Evidence used to assign it |
|---|---|
| Extraction miss | The normalized target is in the DOCX and no candidate covers it in full. |
| Corpus gap | The relevant authority or source passage is missing from the corpus. The two Title 11 exclusions illustrate this gap. It has zero primary scored rows. |
| Lenient fuzzy match | A candidate covers the target, and the comparison accepts a substantive changed condition as low severity. This includes the materiality filter applied after matching. |
| Paraphrase | Rewording contributes to a missed target or an unquoted flag, such as where introductory wording supplies a modal outside the compared span. |
| Formatting variant | Punctuation or presentation affects comparison. One accepted candidate reports only a punctuation difference after aligning to a narrower span. |
| Benchmark label conflict | The source document and exact corpus match support an existence verdict that conflicts with the earlier answer key. |
| Copied-passage boundary | A candidate includes explanatory or application language beyond the matched source boundary. |
| Source attribution | The candidate is compared with another authority or a different cited provision in context. |
| Document target mismatch | The same document is clean under the corrupt-condition target and positive under the any-labeled-error target. |
| Copied-passage risk aggregation | An unquoted flag without a matching altered label is sufficient to raise document risk to medium or higher. |
| Unresolved | The draft and matched span alone do not establish whether the flagged difference changes meaning. |

Strict citation extraction had 270 unmatched rows (197 more-specific subsection or list captures, 32 key strings absent verbatim, and 41 present but unmatched). The existence evaluator uses authority-level matching and missed zero scored fabrications. The current red-team probes also show two separate risks outside the frozen score: base-section matching can accept an invented subsection, and the extractor can skip a short-form `Id.` cite. These diagnostics do not contribute to the fabrication ranking.

## Reproduction

Both runs processed 200 documents in isolated exports of the following repository commits. The document and corpus trees were identical across exports. The unified run confirmed its answer-key hash against the evaluator's frozen hash and processed all documents with zero pipeline errors.

| Baseline | Commit | Answer-key SHA-256 |
|---|---|---|
| Earlier | `926f55de5d415e7fc238b5c036288ad0abc20ab4` | `ae28eb0ef4c16747768be58aa35864236baa747af9d28ed64f11f788f61f8af8` |
| Unified | `65b6e6c19ba658bf34feae94a1a2c6d298c48b6c` | `7829926799fccd1e2d6ad4a2546ea28f3609a1888f1132110161c5304aa16f96` |

Run the following from the corresponding checkout with the dependencies in `requirements.txt` installed.

```sh
# Earlier commit
python scripts/extract_all_documents.py
python scripts/extract_all_citations.py
python scripts/verify_citations.py
python scripts/evaluate_existence.py
# Unified commit
python scripts/detect.py --evaluate --strict
```

The earlier script writes `data/processed/existence-evaluation.json`. The unified command writes evaluator JSON and `reports.jsonl` under `data/processed/detect/`. The inventory reconciles to both runs' evaluator counts and preserves their scoring policies.
