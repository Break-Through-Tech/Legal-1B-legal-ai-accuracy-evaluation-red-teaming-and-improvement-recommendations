"""Shared metric helpers: precision/recall/F1, ROC-AUC and bootstrap confidence intervals."""
from __future__ import annotations

import random
from collections import Counter
from typing import Callable, Iterable, Sequence


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def prf(counts) -> dict:
    """Counts {tp, fp, fn, tn} -> counts plus precision, recall, f1, accuracy (None when undefined)."""
    c = {k: int(counts.get(k, 0)) for k in ("tp", "fp", "fn", "tn")}
    return {**c,
            "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
            "recall": _ratio(c["tp"], c["tp"] + c["fn"]),
            "f1": _ratio(2 * c["tp"], 2 * c["tp"] + c["fp"] + c["fn"]),
            "accuracy": _ratio(c["tp"] + c["tn"], sum(c.values()))}


def add_counts(rows: Iterable[dict]) -> Counter:
    total = Counter()
    for row in rows:
        for k in ("tp", "fp", "fn", "tn"):
            total[k] += row.get(k, 0) or 0
    return total


def roc_auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Probability a random positive outscores a random negative (ties count half)."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def bootstrap_ci(units: Sequence, statistic: Callable[[list], float | None],
                 n: int = 1000, seed: int = 0, level: float = 0.95) -> list[float] | None:
    """Percentile CI of `statistic` over resamples of `units` (documents) with replacement.

    Resampling whole documents keeps the correlation between citations or
    quotes in one document, which a per-item bootstrap would ignore.
    """
    if not units:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        sample = [units[rng.randrange(len(units))] for _ in units]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    lo = values[int((1 - level) / 2 * (len(values) - 1))]
    hi = values[int((1 + level) / 2 * (len(values) - 1))]
    return [lo, hi]


def counts_statistic(name: str) -> Callable[[list[dict]], float | None]:
    """Statistic for bootstrap_ci over per-document count dicts, e.g. counts_statistic('recall')."""
    return lambda sample: prf(add_counts(sample))[name]
