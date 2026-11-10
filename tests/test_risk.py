import unittest

from src.risk import level_for, score_document


def flag(n, severity="high", stage="existence", status="Hallucinated", authority=None, item_type="citation"):
    return {"flag_id": f"f{n}", "stage": stage, "item_type": item_type, "status": status, "text": f"AS {n}",
            "flagged": severity is not None, "severity": severity,
            "evidence": {"authority": authority or f"statute|{n}"}}


class RiskScoreTests(unittest.TestCase):
    def test_no_flags_is_no_risk(self):
        risk = score_document([flag(1, None, status="Valid/Verified")])
        self.assertEqual((risk["score"], risk["level"], risk["drivers"]), (0, "none", []))

    def test_one_fabricated_citation_is_high(self):
        self.assertEqual(score_document([flag(1)])["level"], "high")

    def test_score_never_decreases_as_problems_are_added(self):
        flags, previous = [], 0
        for n, severity in enumerate(["low", "medium", "high", "low", "high"]):
            flags.append(flag(n, severity))
            score = score_document(flags)["score"]
            self.assertGreaterEqual(score, previous)
            self.assertLess(score, 1)
            previous = score

    def test_repeated_authority_counts_once(self):
        once = score_document([flag(1, authority="statute|25.24.999")])
        twice = score_document([flag(1, authority="statute|25.24.999"), flag(2, authority="statute|25.24.999")])
        self.assertEqual(once["score"], twice["score"])
        self.assertEqual(twice["problems"], 1)

    def test_drivers_most_severe_first(self):
        risk = score_document([flag(1, "medium", stage="quote_fidelity", status="material_difference",
                                    item_type="quoted"), flag(2), flag(3)])
        self.assertEqual(risk["drivers"], ["2 fabricated citations", "1 altered quote"])

    def test_extraction_failure_is_unknown(self):
        risk = score_document([], errors=[{"stage": "extract"}])
        self.assertEqual((risk["score"], risk["level"], risk["incomplete"]), (None, "unknown", True))

    def test_levels(self):
        self.assertEqual([level_for(s) for s in (0, 0.1, 0.3, 0.6, 0.99)], ["none", "low", "medium", "high", "high"])


if __name__ == "__main__":
    unittest.main()
