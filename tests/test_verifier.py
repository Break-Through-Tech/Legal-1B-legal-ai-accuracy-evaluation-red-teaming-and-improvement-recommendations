import unittest

from src.verifier import (
    corpus_record,
    corpus_source_text,
    lookup_citation,
    matching_corpus_records,
    verify_citation,
)


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.corpus = {
            "statutes": {
                "AS 25.24.150": [{
                    "id": "statute-150",
                    "citation": "AS 25.24.150",
                }],
            },
            "civil_rules": {
                "90.3": [
                    {
                        "id": "civil-90-3-a",
                        "type": "court_rule",
                        "citation": "Alaska R. Civ. P. 90.3",
                        "subrule": "a",
                    },
                    {
                        "id": "civil-90-3-b",
                        "type": "court_rule",
                        "citation": "Alaska R. Civ. P. 90.3",
                        "subrule": "b",
                    },
                ],
            },
            "evidence_rules": {
                "505": [{
                    "id": "evidence-505",
                    "type": "court_rule",
                    "ruleNumber": "505",
                    "ruleset": "evidence",
                }],
            },
            "cases": {
                "358 P.3d 1284": [{
                    "id": "case-ruppe",
                    "citation": "Ruppe v. Ruppe (Alaska 2015)",
                    "source_text": "Authoritative opinion text.",
                }],
            },
            "by_id": {},
        }
        self.corpus["by_id"] = {
            record["id"]: record
            for index_name in ("statutes", "civil_rules", "evidence_rules", "cases")
            for records in self.corpus[index_name].values()
            for record in records
        }

    def test_match_returns_corpus_references_for_downstream_lookup(self):
        result = lookup_citation(
            {"type": "rule", "rule_family": "evidence", "number": "505"},
            self.corpus,
        )
        self.assertEqual(result["exists"], "true")
        self.assertEqual(result["corpus_ids"], ["evidence-505"])
        self.assertEqual(result["matched_citations"], ["Alaska R. Evid. 505"])

    def test_rule_families_do_not_collide(self):
        citation = {"type": "rule", "rule_family": "civil", "number": "505"}
        self.assertEqual(verify_citation(citation, self.corpus), "false")

    def test_rule_subsection_selects_specific_source_record(self):
        citation = {
            "type": "rule",
            "rule_family": "civil",
            "number": "90.3",
            "subsection": "(b)(1)",
        }
        result = lookup_citation(citation, self.corpus)
        self.assertEqual(result["corpus_ids"], ["civil-90-3-b"])
        self.assertEqual(result["matched_citations"], ["Alaska R. Civ. P. 90.3(b)"])

    def test_public_resolver_returns_the_same_records_as_stable_id_lookup(self):
        citation = {"type": "case", "reporter_cite": "358 P.3d 1284"}
        matched, = matching_corpus_records(citation, self.corpus)
        stored = corpus_record(self.corpus, matched["id"])
        self.assertIs(stored, matched)
        self.assertEqual(corpus_source_text(stored), "Authoritative opinion text.")

    def test_out_of_scope_statute_is_not_called_hallucinated(self):
        citation = {"type": "statute", "section": "11.56.807"}
        result = lookup_citation(citation, self.corpus)
        self.assertEqual(result["exists"], "out_of_scope")
        self.assertEqual(result["corpus_ids"], [])

    def test_case_matches_reporter_citation(self):
        citation = {"type": "case", "reporter_cite": "358 P.3d 1284"}
        self.assertEqual(verify_citation(citation, self.corpus), "true")


if __name__ == "__main__":
    unittest.main()
