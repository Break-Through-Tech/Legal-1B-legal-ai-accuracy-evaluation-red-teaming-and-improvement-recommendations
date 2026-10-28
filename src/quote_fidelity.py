"""Quote fidelity checker (Stage 3).

Finds passages a document takes from a legal source, locates the source text
in the corpus, and flags material differences. Two kinds of passage:

  quoted    — text inside quotation marks (extract_quotes)
  unquoted  — long verbatim runs copied from a cited source without quotation
              marks, e.g. a statute's factor list pasted into the argument
              (find_borrowed_passages). A quarter of the benchmark's altered
              quotes are of this kind.

Pipeline: extract passage -> attribute it to nearby citations -> look up their
corpus source text (QuoteSourceIndex) -> align (align) -> classify each
word-level difference as material or immaterial (classify_diffs).

The comparison is a generic word diff against the source. It does not search
for any particular planted phrase, so insertions, deletions and substitutions
are all caught the same way.
"""
import difflib
import re
from collections import Counter, defaultdict

from src.citation_extractor import extract_citations
from src.verifier import (
    CorpusIndex,
    canonical_citation,
    corpus_source_text,
    load_corpus,
    matching_corpus_records,
)

# Quotes shorter than this are defined terms ("Father", "Petitioner") or
# fragments too short to locate reliably.
MIN_QUOTE_WORDS = 4
# Best-window similarity at or above this means the quote came from that source.
MATCH_THRESHOLD = 0.75
# Between this and MATCH_THRESHOLD the quote overlaps the cited source but is
# heavily changed (flagged not_found). Below it the quoted words are unrelated
# to the source, which in these filings means testimony, not law.
PARTIAL_THRESHOLD = 0.4
# An unquoted passage must share this many consecutive words with its source.
MIN_BORROWED_WORDS = 7
# Words appended to a borrowed passage before the document's clause ends.
MAX_TRAILING_WORDS = 4
# List glue a paraphrase adds or drops freely.
_GLUE = {"and", "or", "that", "such", "the", "a", "an", "of"}

# Words whose change flips legal meaning; any diff touching them is high severity.
HIGH_SEVERITY_WORDS = {
    "shall", "may", "must", "will", "should", "not", "no", "never", "only",
    "all", "any", "each", "every", "none", "except", "unless", "without",
    "and", "or", "nor", "primary", "sole", "joint", "shared", "always",
    "mandatory", "discretionary", "required", "prohibited",
}
# Single-word swaps that do not change meaning. "shall"/"must" are both mandatory.
_EQUIVALENTS = [{"is", "are", "was", "were", "be", "been"}, {"has", "have", "had"},
                {"a", "an"}, {"this", "these"}, {"that", "those"}, {"shall", "must"}]

_QUOTE_CHARS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})
_TOKEN = re.compile(
    r"\[[^\]]*\]"                      # [bracketed alteration]
    r"|\.(?:\s?\.){2}|…"               # ellipsis, spaced or not
    r"|\d+(?:\.\d+)+"                  # dotted section numbers: 25.24.160
    r"|[A-Za-z0-9]+(?:['\-][A-Za-z]+)*(?:(?<=s)'(?![A-Za-z]))?"  # non-custodial, parent's, parents'
    r"|[^\sA-Za-z0-9]"                 # single punctuation
)
_BOUNDARY = {";", ".", ":", "!", "?"}
# Where a source clause ends. A colon is excluded: "minus:" introduces a list,
# and a document's words there summarize the list rather than extend the clause.
_CLAUSE_END = {";", ".", "!", "?"}


# --------------------------------------------------------------------------- #
# Normalization and tokenization
# --------------------------------------------------------------------------- #

def normalize_source(text: str) -> str:
    """Undo PDF line wrapping in corpus text: re-join hyphenated breaks, collapse whitespace."""
    text = text.translate(_QUOTE_CHARS)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1-\2", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    """Split into word, punctuation, ellipsis and [bracketed alteration] tokens."""
    return _TOKEN.findall(text.translate(_QUOTE_CHARS))


def _tokenize_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(text.translate(_QUOTE_CHARS))]


def _is_word(token: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9]", token))


def _is_ellipsis(token: str) -> bool:
    return token == "…" or token.startswith(".") and len(token) > 1


def _key(token: str) -> str:
    """Comparison key: case-folded, hyphens dropped (non-custodial == noncustodial).

    A standalone dash is a range ("AS 18.66.100 - 18.66.180"), which documents
    often spell out as "through".
    """
    if token == "-":
        return "through"
    if _is_ellipsis(token):
        return "..."
    return token.lower().replace("-", "")


def _detok(tokens: list[str]) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"\)\s+\(", ")(", text)
    return re.sub(r"([(\[])\s+", r"\1", text)


# --------------------------------------------------------------------------- #
# Corpus source text
# --------------------------------------------------------------------------- #

class _Source:
    """One searchable corpus passage."""

    def __init__(self, source_id: str, citation: str, text: str):
        self.id = source_id
        self.citation = citation
        self.text = normalize_source(text)
        self.tokens = tokenize(self.text)
        self.keys = [_key(t) for t in self.tokens]
        self.word_idx = [i for i, t in enumerate(self.tokens) if _is_word(t)]
        self._trigrams = None

    def trigrams(self) -> dict:
        """Word-trigram -> token positions of its first word."""
        if self._trigrams is None:
            self._trigrams = defaultdict(list)
            w = self.word_idx
            for n in range(len(w) - 2):
                self._trigrams[(self.keys[w[n]], self.keys[w[n + 1]], self.keys[w[n + 2]])].append(n)
        return self._trigrams


class QuoteSourceIndex:
    """Corpus source text for extracted citations.

    Citations resolve to corpus records through src/verifier.py, so a quote is
    checked against exactly the records the existence check matched (rule
    commentary excluded; a cited subrule narrows to that subrule's record).
    Records are tokenized lazily, so opinions are only tokenized when cited.
    """

    def __init__(self, corpus: CorpusIndex | None = None):
        self.corpus = corpus if corpus is not None else load_corpus()
        self._sources: dict[str, _Source | None] = {}
        self.global_pool = [
            source
            for name in ("statutes", "civil_rules", "evidence_rules")
            for records in self.corpus[name].values()
            for record in records
            if (source := self._source(record))
        ]
        self._global_trigrams = None

    def _source(self, record: dict) -> _Source | None:
        if record["id"] not in self._sources:
            text = corpus_source_text(record)
            self._sources[record["id"]] = (
                _Source(record["id"], canonical_citation(record), text) if text else None)
        return self._sources[record["id"]]

    def sources_for(self, citation: dict) -> list[_Source]:
        """Source passages for one extracted citation; empty if none has text."""
        return [source for record in matching_corpus_records(citation, self.corpus)
                if (source := self._source(record))]

    def global_candidates(self, keys: list[str], limit: int = 5) -> list[_Source]:
        """Statute/rule passages sharing the most word trigrams with `keys`."""
        if self._global_trigrams is None:
            self._global_trigrams = defaultdict(set)
            for n, source in enumerate(self.global_pool):
                for gram in source.trigrams():
                    self._global_trigrams[gram].add(n)
        words = [k for k in keys if re.match(r"[a-z0-9]", k)]
        votes = Counter()
        for i in range(len(words) - 2):
            for n in self._global_trigrams.get(tuple(words[i:i + 3]), ()):
                votes[n] += 1
        return [self.global_pool[n] for n, _ in votes.most_common(limit)]


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #

def _score(q_tokens: list[str], s_len: int, opcodes) -> float:
    """difflib ratio that does not penalize source text an ellipsis stands in for."""
    matched = skipped = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            matched += i2 - i1
        elif all(_is_ellipsis(t) or not _is_word(t) for t in q_tokens[i1:i2]) and any(
                _is_ellipsis(t) for t in q_tokens[i1:i2]):
            skipped += (j2 - j1) + (i2 - i1)
    total = len(q_tokens) + s_len - skipped
    return 2 * matched / total if total else 0.0


def align(quote_tokens: list[str], source: _Source) -> dict | None:
    """Find the window of `source` that best matches the quote.

    Trigram hits vote for where the quote starts in the source; each top
    candidate window is diffed with difflib on comparison keys. Returns the
    best {score, source, s_lo, s_hi, opcodes}, or None when nothing matches.
    """
    q_keys = [_key(t) for t in quote_tokens]
    q_words = [i for i, t in enumerate(quote_tokens) if _is_word(t)]
    grams = source.trigrams()
    votes = Counter()
    for n in range(len(q_words) - 2):
        gram = (q_keys[q_words[n]], q_keys[q_words[n + 1]], q_keys[q_words[n + 2]])
        for w in grams.get(gram, ()):
            votes[source.word_idx[w] - q_words[n]] += 1
    if not votes:
        return None

    # An ellipsis can stand in for any amount of source text.
    slack = max(8, len(quote_tokens) // 2) + (400 if any(map(_is_ellipsis, quote_tokens)) else 0)
    best = None
    for start, _ in votes.most_common(5):
        lo = max(0, start - slack)
        hi = min(len(source.tokens), start + len(quote_tokens) + slack)
        matcher = difflib.SequenceMatcher(None, q_keys, source.keys[lo:hi], autojunk=False)
        blocks = [b for b in matcher.get_matching_blocks() if b.size]
        window_tokens = source.tokens[lo:hi]

        def detached(block, neighbor):
            """A short match separated from the main run by distance or a sentence end."""
            gap = window_tokens[min(block.b + block.size, neighbor.b + neighbor.size):max(block.b, neighbor.b)]
            return block.size < 3 and (len(gap) > 10 or any(t in _CLAUSE_END for t in gap))

        # Drop stray matches ("the", or "in" from the next sentence) at either edge.
        while len(blocks) > 1 and detached(blocks[0], blocks[1]):
            blocks.pop(0)
        while len(blocks) > 1 and detached(blocks[-1], blocks[-2]):
            blocks.pop()
        if not blocks:
            continue
        tight_lo, tight_hi = lo + blocks[0].b, lo + blocks[-1].b + blocks[-1].size
        # Unmatched quote tokens at either edge are either words the quote added
        # (keep the tight span) or edge words it changed (stretch the span over
        # the source words they replaced). Stretch when it costs less than one
        # token's worth of score and does not cross a sentence end, so a one-word
        # edge substitution ("may" for "shall") reads as a substitution.
        head, tail = blocks[0].a, len(q_keys) - blocks[-1].a - blocks[-1].size
        local = None
        for s_lo in (tight_lo, max(0, tight_lo - head)):
            for s_hi in (tight_hi, min(len(source.tokens), tight_hi + tail)):
                extension = source.tokens[s_lo:tight_lo] + source.tokens[tight_hi:s_hi]
                if any(t in _CLAUSE_END for t in extension):
                    continue
                m = difflib.SequenceMatcher(None, q_keys, source.keys[s_lo:s_hi], autojunk=False)
                opcodes = m.get_opcodes()
                score = _score(quote_tokens, s_hi - s_lo, opcodes)
                if local is None or score >= local["score"] - (1 / len(q_keys) if extension else 0):
                    local = {"score": score, "source": source, "s_lo": s_lo, "s_hi": s_hi,
                             "opcodes": opcodes, "matched": sum(b.size for b in m.get_matching_blocks())}
        if local and (best is None or local["score"] > best["score"]):
            best = local
    return best


def _best_alignment(tokens: list[str], sources) -> dict | None:
    best = None
    for source in sources:
        result = align(tokens, source)
        if result and (best is None or result["score"] > best["score"]):
            best = result
    return best


# --------------------------------------------------------------------------- #
# Diff classification
# --------------------------------------------------------------------------- #

def _is_enumerator(tokens: list[str]) -> bool:
    """'(1)', '(A)', '(c)(6)' — subsection labels a quote may silently drop."""
    return bool(tokens) and bool(re.fullmatch(r"(?:\(\w{1,4}\))+", "".join(tokens)))


def classify_diffs(quote_tokens: list[str], source_tokens: list[str], opcodes) -> list[dict]:
    """Turn difflib opcodes into labeled differences.

    Immaterial: punctuation, hyphenation, dropped subsection labels, an
    ellipsis standing in for omitted source words, a [bracketed] edit of one
    word, and equivalent wording (is/are, a/an, shall/must, singular/plural).
    Material: any other added, dropped or substituted word. Material
    differences touching a modal, negation, quantifier or number are high severity.
    """
    diffs = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        q_part, s_part = quote_tokens[i1:i2], source_tokens[j1:j2]
        q_words = [t for t in q_part if _is_word(t)]
        # Subsection labels ("(D)") in the source are structure, not wording.
        s_words = [t for t in tokenize(re.sub(r"\(\s*\w{1,4}\s*\)", " ", " ".join(s_part))) if _is_word(t)]
        brackets = [t for t in q_part if t.startswith("[")]
        ellipsis = any(map(_is_ellipsis, q_part))
        pair = {q_words[0].lower(), s_words[0].lower()} if len(q_words) == len(s_words) == 1 else None

        if not q_words and not s_words and not brackets:
            reason, material = "punctuation", False
        elif ellipsis and not q_words:
            reason, material = "ellipsis_omission", False
        elif not q_words and not brackets and _is_enumerator(s_part):
            reason, material = "subsection_label_omitted", False
        elif brackets and not q_words and len(s_words) <= 1:
            reason, material = "bracketed_alteration", False
        elif pair and (any(pair <= group for group in _EQUIVALENTS) or
                       re.fullmatch(r"(\w+?)(?:e?s)?", min(pair, key=len)) and
                       max(pair, key=len).rstrip("s").rstrip("e") == min(pair, key=len).rstrip("s").rstrip("e")):
            reason, material = "equivalent_wording", False
        elif q_words and not s_words:
            reason, material = "words_added", True
        elif s_words and not q_words:
            reason, material = "words_omitted", True
        else:
            reason, material = "words_changed", True

        touched = {w.lower() for w in q_words + s_words}
        high = material and bool(touched & HIGH_SEVERITY_WORDS or any(w[0].isdigit() for w in touched))
        diffs.append({
            "type": reason,
            "material": material,
            "severity": "high" if high else ("medium" if material else "low"),
            "quote_text": _detok(q_part),
            "source_text": _detok(s_part),
            # Words added where a source clause ends extend what the law says.
            "at_clause_end": j2 == len(source_tokens) or any(t in _CLAUSE_END for t in s_part)
                             or source_tokens[j2] in _CLAUSE_END,
        })
    return diffs


def _verdict(tokens: list[str], best: dict) -> dict:
    """Status, diffs and matched source text for an accepted alignment."""
    source = best["source"]
    source_tokens = source.tokens[best["s_lo"]:best["s_hi"]]
    diffs = classify_diffs(tokens, source_tokens, best["opcodes"])
    if any(d["material"] for d in diffs):
        status = "material_difference"
    elif diffs:
        status = "minor_differences"
    else:
        status = "verified"
    return {
        "status": status,
        "match_score": round(best["score"], 3),
        "matched_source": {"id": source.id, "citation": source.citation},
        "matched_text": _detok(source_tokens),
        "diffs": diffs,
    }


def _severity(diffs: list[dict]) -> str:
    return max((d["severity"] for d in diffs if d["material"]),
               key=["low", "medium", "high"].index, default="medium")


# --------------------------------------------------------------------------- #
# Quoted passages
# --------------------------------------------------------------------------- #

def _quote_spans(paragraph: str):
    """Yield (start, end) of text inside paired quotation marks.

    Curly quotes pair by direction; straight quotes pair in order of appearance.
    """
    for m in re.finditer(r"“([^“”]+)”", paragraph):
        yield m.start(1), m.end(1)
    positions = [m.start() for m in re.finditer(r'"', paragraph)]
    for open_pos, close_pos in zip(positions[0::2], positions[1::2]):
        yield open_pos + 1, close_pos


def _candidate_citations(citations: list[dict], start: int, end: int, paragraph: str):
    """Order the paragraph's citations by how likely the quote came from each.

    Preference: citations before the quote in the same sentence (closest
    first), then one right after it ("... 'quote.' AS 25.20.060(c)."), then the
    rest of the paragraph. A sentence often names several authorities
    ("Under AS 25.20.070, unless ... AS 25.24.150(g) ..., 'quote'"), so the
    checker tries each in turn instead of trusting the nearest one.
    """
    before = [c for c in citations if c["end"] <= start]
    after = [c for c in citations if c["start"] >= end]
    sentence_start = max(paragraph.rfind(". ", 0, start), 0)
    same_sentence = [c for c in reversed(before) if c["start"] >= sentence_start]
    trailing = [after[0]] if after and after[0]["start"] - end < 40 else []
    ordered = same_sentence + trailing + list(reversed(before)) + after
    unique = []
    for c in ordered:
        if c not in unique:
            unique.append(c)
    return unique, bool(same_sentence or trailing)


def extract_quotes(text: str) -> list[dict]:
    """Return quoted passages (>= MIN_QUOTE_WORDS words) with candidate citations.

    Citations from the previous cited paragraph are used only when the quote's
    own paragraph has none (attribution 'inherited').
    """
    quotes = []
    offset = 0
    previous_citations: list[dict] = []
    for paragraph in text.split("\n"):
        citations = extract_citations(paragraph)
        for start, end in sorted(set(_quote_spans(paragraph))):
            quote = paragraph[start:end].strip()
            if sum(_is_word(t) for t in tokenize(quote)) < MIN_QUOTE_WORDS:
                continue
            candidates, in_sentence = _candidate_citations(citations, start, end, paragraph)
            if candidates:
                attribution = "sentence" if in_sentence else "paragraph"
            elif previous_citations:
                candidates, attribution = list(reversed(previous_citations)), "inherited"
            else:
                attribution = "none"
            quotes.append({
                "kind": "quoted",
                "quote": quote,
                "start": offset + start,
                "end": offset + end,
                "context": paragraph[max(0, start - 120):min(len(paragraph), end + 60)],
                "cited_raw": candidates[0]["raw_text"] if candidates else None,
                "candidates": candidates,
                "attribution": attribution,
            })
        if citations:
            previous_citations = citations
        offset += len(paragraph) + 1
    return quotes


def check_quote(quote: dict, index: QuoteSourceIndex) -> dict:
    """Locate one quoted passage in the corpus and report its fidelity.

    status is one of:
      verified            — matches the source word for word
      minor_differences   — only immaterial differences (punctuation, ellipsis, ...)
      material_difference — words added, dropped or changed relative to the source
      misattributed       — not in the cited source, but found verbatim in another
                            statute or rule
      found_elsewhere     — the cited authority has no corpus text (likely a
                            fabricated citation, which Stage 2 flags) but the
                            quote exists in another statute or rule
      not_found           — the cited source partly overlaps the quote but no
                            passage is close enough: a heavily altered quote
      source_unavailable  — the cited authority has no source text in the corpus
      no_source_match     — the quoted words are unrelated to any source;
                            usually testimony or a party's own words
    Flagged statuses: material_difference, misattributed, not_found.
    """
    tokens = tokenize(quote["quote"])
    # Trailing punctuation inside the quote marks is the document's sentence, not the source's.
    while tokens and not _is_word(tokens[-1]) and not tokens[-1].startswith("[") and not _is_ellipsis(tokens[-1]):
        tokens.pop()
    n_words = sum(map(_is_word, tokens))

    def acceptable(result):
        # Short quotes match common phrases by chance; require most words to match.
        return result and result["score"] >= MATCH_THRESHOLD and result["matched"] >= min(n_words, max(4, n_words * 0.6))

    # Try each nearby citation in priority order; the first acceptable match
    # wins, otherwise keep the best partial match.
    best, cited, primary_has_text, any_text = None, None, None, False
    for citation in quote["candidates"]:
        sources = index.sources_for(citation)
        if primary_has_text is None:
            primary_has_text = bool(sources)
        any_text = any_text or bool(sources)
        result = _best_alignment(tokens, sources)
        if result and (best is None or result["score"] > best["score"]):
            best, cited = result, citation
        if acceptable(best):
            break

    record = {k: v for k, v in quote.items() if k != "candidates"}
    if acceptable(best):
        verdict = _verdict(tokens, best)
    else:
        # Not in any cited source: search every statute and rule.
        fallback = _best_alignment(tokens, index.global_candidates([_key(t) for t in tokens]))
        if acceptable(fallback):
            verdict = _verdict(tokens, fallback)
            if verdict["status"] != "material_difference" and quote["attribution"] != "inherited":
                verdict["status"] = "misattributed" if primary_has_text else "found_elsewhere"
            cited = None
        else:
            score = best["score"] if best else 0.0
            if quote["attribution"] == "sentence" and score >= PARTIAL_THRESHOLD:
                status = "not_found"
            elif quote["attribution"] == "sentence" and not any_text:
                status = "source_unavailable"
            else:
                status = "no_source_match"
            verdict = {"status": status, "match_score": round(score, 3) if best else None,
                       "matched_source": None, "matched_text": None, "diffs": []}

    flagged = verdict["status"] in ("material_difference", "misattributed", "not_found")
    return {
        **record,
        "matched_citation": cited["raw_text"] if cited else None,
        **verdict,
        "flagged": flagged,
        "severity": _severity(verdict["diffs"]) if flagged else None,
    }


# --------------------------------------------------------------------------- #
# Unquoted (borrowed) passages
# --------------------------------------------------------------------------- #

def _exact_runs(p_keys: list[str], p_words: list[int], source: _Source, min_words: int):
    """Maximal word-for-word runs (>= min_words words) shared by paragraph and source.

    Runs are over word tokens only, so punctuation differences do not break
    them. Yields (p_word_start, p_word_end, s_word_start, s_word_end).
    """
    grams = source.trigrams()
    s_keys = [source.keys[i] for i in source.word_idx]
    q = [p_keys[i] for i in p_words]
    covered = set()
    for n in range(len(q) - 2):
        for s in grams.get((q[n], q[n + 1], q[n + 2]), ()):
            if (n, s) in covered or (n > 0 and s > 0 and q[n - 1] == s_keys[s - 1]):
                continue  # Not the start of a maximal run.
            length = 0
            while n + length < len(q) and s + length < len(s_keys) and q[n + length] == s_keys[s + length]:
                covered.add((n + length, s + length))
                length += 1
            if length >= min_words:
                yield n, n + length, s, s + length


def _merge_runs(runs: list[tuple], max_gap: int = 4) -> list[list[tuple]]:
    """Chain runs separated by a few changed words into one borrowed passage."""
    runs = sorted(runs)
    chains: list[list[tuple]] = []
    for run in runs:
        if chains:
            last = chains[-1][-1]
            if 0 <= run[0] - last[1] <= max_gap and 0 <= run[2] - last[3] <= max_gap + 2:
                chains[-1].append(run)
                continue
            if run[0] < last[1]:
                continue  # Overlaps a passage already taken from another position.
        chains.append([run])
    return chains


def _changes_the_law(diff: dict) -> bool:
    """Whether a difference in unquoted borrowed text alters the rule it states.

    Appended words count when they extend a source clause past its end and
    read as law: not a citation, not a party or proper name, not list glue,
    and not the start of the document's next list item ("..., and orders").
    Substitutions and omissions count when they swap or drop a modal,
    negation or quantifier.
    """
    added = [t for t in tokenize(diff["quote_text"]) if _is_word(t)]
    removed = [t for t in tokenize(diff["source_text"]) if _is_word(t)]
    if diff["type"] == "words_added":
        return (diff["at_clause_end"]
                and not extract_citations(diff["quote_text"])
                and not re.search(r"\(Alaska|\d", diff["quote_text"])
                and not any(w[0].isupper() for w in added)
                and not all(w.lower() in _GLUE for w in added)
                and not (added and added[0].lower() in {"and", "or", "but", "as"}))
    if len(added) > 2 or len(removed) > 2:
        return False
    changed = {w.lower() for w in added} ^ {w.lower() for w in removed}
    return bool(changed & (HIGH_SEVERITY_WORDS - {"and", "or"})) or {"and", "or"} <= changed


def find_borrowed_passages(text: str, index: QuoteSourceIndex, quoted: list[dict]) -> list[dict]:
    """Find verbatim runs from cited sources that appear without quotation marks.

    A run of >= MIN_BORROWED_WORDS identical words between a paragraph and a
    source cited in that paragraph (or the previous cited one) is borrowed
    text. Runs a few words apart merge into one passage, so a word changed in
    the middle shows up as a difference. If the source passage ends at a
    clause boundary (";", ".") but the document carries on for a few more
    words before its own boundary, those words are reported as added.
    """
    quoted_spans = [(q["start"], q["end"]) for q in quoted]
    passages = []
    offset = 0
    previous_citations: list[dict] = []
    for paragraph in text.split("\n"):
        citations = extract_citations(paragraph)
        spans = _tokenize_spans(paragraph)
        p_tokens = [t for t, _, _ in spans]
        p_keys = [_key(t) for t in p_tokens]
        p_words = [i for i, t in enumerate(p_tokens) if _is_word(t)]
        sources, seen = [], set()
        for citation in citations or previous_citations:
            for source in index.sources_for(citation):
                if source.id not in seen:
                    seen.add(source.id)
                    sources.append((citation, source))
        # Text copied from a statute or rule the paragraph does not cite (often
        # because the citation was fabricated) is found by a corpus-wide search.
        for source in index.global_candidates(p_keys, limit=3):
            if source.id not in seen:
                seen.add(source.id)
                sources.append((None, source))

        found = []
        for citation, source in sources:
            runs = list(_exact_runs(p_keys, p_words, source, MIN_BORROWED_WORDS))
            for chain in _merge_runs(runs):
                found.append((chain[0][0], chain[-1][1], chain, citation, source))
        # Longest passage wins where several sources share the same words.
        found.sort(key=lambda f: -(f[1] - f[0]))
        taken: list[tuple[int, int]] = []
        for pw_lo, pw_hi, chain, citation, source in found:
            if any(pw_lo < hi and lo < pw_hi for lo, hi in taken):
                continue
            t_lo, t_hi = p_words[pw_lo], p_words[pw_hi - 1] + 1
            char_lo, char_hi = offset + spans[t_lo][1], offset + spans[t_hi - 1][2]
            if any(char_lo < q_hi and q_lo < char_hi for q_lo, q_hi in quoted_spans):
                continue
            taken.append((pw_lo, pw_hi))
            s_lo, s_hi = source.word_idx[chain[0][2]], source.word_idx[chain[-1][3] - 1] + 1

            # Closing parentheses end "(a)(2)" on both sides.
            while s_hi < len(source.tokens) and source.tokens[s_hi] == ")":
                s_hi += 1
            while t_hi < len(p_tokens) and p_tokens[t_hi] == ")":
                t_hi += 1
            # Trailing words: the source clause ends here, the document's carries on.
            # After a hard boundary (";", ".") any short continuation counts; after
            # a comma only one that itself ends at a hard boundary. (A source that
            # runs straight into a list, "minus (A) ...", has not ended: the
            # document's words there summarize the list.)
            s_next = source.tokens[s_hi] if s_hi < len(source.tokens) else "."
            if s_next in _CLAUSE_END | {","}:
                k = t_hi
                while k < len(p_tokens) and p_tokens[k] not in _BOUNDARY | {","}:
                    k += 1
                words = sum(_is_word(t) for t in p_tokens[t_hi:k])
                ends_hard = k < len(p_tokens) and p_tokens[k] in _BOUNDARY
                if 0 < words <= MAX_TRAILING_WORDS and (ends_hard or s_next != "," and k < len(p_tokens)):
                    t_hi = k
            char_hi = offset + spans[t_hi - 1][2]

            q_tokens = p_tokens[t_lo:t_hi]
            opcodes = difflib.SequenceMatcher(
                None, [_key(t) for t in q_tokens], source.keys[s_lo:s_hi], autojunk=False).get_opcodes()
            best = {"score": _score(q_tokens, s_hi - s_lo, opcodes), "source": source,
                    "s_lo": s_lo, "s_hi": s_hi, "opcodes": opcodes}
            verdict = _verdict(q_tokens, best)
            # Unquoted text does not promise exact wording, so ordinary
            # paraphrase is not a misquotation. Flag only edits that change
            # what the law says: words appended where a source clause ends,
            # or a swapped or dropped modal, negation or quantifier.
            for d in verdict["diffs"]:
                d["material"] = d["material"] and _changes_the_law(d)
                if not d["material"] and d["severity"] != "low":
                    d["severity"] = "low"
            if verdict["status"] != "verified":
                verdict["status"] = ("material_difference" if any(d["material"] for d in verdict["diffs"])
                                     else "paraphrased")
            flagged = verdict["status"] == "material_difference"
            passages.append({
                "kind": "unquoted",
                "quote": paragraph[char_lo - offset:char_hi - offset],
                "start": char_lo,
                "end": char_hi,
                "context": paragraph[max(0, char_lo - offset - 120):char_hi - offset + 60],
                "cited_raw": citation["raw_text"] if citation else None,
                "attribution": ("uncited" if citation is None else "paragraph" if citations else "inherited"),
                "matched_citation": citation["raw_text"] if citation else None,
                **verdict,
                "flagged": flagged,
                "severity": _severity(verdict["diffs"]) if flagged else None,
            })
        if citations:
            previous_citations = citations
        offset += len(paragraph) + 1
    return passages


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def check_document(text: str, index: QuoteSourceIndex, include_unquoted: bool = True) -> list[dict]:
    """Extract and check every quoted (and optionally unquoted) passage, in document order."""
    quoted = extract_quotes(text)
    results = [check_quote(q, index) for q in quoted]
    if include_unquoted:
        results += find_borrowed_passages(text, index, quoted)
    return sorted(results, key=lambda r: r["start"])
