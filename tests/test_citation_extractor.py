import unittest

from src.citation_extractor import extract_citations


class CitationExtractorTests(unittest.TestCase):
    def test_statute_lists_ranges_and_offsets(self):
        examples = ["AS 25.24.160(a)(4)(A), (C), (D)", "AS 25.24.200(a)(2)-(4)"]
        text = " and ".join(examples)
        results = extract_citations(text)
        self.assertEqual([item["raw_text"] for item in results], examples)
        for item in results:
            self.assertEqual(text[item["start"]:item["end"]], item["raw_text"])

    def test_rule_families_and_fabrication(self):
        results = extract_citations(
            "Alaska Civil Rule 907(a)(2); CIVIL RULE 90.3; Rule 90.3; "
            "Alaska R. Evid. 505; Alaska R. Civ. P. 90.3"
        )
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["number"], "907")
        self.assertEqual(results[0]["subsection"], "(a)(2)")
        self.assertEqual([item["rule_family"] for item in results],
                         ["civil", "civil", None, "evidence", "civil"])

    def test_case_initials_signal_and_pinpoint(self):
        cite = "Ronny M. v. Nanette H., 303 P.3d 392, 395 (Alaska 2013)"
        text = "See " + cite + "."
        result, = extract_citations(text)
        self.assertEqual(result["raw_text"], cite)
        self.assertEqual(result["case_name"], "Ronny M. v. Nanette H.")
        self.assertEqual(result["reporter_cite"], "303 P.3d 392")
        self.assertEqual(result["pinpoint"], "395")
        self.assertEqual(text[result["start"]:result["end"]], cite)

    def test_repeated_mentions_and_non_citations(self):
        self.assertEqual(extract_citations("2015, $95,000, 27 percent"), [])
        results = extract_citations("AS 25.24.946 then Rule 90.3 then AS 25.24.946")
        self.assertEqual([item["type"] for item in results], ["statute", "rule", "statute"])


if __name__ == "__main__":
    unittest.main()
