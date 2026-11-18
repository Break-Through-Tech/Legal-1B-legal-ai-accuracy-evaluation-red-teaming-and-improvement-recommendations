import unittest

from src.evaluation.existence import evaluate_existence
from src.evaluation import adapters
from src.evaluation.unified import clean_false_alarms, evaluate_unified, match_document


def cite_flag(flag_id, citation, status="Hallucinated", flagged=True, exists="false"):
    return {"flag_id": flag_id, "stage": "existence", "item_type": "citation", "citation_type": citation["type"],
            "text": citation["raw_text"], "start": 0, "end": 1, "context": "", "status": status,
            "flagged": flagged, "severity": "high" if flagged else None, "message": "", "reason": "",
            "evidence": {"exists": exists, "corpus_ids": [], "matched_citations": [], "mismatches": [],
                         "authority": "", "citation": citation}}


def quote_flag(flag_id, text, flagged=True, kind="quoted", status="material_difference"):
    return {"flag_id": flag_id, "stage": "quote_fidelity", "item_type": kind, "text": text, "start": 0, "end": 1,
            "context": "", "status": status if flagged else "verified", "flagged": flagged,
            "severity": "high" if flagged else None, "message": "", "reason": "", "evidence": {}}


def report(doc_id, flags, score=0.0, level="none"):
    return {"doc_id": doc_id, "flags": flags, "risk": {"score": score, "level": level, "drivers": []}}


STATUTE = {"type": "statute", "raw_text": "AS 25.24.999", "section": "25.24.999", "subsection": ""}
REAL_RULE = {"type": "rule", "raw_text": "Civil Rule 90.3", "number": "90.3", "rule_family": "civil",
             "subsection": ""}
UNKNOWN_STATUTE = {"type": "statute", "raw_text": "AS 25.99.999", "section": "25.99.999", "subsection": ""}
FAKE_CASE = {"type": "case", "raw_text": "Made v. Up, 449 P.3d 700 (Alaska 2019)", "case_name": "Made v. Up",
             "volume": "449", "reporter": "P.3d", "page": "700", "reporter_cite": "449 P.3d 700", "year": 2019}

KEY = [
    {"doc_id": "d1", "condition": "corrupt",
     "citations": [{"cite": "AS 25.24.999", "type": "statute", "exists": False, "injected": "fabricated_statute"},
                   {"cite": "Civil Rule 90.3", "type": "rule", "exists": True, "injected": False},
                   {"cite": "Made v. Up, 449 P.3d 700", "type": "case", "exists": False,
                    "injected": "fabricated_case"}],
     "quotes": [{"quote_status": "altered", "altered_text": "shall not award custody", "planted": True},
                {"quote_status": "altered", "altered_text": "in the best interests", "planted": False}]},
    {"doc_id": "d2", "condition": "clean", "citations": [], "quotes": []},
    {"doc_id": "d3", "condition": "clean", "citations": [],
     "quotes": [{"quote_status": "altered", "altered_text": "natural change here", "planted": False}]},
    {"doc_id": "d4", "condition": "clean", "citations": [], "quotes": []},
]
REPORTS = [
    report("d1", [
        cite_flag("c1", STATUTE), cite_flag("c2", STATUTE),                       # repeated mention: one TP
        cite_flag("c3", REAL_RULE),                                               # labeled real: FP
        cite_flag("c4", FAKE_CASE, status="Wrong Case Name", exists="true"),      # caught by name check: TP
        cite_flag("c5", UNKNOWN_STATUTE),                                         # not in key: FP
        cite_flag("c6", FAKE_CASE, status="Wrong Year", exists="true"),           # unscored
        quote_flag("q1", "the court shall not award custody to"),                 # planted: TP
        quote_flag("q2", "in the best interests of the child", flagged=False),    # natural: FN
        quote_flag("q3", "some unlabeled copied text", kind="unquoted"),          # FP
    ], score=0.99, level="high"),
    report("d2", [quote_flag("q1", "another unlabeled passage", kind="unquoted")], score=0.6, level="high"),
    report("d3", [quote_flag("q1", "a natural change here indeed")], score=0.3, level="medium"),
    report("d4", [], score=0.0, level="none"),
]


class MatchingRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = evaluate_unified(KEY, REPORTS)
        cls.d1 = match_document(KEY[0], REPORTS[0])

    def test_citation_targets_are_unique_authorities(self):
        cites = [t for t in self.d1["targets"] if t["class"] == "fabricated_citation"]
        self.assertEqual(len(cites), 2)
        statute = next(t for t in cites if t["error_type"] == "fabricated_statute")
        self.assertTrue(statute["caught"])
        self.assertEqual(statute["flag_ids"], ["c1", "c2"])

    def test_wrong_case_name_flag_catches_fabricated_case(self):
        case = next(t for t in self.d1["targets"] if t["error_type"] == "fabricated_case")
        self.assertTrue(case["caught"])
        # The old exists-based scoring cannot see this catch: the reporter cite exists.
        old = evaluate_existence(KEY, adapters.to_verification_rows(REPORTS), expected_documents=len(KEY))
        self.assertEqual(old["metrics"]["end_to_end"]["fabrication:fabricated_case"]["fn"], 1)

    def test_false_positives_and_unscored_flags(self):
        reasons = sorted((fp["class"], fp["reason"]) for fp in self.d1["false_positives"])
        self.assertEqual(reasons, [("altered_quote", "no_labeled_alteration"),
                                   ("fabricated_citation", "labeled_real"),
                                   ("fabricated_citation", "not_in_answer_key")])
        self.assertEqual([f["status"] for f in self.d1["unscored_flags"]], ["Wrong Year"])

    def test_metrics_overall_and_per_class(self):
        m = self.result["metrics"]
        self.assertEqual({k: m["fabricated_citation"][k] for k in ("tp", "fp", "fn")}, {"tp": 2, "fp": 2, "fn": 0})
        # Quotes: d1 planted TP, d1 natural FN, d1 + d2 unlabeled FPs, d3 natural TP.
        self.assertEqual({k: m["altered_quote"][k] for k in ("tp", "fp", "fn")}, {"tp": 2, "fp": 2, "fn": 1})
        self.assertEqual({k: m["overall"][k] for k in ("tp", "fp", "fn")}, {"tp": 4, "fp": 4, "fn": 1})
        self.assertAlmostEqual(m["overall"]["recall"], 0.8)
        self.assertNotIn("accuracy", m["overall"])

    def test_recall_by_error_type(self):
        rows = {r["error_type"]: (r["tp"], r["n"]) for r in self.result["by_error_type"]}
        self.assertEqual(rows, {"fabricated_case": (1, 1), "fabricated_statute": (1, 1),
                                "planted_altered_quote": (1, 1), "natural_misquote": (1, 2)})

    def test_clean_false_alarm_rate(self):
        alarms = self.result["clean_false_alarms"]
        # d2 and d3 are flagged clean documents; d3 holds a natural misquote, so it is not error-free.
        self.assertEqual(alarms["clean"]["false_alarm_documents"], ["d2", "d3"])
        self.assertAlmostEqual(alarms["clean"]["rate"], 2 / 3)
        self.assertEqual(alarms["error_free"]["false_alarm_documents"], ["d2"])
        self.assertAlmostEqual(alarms["error_free"]["rate"], 1 / 2)

    def test_unreadable_clean_document_counts_as_false_alarm(self):
        reports = [*REPORTS[:3], report("d4", [], score=None, level="unknown")]
        self.assertEqual(clean_false_alarms(KEY, reports)["clean"]["false_alarms"], 3)

    def test_excluded_out_of_corpus_statute_is_not_scored(self):
        key = [{"doc_id": "doc-0136", "condition": "clean", "quotes": [],
                "citations": [{"cite": "AS 11.56.807", "type": "statute", "exists": False, "injected": False}]}]
        flag = cite_flag("c1", {"type": "statute", "raw_text": "AS 11.56.807", "section": "11.56.807"})
        result = evaluate_unified(key, [report("doc-0136", [flag], score=0.6, level="high")])
        self.assertEqual(result["metrics"]["overall"]["tp"] + result["metrics"]["overall"]["fn"], 0)
        self.assertEqual(result["metrics"]["overall"]["fp"], 0)

    def test_reports_must_cover_the_key(self):
        with self.assertRaises(ValueError):
            evaluate_unified(KEY, REPORTS[:2])


if __name__ == "__main__":
    unittest.main()
