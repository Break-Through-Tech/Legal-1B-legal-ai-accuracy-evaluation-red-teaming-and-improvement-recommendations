# Red-team and failure analysis

This report documents targeted probes against the unified detector. The probes
are executable regression cases in
[`tests/test_red_team.py`](../tests/test_red_team.py). They use small DOCX
documents so each probe isolates one citation or passage behavior.

## What was tested

| Failure type | Probe | Current result | Finding |
|---|---|---|---|
| `fabricated_statute` | `AS 25.24.999` | Caught as `Hallucinated` | Base-section lookup catches a missing statute. |
| `fabricated_rule` | `Civil Rule 913(b)` | Caught as `Hallucinated` | Rule numbers are checked within the civil-rule namespace. |
| `wrong_reporter` | Real case name with altered reporter page | Caught as `Hallucinated` | Reporter citation matching prevents a real party name from masking a fabricated reporter cite. |
| `wrong_case_name` | Wrong name with a real reporter citation | Caught as `Wrong Case Name` | The detector performs a second case-name consistency check after reporter lookup. |
| `altered_quote` | `shall` changed to `may` | Caught as high-severity `material_difference` | Meaning-changing modal substitutions are surfaced. |
| `fake_subsection` | `AS 25.20.060(a)(999)` | **Missed**; reported `Valid/Verified` | Statute existence currently resolves at the base-section level, not the cited subsection. |
| `short_form_citation` | `Id.` | **Missed**; no citation flag | Short-form citations are not currently extracted. |
| `out_of_scope_real_law` | `AS 11.56.807` | Not flagged; reported as `Mismatched Context/Format` | The detector avoids calling a known real, out-of-corpus statute fabricated, but does not provide a general unknown-authority verdict. |
| `unquoted_copied_text` | Altered copied statutory passage without quotation marks | Flagged | The broader quote mode catches copied text, but this can create false alarms in otherwise clean documents. |

## Interpretation

The probes separate three different outcomes:

1. **Correct detection**: the detector flags a known fabricated or altered item.
2. **Known limitation**: the detector misses an unsupported citation form or
   does not verify a detail such as a statute subsection.
3. **Policy ambiguity**: the detector can identify that a citation is outside
   the corpus, but that does not establish that the authority is fake.

The most important current miss is the fake-subsection case. The verifier
matches statutes by their base section, so a real section can make an invented
subsection appear valid. Improving this requires source records that identify
valid subsections and a decision about whether subsection-level errors should be
scored as fabricated authorities or as a separate error type.

The short-form citation miss is primarily an extraction limitation. Supporting
`Id.` or `supra` requires citation context: the detector must determine which
earlier authority the short form refers to. Treating every `Id.` as a new
citation would be incorrect.

The unquoted-passage result is a precision tradeoff. Including copied text
improves recall for altered legal language that is not placed inside quotation
marks, but it also flags legitimate drafting differences and unlabeled passages.
The safer product behavior is to distinguish high-severity warnings from items
that require human review.

## Reproduce the probes

From the repository root:

```bash
python -m unittest discover -s tests -p 'test_red_team.py'
```

The tests are intentionally small and deterministic. They do not modify the
benchmark or answer key. They should remain as regression cases when the
extractor, verifier, or quote checker changes.

## Recommended next work

1. Add subsection-aware statute records and tests for valid and invalid
   subsections.
2. Add an explicit `unknown` or `unverifiable` citation state for authorities
   absent from the closed corpus.
3. Add context-aware support for `Id.` and `supra`.
4. Evaluate quoted and unquoted passages separately in product-facing metrics.
5. Add held-out red-team documents with case-law quotations, repealed statutes,
   deep subsections, and realistic paraphrases.
