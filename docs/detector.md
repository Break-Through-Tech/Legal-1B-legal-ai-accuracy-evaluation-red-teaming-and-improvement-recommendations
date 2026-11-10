# Unified hallucination detector

`src/detect.py` chains every stage of the pipeline for one document:

```
.docx ─► extract text ─► extract citations ─► verify (corpus) ─► classify ─► quote check ─► risk score
         src/extraction  src/citation_extractor  src/verifier    src/classify  src/quote_fidelity  src/risk
```

It returns one JSON report per document. The report has one **flag** for every citation and for every quoted or copied passage, each with a stage and a severity, plus a **document risk score**. The same API serves a future upload frontend and the benchmark batch run.

## Python API (for the frontend)

```python
from src.detect import Detector

detector = Detector()        # loads the corpus and quote index once (~0.2 s); reuse it for every request
report = detector.check(uploaded_bytes, filename="motion.docx")
```

- `check(file, filename=None, doc_id=None, include_text=True, include_unquoted=True)`
- `file` can be a path, `bytes`, or a binary file-like object (an upload stream). Uploads never touch disk.
- `check` **never raises for a bad document**. If a stage fails, the failure is recorded in `errors` and the remaining stages still run. Tracebacks go to the log, not the report, because reports may be shown to end users. Error stages are `extract` (the file could not be read; risk is `unknown`), `extract_citations`, `verify`, `classify` and `quote_check`.
- The batch run works on any folder of `.docx` files (`--input DIR`, any capitalisation of `.docx`; Word `~$` lock files are skipped). `--evaluate` scores only benchmark documents, recognised by file SHA-256 against `manifest.json`, not by name: a renamed benchmark copy is scored, an unrelated file called `doc-0001.docx` is not. Other documents are still checked and reported, just not scored; `scorecard.json` meta lists them in `unscored_documents` and records `full_benchmark`. With no benchmark documents in the run, no scorecard is written.
- Typical cost is about 20 ms per document (p95 about 55 ms). About 80% of that is the quote check.

## Report schema

```jsonc
{
  "doc_id": "motion",                 // filename stem, or the doc_id you pass
  "filename": "motion.docx",
  "source_sha256": "…",               // hash of the uploaded bytes
  "risk": {
    "score": 0.84,                    // 0..1, null if the file could not be read
    "level": "high",                  // none | low | medium | high | unknown
    "drivers": ["2 fabricated citations"],   // plain-English summary, most severe first
    "problems": 2,                    // distinct problems counted in the score
    "incomplete": false               // true if any stage failed: the score may be too low
  },
  "summary": {"citations": 31, "citations_flagged": 3, "quotes": 6, "quotes_flagged": 0,
              "by_severity": {"high": 3, "medium": 0, "low": 0}},
  "flags": [ /* one per citation and per passage, in document order; see below */ ],
  "errors": [{"stage": "quote_check", "type": "ValueError", "message": "…"}],
  "runtime": {"total_ms": 15.2, "extract_ms": 4.1, "verify_ms": 0.1, "classify_ms": 0.1, "quote_check_ms": 10.8},
  "text": "…"                         // extracted text; flag start/end index into it (include_text=True)
}
```

### Flag

| Field | Meaning |
|---|---|
| `flag_id` | `c<n>` for citations, `q<n>` for passages |
| `stage` | `existence` (citation checked against the corpus) or `quote_fidelity` (passage checked against source text) |
| `item_type` | `citation`, `quoted` (inside quotation marks), or `unquoted` (long run copied from a source without quotation marks) |
| `citation_type` | `statute`, `rule`, or `case` (citations only) |
| `text`, `start`, `end`, `context` | The flagged text, its character offsets in `report.text`, and the surrounding sentence, for highlighting |
| `status` | Citations: `Valid/Verified`, `Hallucinated`, `Wrong Case Name`, `Wrong Year`, `Mismatched Context/Format`. Passages: the quote checker status (see below). |
| `flagged` | `true` when a problem was detected. Clean items are still listed with `false`. |
| `severity` | `high`, `medium`, `low`, or `null` when not flagged |
| `message` | User-facing explanation in plain English |
| `reason` | Short technical reason |
| `evidence` | Corpus ids and matched citations, case name/year `mismatches`, matched source text, word-level diffs, match score, normalized `authority` key |

### Severity

| Stage | Status | Flagged | Severity |
|---|---|---|---|
| existence | `Hallucinated` (not in corpus) | yes | high |
| existence | `Wrong Case Name` (the reporter cite is real but belongs to a differently named case, e.g. a made-up name on a real cite; short forms like "Perry v. Perry" still match) | yes | high |
| existence | `Wrong Year` (case found, cited year differs from the corpus) | yes | low |
| existence | `Valid/Verified` | no | none |
| existence | `Mismatched Context/Format` (AS 11.56.807 / .810: real law outside the corpus) | no | none |
| quote_fidelity | `material_difference` (words added, dropped or changed in a way that changes the law) | yes | from the diff: high when it touches a modal, negation, quantifier, conjunction or number (`shall`, `not`, `all`, `or`, …), otherwise medium |
| quote_fidelity | `misattributed`, `not_found` | yes | checker severity |
| quote_fidelity | `found_elsewhere` (the cited authority is fabricated, but the text exists in another source) | no | none. `evidence.related_flag` points to the fabricated citation's flag, so the problem is not counted twice. |
| quote_fidelity | `verified`, `minor_differences`, `paraphrased`, `source_unavailable`, `no_source_match` | no | none |

## Risk score

Defined in `src/risk.py`:

```
score = 1 − Π (1 − weight)    over distinct flagged problems
weights: high 0.6 · medium 0.3 · low 0.1
level:   none (0) · low (< 0.3) · medium (≥ 0.3) · high (≥ 0.6)
```

- One fabricated citation scores 0.6 and gives level **high**. Two score 0.84, three score 0.936.
- Mentioning the same fabricated authority again does not raise the score. Every mention is still flagged for highlighting.
- The score never decreases as problems are added, and it stays below 1.
- The thresholds are a **policy, not fitted to the benchmark**. The benchmark could be separated perfectly at 0.84, but only because nearly every corrupt document had two or more fabrications planted. A real document with one fake citation is just as dangerous. See [accuracy-scorecard.md](accuracy-scorecard.md).

## Batch run and evaluation

```bash
source .venv/bin/activate
python scripts/detect.py --evaluate              # all 200 benchmark docs + accuracy scorecard (~8 s)
python scripts/detect.py doc-0001 doc-0136       # a subset
python scripts/detect.py --input path/to/docx/   # any folder of .docx (e.g. a new generator version)
python scripts/detect.py brief.docx --show       # any new document(s): print every flagged item
python scripts/evaluate_all.py --compare old/scorecard.json   # re-score, with a before/after table
```

Options: `--out DIR` (default `data/processed/detect/`), `--quoted-only`, and `--strict` (exit 1 if any document errored).

Outputs (gitignored):

| File | Contents |
|---|---|
| `reports.jsonl` | One full report per document |
| `flags.jsonl` | One line per flag, with `doc_id`, ready for pandas |
| `run-log.json` | Run id, git commit and dirty state, setup time, per-document and per-stage runtime (mean/median/p95/max), flag counts by stage × severity, documents by risk level, errors |
| `logs/detect-<run_id>.log` | One line per document, plus full tracebacks for any errors |
| `scorecard.json` / `scorecard.md` | Accuracy summary (with `--evaluate` or `scripts/evaluate_all.py`) |
| `*-evaluation.json` | Full per-evaluator details: misses, false positives, audit lists |

## Accuracy functions

`src/evaluation/` holds pure functions (data in, dict out) that run on detector reports and the answer key:

| Function | What it measures |
|---|---|
| `scorecard(key, reports)` | Everything below, with headline numbers, 95% bootstrap CIs over documents, slices, failure counts and caveats |
| `render_markdown(card)`, `compare(a, b)` | Tables for reports; before/after deltas |
| `existence.evaluate_existence` | Fabricated-citation P/R/F1 (moved from `scripts/evaluate_existence.py`) |
| `quotes.evaluate_quotes`, `quote_recall_by_origin` | Altered-quote P/R/F1, and planted vs natural recall (moved from `scripts/evaluate_quotes.py`) |
| `extraction.evaluate_extraction` | Citation extraction recall (moved from `scripts/evaluate_extraction.py`) |
| `risk.evaluate_risk`, `sweep`, `split_stability` | Document-level clean vs corrupt: AUC, P/R/F1 per level, threshold sweep, even/odd halves |
| `runtime.runtime_stats` | Runtime percentiles and error rate |
| `adapters.*` | Convert reports to the row formats of the old stage scripts |

The old stage scripts (`extract_all_citations.py`, `verify_citations.py`, `classify_citations.py`, `check_quotes.py`, `evaluate_*.py`) still work. The detector reproduces their outputs exactly: on all 200 documents, its verification rows, quote rows and extracted text are identical to theirs.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests
```
