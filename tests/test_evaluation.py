import json
import unittest
from pathlib import Path

from src.detect import Detector
from src.evaluation import adapters, compare, render_markdown, scorecard
from src.evaluation.metrics import bootstrap_ci, counts_statistic, prf, roc_auc
from src.evaluation.risk import evaluate_risk

ROOT = Path(__file__).resolve().parent.parent
DOC_IDS = ["doc-0001", "doc-0002", "doc-0004", "doc-0136"]


def risk_report(doc_id, score, level):
    return {"doc_id": doc_id, "risk": {"score": score, "level": level, "drivers": []}}


class MetricTests(unittest.TestCase):
    def test_prf_handles_empty_denominators(self):
        self.assertEqual(prf({"tn": 3}), {"tp": 0, "fp": 0, "fn": 0, "tn": 3, "precision": None,
                                          "recall": None, "f1": None, "accuracy": 1.0})
        m = prf({"tp": 3, "fp": 1, "fn": 1})
        self.assertEqual((m["precision"], m["recall"], m["f1"]), (0.75, 0.75, 0.75))

    def test_roc_auc_counts_ties_as_half(self):
        self.assertEqual(roc_auc([0.9, 0.1], [True, False]), 1.0)
        self.assertEqual(roc_auc([0.5, 0.5], [True, False]), 0.5)
        self.assertIsNone(roc_auc([0.5], [True]))

    def test_bootstrap_is_deterministic_and_brackets_the_value(self):
        docs = [{"tp": 1}, {"fn": 1}, {"tp": 2}, {"tp": 1, "fn": 1}]
        a = bootstrap_ci(docs, counts_statistic("recall"), n=200, seed=1)
        self.assertEqual(a, bootstrap_ci(docs, counts_statistic("recall"), n=200, seed=1))
        self.assertLessEqual(a[0], 4 / 6)
        self.assertGreaterEqual(a[1], 4 / 6)


class RiskEvaluationTests(unittest.TestCase):
    def test_known_confusion(self):
        key = [{"doc_id": "d1", "condition": "corrupt", "citations": [{"cite": "AS 1.1.1", "type": "statute",
                                                                        "exists": False}], "quotes": []},
               {"doc_id": "d2", "condition": "clean", "citations": [], "quotes": []},
               {"doc_id": "d3", "condition": "clean", "citations": [], "quotes": []}]
        reports = [risk_report("d1", 0.6, "high"), risk_report("d2", 0.3, "medium"), risk_report("d3", 0, "none")]
        r = evaluate_risk(key, reports)
        self.assertEqual({k: r["corrupt"]["operating_point"][k] for k in ("tp", "fp", "fn", "tn")},
                         {"tp": 1, "fp": 1, "fn": 0, "tn": 1})
        self.assertEqual(r["corrupt"]["auc"], 1.0)
        self.assertEqual([d["doc_id"] for d in r["corrupt"]["false_alarms"]], ["d2"])


class ScorecardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        detector = Detector()
        documents = ROOT / "data" / "benchmark" / "documents"
        cls.reports = [detector.check(documents / f"{d}.docx") for d in DOC_IDS]
        key = json.loads((ROOT / "data" / "benchmark" / "answer-key.json").read_text())
        cls.key = [d for d in key if d["doc_id"] in DOC_IDS]
        cls.card = scorecard(cls.key, cls.reports, bootstrap=50)

    def test_adapters_round_trip_quote_fields(self):
        rows = adapters.to_quote_rows(self.reports)
        flagged = sum(f["flagged"] for r in self.reports for f in r["flags"] if f["stage"] == "quote_fidelity")
        self.assertEqual(sum(q["flagged"] for r in rows for q in r["quotes"]), flagged)
        self.assertTrue(all({"cited_raw", "diffs", "matched_text"} <= set(q) for r in rows for q in r["quotes"]))

    def test_scorecard_is_serializable_with_headline_metrics(self):
        json.dumps(self.card)
        ids = {m["id"] for m in self.card["headline"]}
        self.assertLessEqual({"fabricated_citation_recall", "altered_quote_recall", "document_f1_corrupt",
                              "extraction_recall", "runtime_median_ms"}, ids)
        self.assertIn("## Headline", render_markdown(self.card))

    def test_compare_reports_deltas(self):
        worse = json.loads(json.dumps(self.card))
        for m in worse["headline"]:
            if m["id"] == "fabricated_citation_recall":
                m["value"] = m["value"] - 0.25
        diff = {r["id"]: r for r in compare(worse, self.card)["metrics"]}
        self.assertAlmostEqual(diff["fabricated_citation_recall"]["delta"], 0.25)


if __name__ == "__main__":
    unittest.main()
