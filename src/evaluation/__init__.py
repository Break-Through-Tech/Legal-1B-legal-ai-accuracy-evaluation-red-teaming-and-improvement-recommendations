"""Accuracy evaluation of the hallucination detector against the frozen benchmark.

Every function is pure: answer-key rows and detector reports in, dict out.

    from src.evaluation import scorecard
    card = scorecard(answer_key, reports)

Modules: existence, quotes, extraction (moved from scripts/evaluate_*.py),
risk (document-level), runtime, metrics (shared), adapters (report -> rows),
scorecard (aggregate, markdown, before/after compare).
"""
from src.evaluation.scorecard import compare, render_markdown, scorecard

__all__ = ["compare", "render_markdown", "scorecard"]
