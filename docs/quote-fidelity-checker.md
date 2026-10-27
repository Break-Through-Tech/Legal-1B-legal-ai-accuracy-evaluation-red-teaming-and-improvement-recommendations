# Quote Fidelity Checker (Stage 3)

**The checker pulls passages a document takes from a legal source, finds that source's text in the corpus, and flags material differences. On the benchmark it caught all 40 altered quotes (100% recall) at 55% precision. With unquoted passages turned off it reaches 96% precision at 57.5% recall.**

| Mode | Flagged | Caught / altered | False positives | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Quoted passages only (`--quoted-only`) | 24 | 23 / 40 | 1 | 95.8% | 57.5% | 71.9% |
| Quoted + unquoted (default) | 73 | 40 / 40 | 33 | 54.8% | 100% | 70.8% |
| Default, high-severity flags only | 58 | 40 / 40 | 18 | 69.0% | 100% | 81.6% |

Every planted edit type was caught: 35 appended phrases, 4 substitutions (`shall`→`may`, `primary`→`sole`) and 1 dropped `not`.

## Why unquoted passages matter

17 of the 40 altered quotes are **not inside quotation marks**. The document copies a statute's wording straight into its argument, for example the AS 25.24.150(c) factor list, and the alteration sits inside that copied text. A checker that reads only quoted text tops out at 23/40. The unquoted detector finds runs of 7 or more words copied word for word from a cited source and checks how they end and what changed inside them.

## How it works

`src/quote_fidelity.py`, in pipeline order:

1. **Extract.** Quoted passages are text inside paired `"…"` or `“…”` with at least 4 words, so defined terms like `("Father")` are skipped. Unquoted passages are long verbatim runs shared with a cited source (`find_borrowed_passages`).
2. **Attribute.** Each quote gets a ranked list of nearby citations: same sentence (closest first), then a citation right after the quote, then the rest of the paragraph, then the previous cited paragraph. The checker tries each in turn. This matters for sentences like *"Under AS 25.20.070, unless … AS 25.24.150(g) …, 'the child shall have…'"*, where the nearest citation is not the source.
3. **Look up.** Corpus text is keyed the same way `src/verifier.py` keys existence: statutes by section, civil and evidence rules by rule number in separate namespaces (all subrule records), and cases by reporter cite. If the cited source has no match, a corpus-wide trigram search over all statutes and rules runs as a fallback.
4. **Align.** Word-trigram votes propose where the quote starts in the source. difflib then aligns the quote with each candidate window, and an ellipsis may stand in for any amount of omitted text.
5. **Classify.** Each word-level difference gets one label:
   - *Immaterial:* punctuation, case, hyphenation, an ellipsis omission, a dropped subsection label like `(1)`, a `[bracketed]` edit, or equivalent wording (`is`/`are`, `a`/`an`, `shall`/`must`, singular/plural).
   - *Material:* words added, omitted or changed. A material difference that touches a modal, negation, quantifier or number (`shall`, `may`, `not`, `only`, `all`, `sole`…) is **high** severity.
   - *Unquoted passages* do not promise exact wording, so ordinary paraphrase is labeled `paraphrased` and not flagged. They are flagged only for words appended where a source clause ends (`;` `.`), or for a swapped or dropped modal, negation or quantifier.

Nothing in the code looks for the benchmark's planted phrase (`under all circumstances`). The tests use different appended phrases.

### Output statuses

| Status | Flagged | Meaning |
|---|:-:|---|
| `verified` | | Word-for-word match |
| `minor_differences` | | Only immaterial differences |
| `paraphrased` | | Unquoted text reworded without changing the rule |
| `material_difference` | ✔ | Words added, omitted or changed. Each diff lists the quote text and the source text |
| `misattributed` | ✔ | Not in the cited source, but found verbatim in a different statute or rule |
| `not_found` | ✔ | The cited source partly overlaps the quote, but nothing in it is close enough |
| `found_elsewhere` | | The cited authority has no corpus text (a fabricated citation, which Stage 2 flags), but the quote exists in another source. The record names the real one |
| `source_unavailable` | | The cited authority has no source text |
| `no_source_match` | | The quoted words match no source. On this benchmark every one (78) is a party's quoted threat or testimony |

## Interpreting the false positives

21 of the 33 false positives are in **clean** documents. "Clean" means nothing was *planted*. It does not mean every passage matches its source (DATA_DICTIONARY §1). Many flags are real, unplanted differences by the drafting model, for example:

- Dropping **"only"** from AS 25.30.300: *"…has jurisdiction … **only** if this state is the home state…"* (5 documents)
- Omitting **"shall"** in AS 18.65.520, or **"of each parent"** inside a quoted AS 25.24.150(c)(6) factor
- `"each party shall … provide"` where Civil Rule 26.1(b) says `"a party shall"`

The rest are paraphrase that extends a statutory clause with case-specific words, such as *"…stay away from the residence **of the petitioner**"*. These are mostly medium severity and come from unquoted passages.

## Caveats

- **Tuned on the evaluation set.** The rules were refined by examining misses and false positives on this same benchmark, and no held-out split exists. Expect lower numbers on new documents, especially for the unquoted heuristics. Quoted-passage checking is the more conservative, more transferable signal.
- **Skewed alteration types.** 35 of the 40 altered quotes are the same appended phrase (`docs/benchmark-corpus-connections-and-caveats.md` §6). Recall on substitutions and omissions rests on just 5 examples.
- **Faithful quotes have no stored wording** in the answer key. Scoring is per extracted passage: a passage is positive if it contains an `altered_text`, and every other passage counts as a negative.
- **Case law** is checked only when the cited reporter cite is in `cases.jsonl`. The corpus-wide fallback covers statutes and rules only.

## Reproduce

From the repository root:

```bash
pip install -r requirements.txt
python scripts/check_quotes.py            # or --quoted-only, or list doc ids
python scripts/evaluate_quotes.py
python -m unittest tests.test_quote_fidelity
```

Outputs (generated locally, git-ignored): `data/processed/quote-fidelity.jsonl` holds every passage with status, diffs and matched source text. `data/processed/quote-evaluation.json` holds the metrics, misses and every false positive.
