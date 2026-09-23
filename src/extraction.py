"""Text extraction for benchmark .docx documents.

See plans/task-4-clean-standardize-documents.md for the reasoning behind this module's
(deliberately narrow) scope: pull clean plain text out of a document, nothing more.
"""
import re

import docx


def extract_document_text(docx_path) -> str:
    """Read a benchmark .docx and return clean, whitespace-normalized body text.

    - Reads paragraph.text (footnotes/endnotes/comments are empty in every benchmark
      document, so they are not read).
    - Drops blank/whitespace-only spacer paragraphs.
    - Collapses repeated spaces/tabs within a line.
    """
    doc = docx.Document(docx_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs]
    paragraphs = [p for p in paragraphs if p]
    text = "\n".join(paragraphs)
    text = re.sub(r"[ \t]+", " ", text)
    return text
