import unittest

from scripts.classify_citations import classify, explain_reason


class CitationClassificationTests(unittest.TestCase):
    def test_corpus_match_is_valid(self):
        self.assertEqual(classify("true"), "Valid/Verified")

    def test_missing_corpus_authority_is_hallucinated(self):
        self.assertEqual(classify("false"), "Hallucinated")

    def test_out_of_scope_requires_review(self):
        label = classify("out_of_scope")
        self.assertEqual(label, "Mismatched Context/Format")
        self.assertIn("outside the benchmark corpus", explain_reason("out_of_scope", label))


if __name__ == "__main__":
    unittest.main()
