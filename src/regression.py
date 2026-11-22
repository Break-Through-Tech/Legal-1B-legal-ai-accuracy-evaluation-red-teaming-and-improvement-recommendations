"""Fixture-driven regression checks for the unified detector."""
from __future__ import annotations

import io
import json
from pathlib import Path

import docx

from src.detect import Detector
from src.evaluation.scorecard import load_answer_key

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = REPO_ROOT / "tests" / "fixtures" / "regression_cases.json"


def load_evaluation(source: dict) -> dict:
    """Load the evaluator's pinned existence results and corresponding run metadata."""
    evaluation = json.loads(
        (REPO_ROOT / source["existence"]).read_text(encoding="utf-8")
    )
    run_log = json.loads(
        (REPO_ROOT / source["run_log"]).read_text(encoding="utf-8")
    )
    _, answer_key_meta = load_answer_key()
    if not answer_key_meta["answer_key_frozen"]:
        raise ValueError("Regression evaluation must use the frozen answer key")
    if evaluation.get("total_documents") != 200:
        raise ValueError("Existence evaluation must cover all 200 benchmark documents")
    if run_log.get("documents", {}).get("total") != 200:
        raise ValueError("Regression evaluation must cover all 200 benchmark documents")
    if run_log["documents"].get("failed") != 0:
        raise ValueError("Pinned detector run contains failed documents")
    if not isinstance(evaluation.get("missed_fabrications"), list):
        raise ValueError("Evaluation missed_fabrications must be a list")
    evaluation["run_log"] = run_log
    evaluation["answer_key"] = answer_key_meta
    return evaluation


def validate_missed_fabrications(fixture: dict, evaluation: dict) -> None:
    """Require one fixture case for every miss recorded by the pinned evaluation."""
    misses = evaluation["missed_fabrications"]
    required = {
        (miss["doc_id"], tuple(miss["identity"]))
        for miss in misses
    }
    covered = set()
    for case in fixture["cases"]:
        source = case.get("source_miss")
        if not source:
            continue
        key = (source["doc_id"], tuple(source["identity"]))
        miss = next(
            (
                item for item in misses
                if (item["doc_id"], tuple(item["identity"])) == key
            ),
            None,
        )
        if miss is None:
            raise ValueError(f"Regression case {case['id']} references an unknown fabrication miss")
        expected = case["expected"]
        values = expected["values"]
        if (
            miss["cite"] not in case["text"]
            or expected["selector"].get("stage") != "existence"
            or values.get("text") != miss["cite"]
            or values.get("status") != "Hallucinated"
            or values.get("flagged") is not True
        ):
            raise ValueError(
                f"Regression case {case['id']} does not reproduce and assert its fabrication miss"
            )
        covered.add(key)

    missing = sorted(required - covered)
    if missing:
        by_key = {
            (miss["doc_id"], tuple(miss["identity"])): miss["cite"]
            for miss in misses
        }
        formatted = ", ".join(f"{doc_id}: {by_key[(doc_id, identity)]}"
                              for doc_id, identity in missing)
        raise ValueError(f"Missing regression cases for fabrication misses: {formatted}")


def load_cases(path: Path = DEFAULT_CASES) -> dict:
    """Load the regression fixture and validate its top-level structure."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != 1:
        raise ValueError(f"Unsupported regression schema: {fixture.get('schema_version')}")
    if not isinstance(fixture.get("cases"), list) or not fixture["cases"]:
        raise ValueError("Regression fixture must contain at least one case")
    validate_missed_fabrications(fixture, load_evaluation(fixture["source_evaluation"]))
    return fixture


def _make_docx(text: str) -> bytes:
    document = docx.Document()
    for paragraph in text.splitlines():
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _matches(flag: dict, selector: dict) -> bool:
    return all(flag.get(field) == value for field, value in selector.items())


def run_case(detector: Detector, case: dict) -> list[str]:
    """Run one case and return human-readable expectation failures."""
    report = detector.check(
        _make_docx(case["text"]),
        filename=f"{case['id']}.docx",
        include_unquoted=False,
    )
    expected = case["expected"]
    matches = [flag for flag in report["flags"] if _matches(flag, expected["selector"])]
    failures = []

    if report["errors"]:
        failures.append(f"pipeline errors: {report['errors']}")
    if len(matches) != expected["match_count"]:
        failures.append(
            f"expected {expected['match_count']} matching flag(s), found {len(matches)}"
        )

    for index, flag in enumerate(matches, start=1):
        for field, value in expected["values"].items():
            if flag.get(field) != value:
                failures.append(
                    f"flag {index} field {field!r}: expected {value!r}, "
                    f"found {flag.get(field)!r}"
                )

    matched_ids = {id(flag) for flag in matches}
    unexpected = [
        flag for flag in report["flags"]
        if flag.get("flagged") and id(flag) not in matched_ids
    ]
    for flag in unexpected:
        failures.append(
            "unexpected flagged result: "
            f"{flag.get('stage')} {flag.get('status')} {flag.get('text')!r}"
        )
    return failures


def run_regression(path: Path = DEFAULT_CASES) -> list[dict]:
    """Run every fixture case and return its pass/fail details."""
    fixture = load_cases(path)
    detector = Detector()
    return [
        {"id": case["id"], "category": case["category"], "failures": run_case(detector, case)}
        for case in fixture["cases"]
    ]
