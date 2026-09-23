# Task #4 Plan — Clean & Standardize Documents

**Status:** Draft — needs a couple of decisions before implementation starts (see "Open questions" at the end).
**Owner task:** Task #4 on the team task list — "Normalize text extraction from DOCX, strip noise,
standardize whitespace/encoding, informed by learnings from Task #1 & #3."

---

## 1. Problem overview

Task #5 (build the citation extractor) needs one thing as input: **clean, consistent plain text
for each of the 200 benchmark documents**, so regex/pattern matching can run reliably against
it. Right now nothing in the repo does that extraction — every prior exploration session
(`docs/benchmark-exploration.md`, `docs/citation-corpus-exploration.md`) re-implemented
throwaway extraction code from scratch. Task #4's job is to build that one small, reusable
piece *once*, based on what's already been learned about the documents, so Task #5 can just
call a function and get text back.

This is a narrow task. It is not the citation extractor, not the normalizer that maps
`Civil Rule 90.3(a)` to a corpus lookup key, and not a cleaning pass over the corpus JSONL
files. Those are explicitly out of scope here (see §3).

## 2. What we already know (from Task #1/#3 exploration — no new investigation needed)

Verified directly against the files, not just assumed:

- **All document text lives in `word/document.xml`**, read via `paragraph.text` — not runs.
  `footnotes.xml`, `endnotes.xml`, and `comments.xml` are present in all 200 files but contain
  **zero characters of text** in every one, so they can be skipped entirely.
  (`docs/benchmark-exploration.md` §2.1)
- **Paragraphs are noisy with blank spacer paragraphs.** Spot-checked `doc-0001.docx`:
  97 total paragraphs, only 48 non-empty. Filtering with `if p.text.strip()` removes this
  noise — this matches the pattern already used in earlier exploration scripts.
- **No double-spaces or tab characters found** in the paragraph text of the doc checked, and
  `docs/benchmark-exploration.md` §8 independently confirms the documents use **only straight
  ASCII quotes** (no curly/typographic quotes) — so there is **no Unicode/mojibake problem in
  the documents themselves**. (I also directly grepped `data/corpus/*.jsonl` for the mojibake
  marker `â€` used by curly-quote-in-Latin-1 corruption and found zero matches — an apparent
  garbled-character issue seen earlier in this session's terminal turned out to be a display
  artifact, not real data corruption. **The corpus does not need encoding cleanup.**)
- **Every document follows the identical 5-section skeleton** (`I. INTRODUCTION` … `V.
  CONCLUSION`) and an identical caption block. (`docs/benchmark-exploration.md` §2.3)
- **All 3,490 answer-key citation strings were found essentially verbatim in body paragraph
  text** (5 exceptions are answer-key artifacts, not extraction problems — see
  `docs/benchmark-exploration.md` §7.6). This means **the cleaning bar is low**: we are not
  fixing broken/garbled source text, we are standardizing formatting so downstream regex
  matching is consistent and easy to reason about.

**Conclusion:** this task is mostly about writing one well-tested, boring function — not
solving a hard data-quality problem. The data is already clean; we just need a single
consistent way to pull it out of `.docx` and hand it to Task #5.

## 3. Scope

**In scope:**
- Extracting plain text from each `.docx` benchmark document (paragraphs only, footnotes/
  endnotes/comments skipped since they're empty).
- Dropping empty/whitespace-only paragraphs.
- Collapsing incidental whitespace (multiple spaces, trailing/leading whitespace) so string
  matching in Task #5 isn't tripped up by formatting noise.
- A way to run this over all 200 documents and get the result back per `doc_id`.

**Out of scope (explicitly deferred to later tasks):**
- Normalizing *citation format* (e.g. `Civil Rule 90.3(a)` → `90.3`, stripping statute
  subsections, reporter-citation extraction) — that belongs to Task #5's extractor/lookup
  logic, not to text cleaning.
- Touching or rewriting the corpus JSONL files (`data/corpus/*.jsonl`) — they are frozen,
  already clean (verified above), and DATA_DICTIONARY.md explicitly says the benchmark is
  frozen; we should not modify inputs we don't own.
- Section/heading segmentation, caption-block stripping, or removing the printed `(doc-NNNN)`
  document ID from body text. These are real but **cosmetic** observations from
  `benchmark-exploration.md` §2.3, not blockers for citation extraction — adding them now
  would be solving a problem Task #5 doesn't actually have yet.

## 4. Proposed approach

One small module, one function, no class hierarchy, no config system:

```
src/
  extraction.py      # extract_document_text(path) -> str
```

```python
# src/extraction.py
import re
import docx

def extract_document_text(docx_path) -> str:
    """Read a benchmark .docx and return clean, whitespace-normalized body text."""
    doc = docx.Document(docx_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs]
    paragraphs = [p for p in paragraphs if p]           # drop blank spacer paragraphs
    text = "\n".join(paragraphs)
    text = re.sub(r"[ \t]+", " ", text)                 # collapse repeated spaces/tabs
    return text
```

That's the entire cleaning step. No footnote/endnote handling is needed (they're empty), no
encoding fixes are needed (verified clean), no section parsing is needed (out of scope).

For running it over all 200 documents, a tiny script (not a new abstraction — just a loop):

```
scripts/
  extract_all_documents.py   # loops data/benchmark/documents/*.docx, calls extract_document_text,
                              # writes data/processed/documents.jsonl (doc_id + text)
```

This gives Task #5 one place to read clean text from (`data/processed/documents.jsonl`)
instead of every future script re-running `python-docx` extraction itself.

## 5. Files to add / change

| Path | Change | Why |
|---|---|---|
| `src/extraction.py` (new) | Add `extract_document_text()` | The one reusable cleaning function |
| `scripts/extract_all_documents.py` (new) | Add batch runner | Produces the cleaned corpus once, so Task #5 doesn't reparse `.docx` repeatedly |
| `data/processed/documents.jsonl` (new, generated) | Output of the batch script: `{"doc_id": ..., "text": ...}` per line | Single, reusable clean-text artifact for downstream tasks |
| `requirements.txt` | Add `python-docx` | Needed to read `.docx`; currently empty |
| `docs/` | *(no new doc needed yet)* | This plan replaces a write-up until there's something worth reporting after implementation |

Nothing under `data/corpus/` or `data/benchmark/` (the frozen inputs) is modified.

## 6. Alternatives considered

1. **Precompute `data/processed/documents.jsonl` vs. extract on-demand every time.**
   Chosen: **precompute**. Parsing 200 small `.docx` files is fast (well under a second each),
   so on-demand would also work — but a single generated file means Task #5, evaluation
   notebooks, and anyone else on the team all read the *same* clean text without needing
   `python-docx` installed or re-running extraction, and it's trivial to regenerate if the
   cleaning function changes. Rejected the "no cache file, always parse live" option because
   it would force every downstream script to import our module and depend on `python-docx`
   just to get text, for no real benefit.

2. **A full `Document` class wrapping paragraphs/sections/metadata.**
   Rejected — nothing downstream needs section-aware structure yet (Task #5 works off flat
   citation regexes; section-level analysis in `benchmark-exploration.md` was for
   understanding, not for building on top of). A plain string is the "what we need right now"
   answer. If Task #5 or #6 later needs section-aware context, add it then.

3. **Cleaning/normalizing the corpus JSONL files too.**
   Rejected for this task — verified they're already clean (no mojibake, `DATA_DICTIONARY.md`
   asserts the benchmark is frozen and hash-verified). Touching frozen inputs is also a
   reusability risk: the project's success criterion is being able to re-run everything in
   January against an *updated* generator output, so scripts should read the frozen corpus
   as-is, not maintain a modified copy of it.

4. **A config-driven / pluggable cleaning pipeline (e.g. list of cleaning "steps" you can
   add/remove/reorder).**
   Rejected — there is exactly one cleaning need right now (strip blank paragraphs, collapse
   whitespace). A configurable pipeline is solving for hypothetical future cleaning steps that
   don't exist yet. If a second real cleaning need shows up, add a second line to the function;
   don't build a plugin system for one function.

## 7. Things to avoid while building this

Per team guidance, and specific to this task:

1. **No abstractions for problems we don't have yet.** No `TextCleaner` base class, no
   strategy pattern, no plugin registry. One function. If it grows past ~20 lines, that's a
   signal to stop and ask whether the scope crept, not to refactor into more structure.
2. **Keep the code boring and obvious.** A teammate should be able to read
   `extract_document_text()` top to bottom in 10 seconds and know exactly what it does. Prefer
   `re.sub` one-liners over building a tokenizer.
3. **Don't touch the frozen benchmark/corpus files.** Read-only access. All output goes to a
   new `data/processed/` folder, never back into `data/benchmark/` or `data/corpus/`.
4. **Don't pre-solve Task #5's problems here.** Citation regex patterns, corpus-lookup
   normalization (subsection stripping, rule number reduction, reporter-citation extraction)
   belong in Task #5, even though some of that logic is easy to imagine while already looking
   at this text. Keep this task's diff small and single-purpose.
5. **Validate before scaling.** Run the function on 2–3 documents and manually eyeball the
   output before running it across all 200 and generating `documents.jsonl`.

## 8. Definition of done

- `src/extraction.py` exists with one tested function.
- Running the batch script produces `data/processed/documents.jsonl` with exactly 200 records,
  one per `doc_id` in `data/benchmark/manifest.json`.
- Spot-check: for 3–5 documents, every answer-key `cite` string for that `doc_id` is still
  found in the cleaned text (this is the same verbatim-match check already used in exploration
  — it should still pass after cleaning, confirming nothing was accidentally stripped).
- No changes to any file under `data/benchmark/` or `data/corpus/`.

## 9. Open questions (need an answer before/while implementing)

1. **Precompute output location** — is `data/processed/documents.jsonl` the right spot, or
   would you rather keep it inside `data/benchmark/` (e.g. `data/benchmark/documents_clean.jsonl`)
   next to the other benchmark artifacts?
   - `data/processed/documents.jsonl` would be the output location for cleaned data.
2. **`src/` as the package root** — is `src/` the right place to start the reusable Python
   module (matching the project overview's eventual "clean, documented Python module" goal),
   or do you have a different preferred package name/location for the team?
   - yes
3. **Scope check on whitespace collapsing** — is collapsing internal repeated
   spaces/tabs enough, or is there a specific formatting issue you've already run into that
   this plan doesn't cover?
   - so far yes.