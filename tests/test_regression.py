import copy
import unittest

from src.regression import (
    load_cases,
    load_evaluation,
    run_case,
    run_regression,
    validate_missed_fabrications,
)


EXPECTED_CATEGORIES = {
    "fabricated_statute",
    "fabricated_rule",
    "fabricated_case",
    "wrong_reporter",
    "altered_quote",
}

EXPECTED_CAVEAT_CASES = {
    "out-of-scope-as-11-56-807",
    "out-of-scope-as-11-56-810",
    "corrected-real-statute-as-25-24-900",
    "corrected-real-statute-as-25-24-910",
    "corrected-real-statute-as-25-24-920",
}


class RegressionTests(unittest.TestCase):
    def test_fixture_covers_every_benchmark_corruption_category(self):
        fixture = load_cases()
        categories = {case["category"] for case in fixture["cases"]}

        self.assertTrue(EXPECTED_CATEGORIES.issubset(categories))

    def test_fixture_covers_required_benchmark_caveats(self):
        fixture = load_cases()
        case_ids = {case["id"] for case in fixture["cases"]}

        self.assertTrue(EXPECTED_CAVEAT_CASES.issubset(case_ids))
        self.assertEqual(
            fixture["benchmark_caveats"]["out_of_scope_real_authorities"],
            ["AS 11.56.807", "AS 11.56.810"],
        )
        self.assertEqual(
            fixture["benchmark_caveats"]["corrected_real_statutes"],
            ["AS 25.24.900", "AS 25.24.910", "AS 25.24.920"],
        )

    def test_pinned_full_run_has_no_missed_fabrications(self):
        fixture = load_cases()
        source = load_evaluation(fixture["source_evaluation"])

        self.assertEqual(source["total_documents"], 200)
        self.assertEqual(source["metrics"]["end_to_end"]["overall"]["tp"], 273)
        self.assertEqual(source["metrics"]["end_to_end"]["overall"]["fn"], 0)
        self.assertEqual(source["missed_fabrications"], [])
        self.assertTrue(source["answer_key"]["answer_key_frozen"])
        self.assertEqual(source["run_log"]["documents"]["failed"], 0)

    def test_every_pinned_miss_requires_a_regression_case(self):
        fixture = load_cases()
        evaluation = {
            "missed_fabrications": [
                {
                    "doc_id": "doc-9999",
                    "identity": ["statute", "99.99.999"],
                    "cite": "AS 99.99.999",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "doc-9999: AS 99.99.999"):
            validate_missed_fabrications(fixture, evaluation)

    def test_mapped_miss_must_reproduce_the_authority_and_expected_flag(self):
        fixture = copy.deepcopy(load_cases())
        evaluation = {
            "missed_fabrications": [
                {
                    "doc_id": "doc-9999",
                    "identity": ["statute", "99.99.999"],
                    "cite": "AS 99.99.999",
                }
            ]
        }
        case = fixture["cases"][0]
        case["source_miss"] = {
            "doc_id": "doc-9999",
            "identity": ["statute", "99.99.999"],
        }

        with self.assertRaisesRegex(ValueError, "does not reproduce and assert"):
            validate_missed_fabrications(fixture, evaluation)

        case["text"] = "The court applies AS 99.99.999."
        case["expected"]["values"]["text"] = "AS 99.99.999"
        validate_missed_fabrications(fixture, evaluation)

    def test_unexpected_flagged_results_fail_a_case(self):
        case = copy.deepcopy(load_cases()["cases"][0])

        class DetectorWithExtraFlag:
            def check(self, *args, **kwargs):
                return {
                    "errors": [],
                    "flags": [
                        {
                            "stage": "existence",
                            "citation_type": "statute",
                            "text": "AS 25.24.999",
                            "status": "Hallucinated",
                            "flagged": True,
                            "severity": "high",
                        },
                        {
                            "stage": "quote_fidelity",
                            "text": "unexpected passage",
                            "status": "material_difference",
                            "flagged": True,
                        },
                    ],
                }

        failures = run_case(DetectorWithExtraFlag(), case)

        self.assertTrue(any("unexpected flagged result" in failure for failure in failures))

    def test_all_regression_cases_pass(self):
        failures = [result for result in run_regression() if result["failures"]]

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
