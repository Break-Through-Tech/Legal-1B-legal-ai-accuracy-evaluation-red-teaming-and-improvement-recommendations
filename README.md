# Legal AI Accuracy Evaluation and Hallucination Detection

This Break Through Tech AI Studio project, developed with ProSe AI, evaluates AI-generated Alaska family-law documents for fabricated legal citations and inaccurate quotations. The repository provides a reproducible pipeline that extracts citations, verifies authorities against a frozen legal corpus, checks quoted or copied legal text, and produces document-level risk reports.

## Project highlights

- Processes all 200 documents in the frozen benchmark through one detector.
- Extracts Alaska statutes, civil and evidence rules, and case citations.
- Verifies citations against 2,000+ corpus records using authority-specific matching.
- Detects altered, misattributed, and unsupported legal passages.
- Produces structured flags, explanations, evidence, runtime data, and a document risk score.
- Supports paths, uploaded bytes, and file-like objects without writing uploads to disk.

## Current results

| Metric | Result |
|---|---:|
| Fabricated-citation recall | 100.0% |
| Fabricated-citation precision | 100.0% |
| Altered-quote recall | 61.3% |
| Altered-quote precision | 67.1% |
| Document-level F1, clean vs. corrupt | 91.2% |
| Citation extraction recall | 92.3% |
| Median runtime per document | 20.3 ms |
| Pipeline errors on 200 documents | 0 |

These results are measured on the same 200 documents used during development. There is currently no untouched held-out test set, so the results should be treated as in-sample benchmark performance rather than an estimate of performance on new legal documents.

See [the accuracy scorecard](docs/accuracy-scorecard.md) for confidence intervals, error slices, counting policies, and limitations.

## Pipeline

```text
DOCX
  -> document text extraction
  -> citation extraction
  -> corpus existence verification
  -> citation classification
  -> quote-fidelity checking
  -> document risk scoring
  -> JSON report
```

The detector distinguishes:

- Verified authorities
- Fabricated citations
- Incorrect case names or years
- Real authorities known to be outside the benchmark corpus
- Materially altered quotations
- Misattributed or unsupported legal passages

Implementation details and the output schema are documented in [docs/detector.md](docs/detector.md).

## Setup

```bash
git clone https://github.com/Break-Through-Tech/Legal-1B-legal-ai-accuracy-evaluation-red-teaming-and-improvement-recommendations.git
cd Legal-1B-legal-ai-accuracy-evaluation-red-teaming-and-improvement-recommendations
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Run the detector

Evaluate the complete frozen benchmark:

```bash
python scripts/detect.py --evaluate
```

Check selected benchmark documents:

```bash
python scripts/detect.py doc-0001 doc-0136
```

Check new DOCX files:

```bash
python scripts/detect.py path\to\document.docx --show
python scripts/detect.py --input path\to\document-folder
```

Generated reports are written under `data/processed/detect/` and are excluded from version control.

## Python API

```python
from src.detect import Detector

detector = Detector()
report = detector.check("path/to/document.docx")

print(report["risk"])
print(report["flags"])
```

The detector also accepts uploaded bytes or binary file-like objects. Reuse one `Detector` instance so the corpus is loaded only once.

## Tests

```bash
python -m unittest discover -s tests
```

## Repository structure

| Path | Purpose |
|---|---|
| `src/` | Extraction, verification, quote checking, classification, risk scoring, and unified detector |
| `scripts/` | Command-line pipeline and evaluation entry points |
| `tests/` | Unit and integration tests |
| `data/benchmark/` | Frozen documents, answer key, manifest, and data dictionary |
| `data/corpus/` | Alaska statutes, rules, evidence rules, and case records |
| `docs/` | Methodology, benchmark analysis, results, caveats, and scorecards |

## Team contributions

| Contributor | GitHub | Primary contributions |
|---|---|---|
| Chikanma Okoisor | [@Kami1230](https://github.com/Kami1230) | Document cleaning, corpus verifier, pipeline consolidation, shared corpus APIs |
| Aadhya Pandillapally | [@aadhyapa](https://github.com/aadhyapa) | Corpus analysis, quote-fidelity checker, pipeline integration |
| Mokshil Shah | [@Mokshil28](https://github.com/Mokshil28) | Citation extractor, extraction evaluation, accuracy analysis |
| Erionila Mane | [@erionila-mane](https://github.com/erionila-mane) | Citation classification and reporting logic |
| Brant Bueno | [@bfajardo1105](https://github.com/bfajardo1105) | Benchmark exploration and analysis |
| Zahel Nasari | [@zn2211](https://github.com/zn2211) | Evaluation handoff and improvement-report work |

## Known limitations and next steps

- Build and preserve an untouched held-out evaluation set.
- Improve recall for naturally occurring paraphrase-style misquotes.
- Reduce false alarms from unquoted copied passages.
- Distinguish unknown authorities from fabricated authorities when operating beyond the fixed corpus.
- Complete failure taxonomy, regression cases, final evaluation notebook, and improvement recommendations.

## Documentation

- [Unified detector](docs/detector.md)
- [Accuracy scorecard](docs/accuracy-scorecard.md)
- [Quote-fidelity checker](docs/quote-fidelity-checker.md)
- [Citation existence results](docs/task-4-existence-results.md)
- [Citation extraction results](docs/task-6-extraction-results.md)
- [Benchmark freeze and label schema](docs/benchmark-freeze-and-label-schema.md)
- [Benchmark and corpus caveats](docs/benchmark-corpus-connections-and-caveats.md)

## Acknowledgements

This project was completed through the Break Through Tech AI Studio in partnership with ProSe AI. We thank challenge advisor Benjamin Booker, AI Studio coach Nagalakshmi Pulivarthi, and the Break Through Tech team for their guidance.
