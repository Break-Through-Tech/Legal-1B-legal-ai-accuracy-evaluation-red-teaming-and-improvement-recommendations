# Task 6 — Extraction Accuracy Report

**The extractor processed 200 documents and found 8,379 citation mentions. Overall normalized exact recall was 92.89%; provision coverage was 99.38% when extra subsections were credited.**

| Citation type | Extracted mentions¹ | Matched / expected² | Exact recall |
|---|---:|---:|---:|
| Statutes | 4,312 | 1,412 / 1,546 | 91.33% |
| Rules | 2,450 | 680 / 772 | 88.08% |
| Cases | 1,617 | 1,057 / 1,072 | 98.60% |
| **Total** | **8,379** | **3,149 / 3,390** | **92.89%** |

¹ Mentions include repeats. ² Recall counts unique normalized citations within each document. The answer key has 3,490 entries; normalization merges 100 equivalent entries. Matching ignores whitespace/case differences, supported introductory case signals, and pinpoint pages; civil/evidence rule aliases are normalized. Subsections remain exact and bare rules remain distinct.

| Reason for exact mismatch | Count | What it means |
|---|---:|---|
| Extra subsections, ranges, or lists captured | 220 | Key expects `(a)`; output captures forms such as `(a)(4)` |
| Multi-period case initials | 12 | Names such as `D.D. v. L.A.H.` fail the case pattern |
| Extra introductory words in case name | 3 | Output includes words such as `The` or `As` |
| Bare-rule versus civil-rule difference | 3 | Key and output use different rule-family labels |
| Key subsection absent from cleaned text | 3 | Answer-key/text discrepancy requiring review |
| **Total exact mismatches** | **241** | **Most are differences in citation detail** |

Crediting the 220 references captured with additional subsections/lists gives **3,369 / 3,390 = 99.38% provision coverage**, with 21 entries still unmatched. This measures broader provision detection, not exact citation boundaries or expansion of every range member.

**Next fixes:** support multi-period initials, remove introductory prose from case names, and review rule-family differences and the three answer-key discrepancies. Short-form cases, lowercase party-name connectors, and other reporters remain unsupported. Citation existence, quote accuracy, and precision were not evaluated.

Reproduce from the repository root with an existing `.venv`:

```bash
source .venv/bin/activate
python scripts/extract_all_citations.py
python scripts/evaluate_extraction.py
```

Detailed per-document results and missed examples: `data/processed/extraction-evaluation.json` (generated locally).
