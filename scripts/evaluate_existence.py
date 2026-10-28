"""Evaluate corpus existence predictions; false existence is the positive class."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = ("doc-0136", ("statute", "11.56.807"))


def identity(citation):
    """Authority identity shared by key strings and structured extractor records."""
    kind = citation['type']
    text = citation.get('cite', citation.get('raw_text', ''))
    if kind == 'statute':
        match = re.search(r'\bAS\s+(\d+\.\d+\.\d+)', text, re.I)
        value = citation.get('section') or (match.group(1) if match else None)
        result = (kind, value)
    elif kind == 'rule':
        match = re.search(r'(?:Rule|R\.\s*(?:Civ\.\s*P\.|Evid\.))\s*(\d+(?:\.\d+)?)', text, re.I)
        number = citation.get('number') or (match.group(1) if match else None)
        family = citation.get('rule_family') or ('evidence' if re.search(r'evid', text, re.I) else 'civil')
        result = (kind, family, str(number) if number is not None else None)
    elif kind == 'case':
        match = re.search(r'(\d+)\s+P\.(2d|3d)\s+(\d+)', citation.get('reporter_cite') or text, re.I)
        result = (kind, f'{match[1]} P.{match[2].lower()} {match[3]}' if match else None)
    else:
        raise ValueError(f'Unsupported citation type: {kind}')
    if None in result:
        raise ValueError(f'Cannot identify citation: {citation}')
    return result


def indexed(rows):
    result = {}
    for row in rows:
        doc_id = row['doc_id']
        if doc_id in result:
            raise ValueError(f'Duplicate document ID: {doc_id}')
        result[doc_id] = row
    return result


def metrics(counts):
    c = {k: counts[k] for k in ('tp', 'fp', 'fn', 'tn')}
    def ratio(a, b):
        return a / b if b else None
    return {**c, 'precision': ratio(c['tp'], c['tp'] + c['fp']),
            'recall': ratio(c['tp'], c['tp'] + c['fn']),
            'f1': ratio(2*c['tp'], 2*c['tp'] + c['fp'] + c['fn'])}


def evaluate(key_rows, prediction_rows, expected_documents=200):
    key, predictions = indexed(key_rows), indexed(prediction_rows)
    if len(key) != expected_documents or set(key) != set(predictions):
        raise ValueError('Document IDs must agree and cover the expected benchmark documents')
    totals = {view: defaultdict(Counter) for view in ('end_to_end', 'verifier_only')}
    audit = {name: [] for name in ('exclusions', 'false_positives', 'missed_fabrications',
                                  'unmatched_extractions', 'abstentions', 'conflicting_predictions', 'missing_real_citations')}
    coverage = Counter(expected=0, matched=0, missing=0)
    per_doc = []
    for doc_id, doc in key.items():
        expected, extracted = {}, defaultdict(list)
        for c in doc['citations']:
            ident = identity(c)
            if type(c['exists']) is not bool:
                raise ValueError('Answer-key exists must be boolean')
            if ident in expected and expected[ident]['exists'] != c['exists']:
                raise ValueError(f'Conflicting answer-key labels: {doc_id} {ident}')
            if ident not in expected:
                expected[ident] = {**c, 'injection_types': []}
            tag = c.get('injected')
            if tag and tag not in expected[ident]['injection_types']:
                expected[ident]['injection_types'].append(tag)
        for c in predictions[doc_id]['citations']:
            if c.get('exists') not in ('true', 'false', 'out_of_scope'):
                raise ValueError(f'Invalid prediction: {doc_id} {c}')
            extracted[identity(c)].append(c)
        local = {view: Counter() for view in totals}
        for ident, mentions in extracted.items():
            if ident not in expected:
                audit['unmatched_extractions'].append({'doc_id': doc_id, 'identity': ident, 'mentions': mentions})
        for ident, c in expected.items():
            mentions = extracted.get(ident, [])
            item = {'doc_id': doc_id, 'identity': ident, 'cite': c['cite'],
                    'expected_exists': c['exists'], 'predictions': mentions}
            if (doc_id, ident) == EXCLUDED:
                audit['exclusions'].append({**item, 'reason': 'Known real authority outside corpus; DATA_DICTIONARY §3.2'})
                continue
            coverage['expected'] += 1
            coverage['matched' if mentions else 'missing'] += 1
            states = {m['exists'] for m in mentions}
            prediction = next(iter(states)) if len(states) == 1 else None
            if len(states) > 1:
                audit['conflicting_predictions'].append(item)
            elif prediction == 'out_of_scope':
                audit['abstentions'].append(item)
            decided = prediction in ('true', 'false')
            flagged = prediction == 'false'
            positive = not c['exists']
            reason = ('not_extracted' if not mentions else 'conflicting_predictions' if len(states) > 1
                      else 'unexpected_abstention' if not decided else 'incorrect_existence_prediction')
            if positive and not flagged:
                audit['missed_fabrications'].append({**item, 'reason': reason})
            elif not positive and flagged:
                audit['false_positives'].append({**item, 'reason': reason})
            if not positive and not mentions:
                audit['missing_real_citations'].append(item)
            groups = ['overall', 'type:' + c['type'], 'condition:' + doc['condition']]
            groups += ['fabrication:' + tag for tag in c['injection_types']]
            for view in totals:
                # Abstentions/conflicts never count as successful predictions.
                if view == 'verifier_only' and not decided:
                    continue
                if not positive and not decided:
                    continue
                outcome = ('tp' if flagged else 'fn') if positive else ('fp' if flagged else 'tn')
                local[view][outcome] += 1
                for group in groups:
                    totals[view][group][outcome] += 1
        per_doc.append({'doc_id': doc_id, **{v: metrics(c) for v, c in local.items()}})
    return {'total_documents': len(key), 'raw_answer_key_entries': sum(len(d['citations']) for d in key.values()),
            'policy': 'Unique authority per document; false existence is positive. End-to-end includes unextracted fabrications as FN. Verifier-only includes decided matched authorities. Unknown predictions are audited, not assumed fabricated. Precision covers labeled predictions only.',
            'coverage': {**coverage, 'recall': coverage['matched']/coverage['expected'] if coverage['expected'] else None},
            'metrics': {v: {g: metrics(c) for g, c in groups.items()} for v, groups in totals.items()},
            'documents': per_doc, **audit}


def main():
    path = ROOT / 'data/processed/verification.jsonl'
    if not path.exists():
        raise SystemExit('Run scripts/verify_citations.py first')
    report = evaluate(json.loads((ROOT / 'data/benchmark/answer-key.json').read_text()),
                      [json.loads(line) for line in path.read_text().splitlines() if line.strip()])
    output = ROOT / 'data/processed/existence-evaluation.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'coverage': report['coverage'], 'metrics': report['metrics'],
                      'audit_counts': {k: len(report[k]) for k in ('exclusions', 'false_positives', 'missed_fabrications', 'unmatched_extractions', 'abstentions', 'conflicting_predictions')}}, indent=2))
    print(f'Detailed results: {output}')


if __name__ == '__main__':
    main()
