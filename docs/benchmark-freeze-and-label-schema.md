\# Milestone #3 — Task #1: Freeze Benchmark and Define Labels



\*\*Project:\*\* Legal 1B — Legal AI Accuracy Evaluation, Red-Teaming, and Improvement Recommendations  

\*\*Host Company:\*\* ProSe AI  

\*\*Milestone:\*\* End-to-End Detection and Failure Analysis  

\*\*Task:\*\* Freeze Benchmark and Define Labels  

\*\*Branch:\*\* `task1-freeze-benchmark-labels`



\## 1. Purpose



The purpose of this task is to establish a reproducible benchmark for evaluating hallucinated legal citations and quotation errors in AI-generated Alaska family-law documents.



The benchmark must remain unchanged during evaluation. Any adjustments to detection logic, scoring rules, or evaluation procedures must be documented to ensure transparent and reproducible results.



\## 2. Frozen Benchmark Information



The benchmark contains 200 AI-generated legal documents, together with a corrected answer key and manifest.



| Item | Verified Information |

|---|---|

| Total documents | 200 |

| Clean documents | 97 |

| Corrupt documents | 103 |

| Citation entries | 3,584 |

| Unique normalized authority targets | 2,493 |

| Eligible citation-scoring targets | 2,491 |

| Planted fabricated citations | 273 |

| Planted quote alterations | 40 |

| Natural misquotes | 40 |

| Faithful quote rows | 122 |

| Total planted errors | 313 |



The corrected benchmark was retrieved from the repository's main branch.



\*\*Frozen Git commit:\*\*



`b3a8b736cc517461f1ccf9e3bc71a6bb9e86f691`



\## 3. Benchmark Integrity Verification



All 200 Word documents were checked against the SHA-256 values recorded in `manifest.json`.



\*\*Verification result: PASS — All 200 document hashes match.\*\*



The following SHA-256 hashes were also recorded:



\*\*answer-key.json\*\*



`8CE6F0BC7D3FAC45C7EFA2A2B4DF48702D3078D5674A4B6D079C633E8DFC922E`



\*\*manifest.json\*\*



`6FF50A2FAD4C231698721DA7612FE4E3AC745DEAB165E8349F877D259558742C`



These hashes identify the benchmark files used for this evaluation. Future evaluations should confirm that the files still match these values.



\## 4. Citation Label Definitions



Citation labels are defined using the corrected `answer-key.json` and the benchmark's official `DATA\_DICTIONARY.md`.



\### Valid / Existing Citation



\*\*Label:\*\* `exists: true`



The citation refers to a real legal authority present in the benchmark corpus.



\### Fabricated Citation



\*\*Label:\*\* `exists: false`



The authority is absent from the benchmark corpus and is labeled as fabricated by construction, except for the two documented exclusions.



The `injected` field identifies the corruption type when applicable.



\### Excluded Citation



The following references are genuine Alaska laws outside the benchmark corpus:



\- `AS 11.56.807`

\- `AS 11.56.810`



Both appear in `doc-0136` and must be excluded from Stage-2 existence scoring.



They must not be counted as fabricated legal authorities merely because they are absent from the corpus.



\### Injection Metadata



The `injected` field records the type of citation corruption when applicable.



A value of `false` identifies an untouched citation, including the five corrected injected statutes that were subsequently confirmed to refer to real sections.



The `replaced\_real` field can identify the original citation replaced during corruption and may support failure analysis.



\## 5. Citation Normalization and Scoring Rules



Citation evaluation must use the `norm` field.



Each distinct normalized authority is scored once per document. Multiple mentions of the same authority within a document must not be counted as independent targets.



Normalization rules:



\- \*\*Statutes:\*\* Use the statute section without pinpoints. Example: `AS 25.24.160(a)(4)` becomes `AS 25.24.160`.

\- \*\*Civil Rules:\*\* Preserve the rule family and number. Example: `Civil Rule 90.3(a)` becomes `Alaska R. Civ. P. 90.3`.

\- \*\*Evidence Rules:\*\* Preserve the evidence-rule family. Example: `Alaska R. Evid. 505(a)` becomes `Alaska R. Evid. 505`.

\- \*\*Cases:\*\* Match using the reporter citation rather than the case name.



The original 3,584 citation entries reduce to 2,493 normalized authority targets. After excluding the two out-of-corpus references, 2,491 targets remain eligible for citation scoring.



Deduplication must occur within each document, not across the entire benchmark.



\## 6. Quotation Label Definitions



Quotation errors must be evaluated separately from citation existence errors.



\### Planted Quote Alteration



\*\*Label:\*\* `planted: true`



An intentionally introduced alteration to source wording.



The corrected benchmark contains 40 planted quote alterations. These are the targeted positive cases for planted-alteration evaluation.



\### Natural Misquote



\*\*Label:\*\* `planted: false` on an altered quote



A quotation error introduced naturally by the drafting model rather than deliberately planted.



The corrected benchmark identifies 40 natural misquotes. These must be evaluated and reported separately from planted alterations.



\### Faithful Quote



A quotation entry labeled as faithful to the referenced source.



The benchmark contains 122 faithful quote rows. Faithful records may represent a document-and-source pair rather than every individual passage.



\### Unlabeled Passage



A passage without an explicit quotation label must not automatically be classified as accurate or inaccurate.



Quotation labels are a sample and do not cover every passage in the documents.



\## 7. Evaluation Rules



The following rules apply to future benchmark evaluations:



1\. Evaluate citation existence at the normalized-authority level within each document.

2\. Exclude `AS 11.56.807` and `AS 11.56.810` from Stage-2 scoring.

3\. Evaluate the 40 planted quote alterations separately from the 40 natural misquotes.

4\. Do not treat unlabeled passages as negative examples.

5\. Do not count multiple mentions of the same normalized authority in one document as separate scoring targets.

6\. Preserve the distinction between genuinely nonexistent authorities and references that an automated matcher fails to locate.

7\. Calculate and report performance metrics using the appropriate eligible scoring population.

8\. Document the matching methodology, evaluation settings, and limitations.



\## 8. Benchmark Freeze and Change-Control Policy



The benchmark documents, corrected answer key, and manifest are frozen for this evaluation.



They must not be regenerated or edited as part of detector development.



Any changes to evaluation code, normalization rules, matching thresholds, or scoring procedures must be recorded.



For each change, document:



\- Date of change

\- Git commit

\- Description of the modification

\- Reason for the modification

\- Whether the frozen benchmark was inspected or used during tuning

\- Impact on evaluation results



If benchmark artifacts must change, a new benchmark version must be established, its hashes recorded, and previous results clearly distinguished from results produced with the revised version.



\## 9. Known Limitations and Considerations



The benchmark was corrected after a detailed audit of the generated documents.



These corrections included additional citation entries, updated citation labels, corrected references, and improved quotation metadata.



The updated benchmark may produce different evaluation scores from earlier versions.



These differences should not automatically be interpreted as improved or reduced detector performance.



Particular attention should be given to natural quotation errors involving subtle wording changes, such as removing terms that materially affect legal meaning.



\## 10. Verification Summary



The following steps have been completed:



\- \[x] Retrieved the corrected benchmark from the main branch.

\- \[x] Recorded the frozen repository commit.

\- \[x] Verified SHA-256 hashes for all 200 documents.

\- \[x] Recorded the answer-key SHA-256 hash.

\- \[x] Recorded the manifest SHA-256 hash.

\- \[x] Documented citation existence labels and scoring exclusions.

\- \[x] Documented planted and natural quotation-error labels.

\- \[x] Defined normalization and deduplication rules.

\- \[x] Defined requirements for recording future evaluation changes.



\*\*Benchmark integrity status: VERIFIED\*\*



The benchmark files are ready to serve as a documented reference version for subsequent detection evaluation and failure analysis.



\*\*Reference:\*\* `data/benchmark/DATA\_DICTIONARY.md`

