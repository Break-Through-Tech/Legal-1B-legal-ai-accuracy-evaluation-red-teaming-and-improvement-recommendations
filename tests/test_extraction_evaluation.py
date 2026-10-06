import unittest

from scripts.evaluate_extraction import normalize


class EvaluationNormalizationTests(unittest.TestCase):
    def test_case_signal_and_pinpoint_variants_match(self):
        self.assertEqual(
            normalize('case', 'In Ruppe v. Ruppe, 358 P.3d 1284, 1287 (Alaska 2015)'),
            normalize('case', 'Ruppe v. Ruppe, 358 P.3d 1284 (Alaska 2015)'),
        )

    def test_rule_alias_preserves_subsection_and_family(self):
        self.assertEqual(normalize('rule', 'Alaska R. Evid. 505(a)'),
                         normalize('rule', 'Evidence Rule 505(a)'))
        self.assertNotEqual(normalize('rule', 'Rule 505(a)'),
                            normalize('rule', 'Evidence Rule 505(a)'))
        self.assertNotEqual(normalize('statute', 'AS 25.24.160(a)'),
                            normalize('statute', 'AS 25.24.160(a)(4)'))


if __name__ == '__main__':
    unittest.main()
