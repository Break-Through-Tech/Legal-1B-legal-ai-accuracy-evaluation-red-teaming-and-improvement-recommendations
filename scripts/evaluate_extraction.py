"""Evaluate saved citation extraction against the benchmark key (no tuning)."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def normalize(kind, text):
    text = re.sub(r"\s+", " ", text).strip().lower().replace("–", "-")
    if kind == "case":
        text = re.sub(r"^(?:(?:see|in|under|compare)\s+)+", "", text)
        text = re.sub(r"(p\.(?:2d|3d)\s+\d+),\s*\d+(?:-\d+)?(?=\s*\()", r"\1", text)
    elif kind == "rule":
        text = re.sub(r"^alaska\s+", "", text)
        text = re.sub(r"^r\.\s*civ\.\s*p\.", "civil rule", text)
        text = re.sub(r"^r\.\s*evid\.", "evidence rule", text)
    return text


def read_jsonl(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = {row['doc_id']: row for row in rows}
    if len(rows) != len(result):
        raise ValueError(f"Duplicate document IDs in {path}")
    return result


def main():
    key = json.loads((ROOT / 'data/benchmark/answer-key.json').read_text())
    actual = read_jsonl(ROOT / 'data/processed/citations.jsonl')
    documents = read_jsonl(ROOT / 'data/processed/documents.jsonl')
    ids = [doc['doc_id'] for doc in key]
    if len(ids) != len(set(ids)) or set(ids) != set(actual) or set(ids) != set(documents):
        raise ValueError('Document IDs must agree across all three inputs')
    totals = defaultdict(Counter)
    misses = []
    per_doc = []
    for doc in key:
        doc_id = doc['doc_id']
        extracted = {(c['type'], normalize(c['type'], c['raw_text'])) for c in actual[doc_id]['citations']}
        expected = {(c['type'], normalize(c['type'], c['cite'])) for c in doc['citations']}
        hits = expected & extracted
        per_doc.append({'doc_id': doc_id, 'expected': len(expected), 'matched': len(hits),
                        'recall': len(hits) / len(expected) if expected else None})
        seen = set()
        for c in doc['citations']:
            identity = (c['type'], normalize(c['type'], c['cite']))
            if identity in seen:
                continue
            seen.add(identity)
            matched = identity in hits
            for group in ('overall', 'type:' + c['type'], 'condition:' + doc['condition'],
                          'injected:' + str(c.get('injected', False))):
                totals[group]['expected'] += 1
                totals[group]['matched'] += int(matched)
            if not matched:
                text = documents[doc_id]['text']
                needle = re.sub(r'\s+', ' ', c['cite']).lower()
                body = re.sub(r'\s+', ' ', text).lower()
                pos = body.find(needle)
                # Separate absent literal strings from proven detection failures.
                extensions = [value for kind, value in extracted if kind == identity[0]
                              and value.startswith(identity[1])
                              and value[len(identity[1]):].startswith(('(', ',', '-'))]
                reason = ('captured_with_more_specific_subsection_or_list' if extensions else
                          'present_in_text_but_not_matched' if pos >= 0 else 'key_string_not_found_verbatim')
                misses.append({'doc_id': doc_id, **c, 'reason': reason,
                               'related_extractions': extensions,
                               'context': body[max(0, pos-80):pos+len(needle)+80] if pos >= 0 else None})
    result = {'matching_policy': 'Unique normalized (type, citation) per document; whitespace/case normalized; case signals and pinpoint pages ignored; civil/evidence rule aliases normalized; bare rules remain distinct; subsections and lists/ranges remain exact.',
              'raw_answer_key_entries': sum(len(d['citations']) for d in key),
              'total_documents': len(key), 'metrics': {}, 'documents': per_doc,
              'miss_reasons': dict(Counter(m['reason'] for m in misses)), 'misses': misses}
    for group, counts in totals.items():
        result['metrics'][group] = {**counts, 'missed': counts['expected']-counts['matched'],
                                    'recall': counts['matched']/counts['expected']}
    covered = sum(m['reason'] == 'captured_with_more_specific_subsection_or_list' for m in misses)
    result['provision_coverage'] = {'expected': totals['overall']['expected'],
                                  'matched': totals['overall']['matched'] + covered,
                                  'recall': (totals['overall']['matched'] + covered) / totals['overall']['expected'],
                                  'policy': 'Also credit broader key provisions captured with additional subsections, lists, or ranges; this does not prove exact span or range-member extraction.'}
    path = ROOT / 'data/processed/extraction-evaluation.json'
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'metrics': result['metrics'], 'miss_reasons': result['miss_reasons']}, indent=2))
    print(f'Detailed results: {path}')


if __name__ == '__main__':
    main()
