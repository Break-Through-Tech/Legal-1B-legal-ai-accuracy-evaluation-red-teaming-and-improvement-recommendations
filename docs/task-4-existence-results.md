# Task #4 — Citation Existence Evaluation

Across all 200 documents, the detector caught **273 of 278 labeled fabrications: 98.20% recall**. Labeled-prediction precision was **100.00%**, and F1 was **99.09%**. No detector tuning or benchmark changes were made.

## Results

Positive means fabricated (`exists: false`). Authorities are deduplicated per document by statute base section, rule family/number, or case reporter citation. Subsections, case names, and pinpoint pages do not distinguish authorities for this existence task. Bare rules are civil; evidence rules remain separate.

| View | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| end to end | 273 | 0 | 5 | 2107 | 100.00% | 98.20% | 99.09% |
| verifier only | 273 | 0 | 5 | 2107 | 100.00% | 98.20% | 99.09% |

End-to-end scoring counts unextracted fabrications as false negatives. Verifier-only scoring includes matched authorities with a decided prediction. These views happen to agree here because all labeled fabrications were extracted. Unextracted real authorities are coverage gaps, not true negatives. Unexpected abstentions or conflicting predictions are audited and count as misses for positive end-to-end targets; neither receives verifier-only credit.

| Slice (end-to-end) | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| type:rule | 88 | 0 | 0 | 358 | 100.00% | 100.00% | 100.00% |
| condition:corrupt | 273 | 0 | 5 | 1033 | 100.00% | 98.20% | 99.09% |
| fabrication:fabricated_rule | 88 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| type:statute | 134 | 0 | 5 | 740 | 100.00% | 96.40% | 98.17% |
| fabrication:fabricated_statute | 134 | 0 | 5 | 0 | 100.00% | 96.40% | 98.17% |
| type:case | 51 | 0 | 0 | 1009 | 100.00% | 100.00% | 100.00% |
| condition:clean | 0 | 0 | 0 | 1074 | N/A | N/A | N/A |
| fabrication:wrong_reporter | 30 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| fabrication:fabricated_case | 21 | 0 | 0 | 0 | 100.00% | 100.00% | 100.00% |

N/A means a zero denominator; machine-readable metrics use `null`. Fabrication-type slices contain positive targets only, so their precision does not measure false positives on real citations.

## Coverage and audit

- The pipeline extracted and verified 8,379 mentions across 200 documents. Raw verification totals: 8,104 true, 273 false, and 2 out-of-scope mentions.
- The 3,490 answer-key entries reduce to 2,398 document/authority targets. One excluded target leaves 2,397 scoring targets; 2,385 were extracted (99.50% coverage). The 12 missing targets are real authorities.
- Excluded `AS 11.56.807` in `doc-0136`, per DATA_DICTIONARY §3.2. Its repeated mentions count as one excluded authority.
- There are 46 extracted document/authority targets (135 mentions) absent from the key. They are retained for audit, without assumed labels. No unexpected abstentions or conflicting predictions occurred among scored key targets.
- Precision covers labeled predictions only. These results do not establish precision on every extracted reference or generalize beyond this Alaska family-law benchmark.

### Five missed fabrication labels

| Document | Key citation | Prediction |
|---|---|---|
| doc-0059 | AS 25.24.900 | exists: true |
| doc-0110 | AS 25.24.910 | exists: true |
| doc-0152 | AS 25.24.910 | exists: true |
| doc-0182 | AS 25.24.920 | exists: true |
| doc-0198 | AS 25.24.900 | exists: true |

All five are verifier misses against the answer key, not extraction failures. The corpus contains the corresponding base sections (`AS 25.24.900`, `AS 25.24.910`, and `AS 25.24.920`), while the answer key labels these references false. The report retains those labels and counts all five as false negatives; this discrepancy warrants dataset-owner review rather than tuning the detector to the key.

## Reproduce

From the repository root, using the existing virtual environment:

```bash
.venv/bin/python scripts/extract_all_documents.py
.venv/bin/python scripts/extract_all_citations.py
.venv/bin/python scripts/verify_citations.py
.venv/bin/python scripts/evaluate_existence.py
.venv/bin/python -m unittest discover -s tests
```

Detailed metrics, per-document counts, exclusions, false positives, missed fabrications, missing real targets, and unmatched extraction evidence are written to `data/processed/existence-evaluation.json` (generated and ignored by Git). The evaluator requires exactly 200 unique matching document IDs, validates labels and predictions, and rejects conflicting answer-key labels for a normalized authority. Detector inference never reads the answer key.

Annotation evaluation is deferred in the verifier and quote module so the existing Python 3.9 virtual environment can import them; detector behavior and interfaces are unchanged.
