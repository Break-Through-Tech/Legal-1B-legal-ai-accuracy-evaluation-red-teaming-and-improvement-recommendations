import unittest

from scripts.evaluate_existence import evaluate, identity, metrics


def citation(text='AS 25.24.999', exists=False, kind='statute'):
    return {'cite': text, 'type': kind, 'exists': exists}


def prediction(text='AS 25.24.999', exists='false', kind='statute'):
    return {'raw_text': text, 'type': kind, 'exists': exists}


class ExistenceEvaluationTests(unittest.TestCase):
    def run_eval(self, citations, predictions, doc_id='doc-0001'):
        return evaluate([{'doc_id': doc_id, 'condition': 'corrupt', 'citations': citations}],
                        [{'doc_id': doc_id, 'citations': predictions}], expected_documents=1)

    def test_perfect_and_duplicate_mentions(self):
        r = self.run_eval([citation(), citation(), citation('AS 25.24.150(a)', True)],
                          [prediction(), prediction(), prediction('AS 25.24.150(a)(4)', 'true')])
        self.assertEqual(r['coverage']['expected'], 2)
        for view in r['metrics'].values():
            self.assertEqual(view['overall']['f1'], 1)
            self.assertEqual(view['overall']['tn'], 1)

    def test_missing_fabrication_and_real_coverage_gap(self):
        r = self.run_eval([citation(), citation('AS 25.24.150', True)], [])
        self.assertEqual(r['metrics']['end_to_end']['overall']['fn'], 1)
        self.assertEqual(r['documents'][0]['verifier_only']['fn'], 0)
        self.assertEqual(len(r['missing_real_citations']), 1)
        self.assertEqual(r['missed_fabrications'][0]['reason'], 'not_extracted')

    def test_false_positive_and_wrong_reporter(self):
        c = citation('Hayes v. Hayes, 614 P.2d 743 (Alaska 1996)', kind='case')
        c['injected'] = 'wrong_reporter'
        r = self.run_eval([c, citation('AS 25.24.150', True)],
                          [prediction('614 P.2d 743', kind='case'), prediction('AS 25.24.150')])
        self.assertEqual(r['metrics']['end_to_end']['overall']['precision'], .5)
        self.assertEqual(r['metrics']['end_to_end']['fabrication:wrong_reporter']['recall'], 1)
        self.assertEqual(len(r['false_positives']), 1)

    def test_rule_aliases_and_namespaces(self):
        def rule(s):
            return identity(citation(s, kind='rule'))
        self.assertEqual(rule('Civil Rule 90.3(a)'), rule('Alaska R. Civ. P. 90.3'))
        self.assertEqual(rule('Rule 505'), rule('Civil Rule 505'))
        self.assertEqual(rule('Evidence Rule 505(a)'), rule('Alaska R. Evid. 505'))
        self.assertNotEqual(rule('Rule 505'), rule('Evidence Rule 505'))

    def test_exclusion(self):
        r = self.run_eval([citation('AS 11.56.807')],
                          [prediction('AS 11.56.807', 'out_of_scope')], 'doc-0136')
        self.assertEqual(len(r['exclusions']), 1)
        self.assertEqual(r['coverage']['expected'], 0)

    def test_conflicting_labels(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting answer-key'):
            self.run_eval([citation(), citation(exists=True)], [])

    def test_conflicts_abstentions_and_unlabeled(self):
        for preds, field in (([prediction(), prediction(exists='true')], 'conflicting_predictions'),
                             ([prediction(exists='out_of_scope')], 'abstentions')):
            r = self.run_eval([citation()], preds + [prediction('AS 25.24.888')])
            self.assertEqual(len(r[field]), 1)
            self.assertEqual(len(r['unmatched_extractions']), 1)
            self.assertEqual(r['metrics']['end_to_end']['overall']['fn'], 1)
            self.assertEqual(r['documents'][0]['verifier_only']['tp'], 0)

    def test_document_validation(self):
        row = {'doc_id': 'a', 'condition': 'clean', 'citations': []}
        for key, pred, count in (([row], [], 1), ([row, row], [row], 2),
                                 ([row], [row, row], 1), ([row], [row], 200)):
            with self.assertRaises(ValueError):
                evaluate(key, pred, count)

    def test_undefined_metrics(self):
        from collections import Counter
        self.assertEqual(metrics(Counter()), {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0,
                                              'precision': None, 'recall': None, 'f1': None})


if __name__ == '__main__':
    unittest.main()
