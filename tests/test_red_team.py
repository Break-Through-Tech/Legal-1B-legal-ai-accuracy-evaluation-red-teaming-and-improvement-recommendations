import io
import unittest

import docx

from src.detect import Detector


def make_docx(text: str) -> bytes:
    document = docx.Document()
    for paragraph in text.split("\n"):
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class RedTeamDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector()

    def check(self, text: str) -> dict:
        return self.detector.check(make_docx(text), filename="red-team.docx")

    @staticmethod
    def citation_flags(report: dict) -> list[dict]:
        return [flag for flag in report["flags"] if flag["stage"] == "existence"]

    @staticmethod
    def quote_flags(report: dict) -> list[dict]:
        return [flag for flag in report["flags"] if flag["stage"] == "quote_fidelity"]

    def test_fabricated_statute_is_caught(self):
        flags = self.citation_flags(self.check("The court applies AS 25.24.999."))

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Hallucinated")
        self.assertTrue(flags[0]["flagged"])
        self.assertEqual(flags[0]["severity"], "high")

    def test_fabricated_rule_is_caught_without_cross_family_collision(self):
        flags = self.citation_flags(self.check("The court applies Civil Rule 913(b)."))

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Hallucinated")
        self.assertTrue(flags[0]["flagged"])

    def test_wrong_reporter_is_caught_even_when_case_name_is_real(self):
        flags = self.citation_flags(
            self.check("See Hollister v. Brandt, 449 P.3d 701 (Alaska 2019).")
        )

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Hallucinated")
        self.assertTrue(flags[0]["flagged"])

    def test_wrong_case_name_on_real_reporter_is_caught(self):
        flags = self.citation_flags(
            self.check("See Hollister v. Brandt, 449 P.3d 700 (Alaska 2019).")
        )

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Wrong Case Name")
        self.assertTrue(flags[0]["flagged"])

    def test_altered_quote_with_modal_change_is_caught(self):
        report = self.check(
            'Under AS 25.20.060(a), the court "may award custody on the '
            'basis of the best interests of the child."'
        )
        flags = self.quote_flags(report)

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "material_difference")
        self.assertTrue(flags[0]["flagged"])
        self.assertEqual(flags[0]["severity"], "high")

    def test_fake_subsection_of_real_statute_passes_current_section_level_check(self):
        flags = self.citation_flags(self.check("The court applies AS 25.20.060(a)(999)."))

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Valid/Verified")
        self.assertFalse(flags[0]["flagged"])

    def test_short_form_citation_is_not_extracted(self):
        report = self.check("The next paragraph relies on Id. for the same proposition.")

        self.assertEqual(self.citation_flags(report), [])

    def test_known_out_of_scope_real_statute_is_not_flagged(self):
        flags = self.citation_flags(self.check("The order references AS 11.56.807."))

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "Mismatched Context/Format")
        self.assertFalse(flags[0]["flagged"])

    def test_unquoted_copied_text_can_create_a_clean_document_false_alarm(self):
        report = self.check(
            "Under AS 25.24.150(c), the court considers the physical, emotional, "
            "mental, religious, and social needs of the child in all cases; and the "
            "capability and desire of each parent to meet these needs."
        )

        flags = self.quote_flags(report)
        self.assertTrue(any(flag["flagged"] for flag in flags))
        self.assertTrue(any(flag["item_type"] == "unquoted" for flag in flags))


if __name__ == "__main__":
    unittest.main()
