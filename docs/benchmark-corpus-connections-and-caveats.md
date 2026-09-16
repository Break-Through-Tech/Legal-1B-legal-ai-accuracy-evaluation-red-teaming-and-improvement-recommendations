# Benchmark and Corpus: Connections and Evaluation Caveats

This document explains how the benchmark and reference corpus work together, and which data issues could make a correct detector appear wrong. It brings together findings from the team’s [benchmark exploration](https://github.com/Break-Through-Tech/Legal-1B-legal-ai-accuracy-evaluation-red-teaming-and-improvement-recommendations/blob/c4da65a/docs/benchmark-exploration.md) by Brant Bueno and [corpus exploration](https://github.com/Break-Through-Tech/Legal-1B-legal-ai-accuracy-evaluation-red-teaming-and-improvement-recommendations/blob/b1c9516/docs/citation-corpus-exploration.md) by Aadhya Pandillapally. This is a synthesis of those reviews, not a detector performance report.

## What we have

| Dataset | Contents | Purpose |
|---|---|---|
| **Benchmark** | 200 AI-generated legal documents and an answer key, with 3,490 citation labels and 163 quote labels. | Provides the documents our detector checks and the expected results. |
| **Corpus** | 2,212 reference records covering statutes, court cases, civil rules, and evidence rules/commentary. | Provides the sources our detector uses to verify citations and quotations. |

Think of the **benchmark as exam papers**, the **corpus as the reference library**, and the **answer key as the grading guide**.

## How they connect

The detector reads a benchmark document, finds its citations, and looks them up in the corpus. For quoted passages, it compares the document's wording with the source text. We then compare its findings with the answer key to measure how well it worked.

For example, a document may say `Civil Rule 90.3`, while the corpus uses `Alaska R. Civ. P. 90.3`. The detector needs to recognize the equivalent formatting before deciding whether it found the source.

## What needs attention

**1. Different wording can refer to the same source.** A document may use `Civil Rule 90.3`, while the corpus uses `Alaska R. Civ. P. 90.3`. Matching only identical text would miss this connection. However, meaningful details must stay: `(a)` and `(b)` identify different subsections, civil rules and evidence rules are different rule families, and a case's reporter volume and page help identify the specific decision. Simplifying formatting should not erase these differences.

**2. A reference record does not always contain the words we need.** The corpus review found 70 statute records without source text, marked repealed or renumbered in the dataset. Finding such a record confirms that it is listed, but does not provide text for checking a quotation or establish that it is current law. Record membership, text availability, and the stored status are separate pieces of information.

**3. “Deliberately changed” and “labeled nonexistent” are different counts.** The benchmark has 278 deliberately changed citations, but 310 citations labeled `exists: false`. The additional 32 were not marked as injected errors. This difference alone does not prove a mistake; it means the injection label cannot replace the existence label when evaluating results. Similarly, “clean” means no errors were deliberately planted, not that every citation has a true existence label: 17 clean documents contain at least one false existence label.

**4. Some labels conflict with the reference collection.** For example, `AS 25.24.900` appears among the injected citations labeled fabricated, but it also appears in the corpus. A detector could find that record and still disagree with the answer key. Conversely, the benchmark review found citations labeled real whose rule numbers are missing from the corpus. These cases need review: “not found in this collection” is not proof that a source does not exist. Preserve the original data and document disagreements separately.

**5. We need to compare the right items.** A citation may appear several times in one document, while the answer key lists its citation string once. Counting every repeated mention as a separate prediction against that one label can distort results. Quote matching also needs care: the 123 faithful quote labels identify a source but do not store the quoted wording, so the relevant passage must first be located in the document.

**6. Results describe this benchmark's coverage.** These are Alaska family-law documents with selected planted error types. Of the 40 altered quotes, 35 were changed by appending the same phrase, `under all circumstances`. Catching that phrase would not demonstrate an ability to catch every kind of inaccurate quotation. Report what was tested and distinguish detector mistakes from missing sources, uncertain passage matches, and label disagreements.

## Two different checks using the same data

| Check | What the benchmark provides | What the corpus provides |
|---|---|---|
| **Citation existence** | The citation used in a document—for example, a statute number or case name and reporter. | Reference records to check whether that authority is present. |
| **Quote accuracy** | The words quoted in the document. | Source text to compare those words against, where available. |

A citation can match a corpus record while its quotation has been changed. That is why finding the source and checking the quoted words are separate tasks.

The datasets also help reveal each other's limitations: an answer-key citation labeled real may be missing from the corpus, or a citation labeled fabricated may match a corpus entry. These disagreements need review before we treat them as detector mistakes.
