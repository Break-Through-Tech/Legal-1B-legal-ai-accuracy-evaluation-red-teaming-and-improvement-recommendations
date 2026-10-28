import unittest

from src.quote_fidelity import QuoteSourceIndex, check_document, tokenize


def flagged(results):
    return [r for r in results if r["flagged"]]


class TokenizeTests(unittest.TestCase):
    def test_ellipsis_section_numbers_and_possessives(self):
        self.assertEqual(tokenize("is . . . 27% under AS 25.24.160"),
                         ["is", ". . .", "27", "%", "under", "AS", "25.24.160"])
        self.assertEqual(tokenize("the parents' and parent's non-custodial"),
                         ["the", "parents'", "and", "parent's", "non-custodial"])


class QuotedPassageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = QuoteSourceIndex()

    def check(self, text):
        return check_document(text, self.index, include_unquoted=False)

    def test_faithful_quote_is_verified(self):
        result, = self.check('Under AS 25.20.060(a), the court "shall award custody on the '
                             'basis of the best interests of the child."')
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["flagged"])

    def test_modal_substitution_is_high_severity(self):
        result, = self.check('Under AS 25.20.060(a), the court "may award custody on the '
                             'basis of the best interests of the child."')
        self.assertEqual(result["status"], "material_difference")
        self.assertEqual(result["severity"], "high")
        diff, = [d for d in result["diffs"] if d["material"]]
        self.assertEqual((diff["type"], diff["quote_text"], diff["source_text"]),
                         ("words_changed", "may", "shall"))

    def test_appended_qualifier_is_flagged_whatever_the_words(self):
        result, = self.check('AS 25.20.060(a) provides that the court "shall award custody on the '
                             'basis of the best interests of the child in every contested case."')
        diff, = [d for d in result["diffs"] if d["material"]]
        self.assertEqual((diff["type"], diff["quote_text"]), ("words_added", "in every contested case"))

    def test_dropped_negation_is_flagged(self):
        result, = self.check('Under AS 18.66.130(a), an invitation by the petitioner to communicate '
                             '"does waive or nullify any provision in a protective order."')
        diff, = [d for d in result["diffs"] if d["material"]]
        self.assertEqual((diff["type"], diff["source_text"], diff["severity"]),
                         ("words_omitted", "not", "high"))

    def test_ellipsis_and_punctuation_are_immaterial(self):
        result, = self.check('Under AS 25.20.060(a), "the court shall award custody . . . '
                             'on the basis of the best interests of the child"')
        self.assertIn(result["status"], ("verified", "minor_differences"))
        self.assertFalse(result["flagged"])

    def test_quote_found_under_a_different_authority(self):
        result, = self.check('AS 25.20.090 provides that the child "shall have, to the greatest '
                             'degree practical, equal access to both parents."')
        self.assertEqual(result["status"], "misattributed")
        self.assertEqual(result["matched_source"]["citation"], "AS 25.20.070")

    def test_nearby_second_citation_is_tried(self):
        result, = self.check('Under AS 25.20.070, unless the presumption of AS 25.24.150(g) applies, '
                             '"the child shall have, to the greatest degree practical, equal access '
                             'to both parents."')
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["matched_citation"], "AS 25.20.070")

    def test_testimony_and_defined_terms_are_not_flagged(self):
        results = self.check('Petitioner ("Mother") seeks relief under AS 18.66.100.\n'
                             'Respondent said he would "make sure she regretted it forever."')
        self.assertEqual([r["status"] for r in results], ["no_source_match"])
        self.assertEqual(flagged(results), [])


class UnquotedPassageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = QuoteSourceIndex()

    def test_qualifier_appended_to_copied_statute_text(self):
        text = ("Under AS 25.24.150(c), the court considers the physical, emotional, mental, "
                "religious, and social needs of the child in all cases; and the capability and "
                "desire of each parent to meet these needs.")
        result, = flagged(check_document(text, self.index))
        self.assertEqual(result["kind"], "unquoted")
        diff, = [d for d in result["diffs"] if d["material"]]
        self.assertEqual(diff["quote_text"], "in all cases")

    def test_ordinary_paraphrase_is_not_flagged(self):
        text = ("Under AS 25.24.150(c), the court considers the physical, emotional, mental, "
                "religious, and social needs of the child, and the capability and desire of "
                "each parent to meet those needs.")
        results = check_document(text, self.index)
        self.assertTrue(results)
        self.assertEqual(flagged(results), [])


if __name__ == "__main__":
    unittest.main()
