"""Deterministic structured metrics. Every metric stores numerator/denominator."""
from __future__ import annotations

from collections import defaultdict

from .contract import FIELDS, normalize, report_errors, strict_json


def fraction(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def score(example, raw, *, error=None, truncated=False):
    payload = example['payload']
    parsed = None
    errors = []
    try:
        parsed = strict_json(raw)
        json_valid = True
    except (ValueError, TypeError) as exc:
        json_valid = False
        errors.append(str(exc))
    schema_errors = report_errors(parsed, payload) if json_valid else ['invalid JSON']
    errors.extend(schema_errors)
    assessable = json_valid and not schema_errors and not error and not truncated
    counts = defaultdict(lambda: [0, 0])
    def add(key, n, d):
        counts[key][0] += int(n)
        counts[key][1] += int(d)
    add('json_validity', json_valid, 1)
    add('schema_compliance', json_valid and not schema_errors, 1)
    add('assessable_output', assessable, 1)
    source_map = {s['source_id']: s for s in payload['sources']}
    field_labels = []
    for field in FIELDS:
        target = example['expected']['fields'][field]
        available = target['kind'] == 'source_reported'
        answer = parsed['fields'][field] if assessable else None
        correct = bool(answer and normalize(answer['value'], field) == normalize(target['value'], field)
                       and answer['kind'] == target['kind'])
        abstains = bool(answer and answer['kind'] == 'unavailable')
        supports = False
        if answer and answer['kind'] == 'source_reported':
            cited = answer['source_ids']
            supports = bool(cited) and all(
                sid in source_map and source_map[sid]['field'] == field
                and normalize(source_map[sid]['value'], field) == normalize(answer['value'], field)
                for sid in cited)
            add('structured_claims_supported', supports, 1)
            add('unsupported_structured_claims', not supports, 1)
            add('citation_existence', bool(cited), 1)
            for sid in cited:
                add('citation_validity', sid in source_map, 1)
                add('citation_structured_support', sid in source_map and source_map[sid]['field'] == field
                    and normalize(source_map[sid]['value'], field) == normalize(answer['value'], field), 1)
        add('available_reporting_e2e', correct if available else 0, available)
        add('correct_abstention_e2e', correct if not available else 0, not available)
        add('structured_field_success_e2e', correct and (supports if available else True), 1)
        if assessable:
            add('available_reporting_assessable', correct if available else 0, available)
            add('correct_abstention_assessable', correct if not available else 0, not available)
            add('false_abstention_assessable', abstains if available else 0, available)
        field_labels.append({'field': field, 'available': available,
                             'label': 'unassessable' if not assessable else 'correct_supported' if correct and (supports or not available)
                             else 'false_abstention' if available and abstains else 'unsupported_or_incorrect'})
    # Explicit zero denominators, never perfection for a no-claim output.
    for name in ('structured_claims_supported', 'unsupported_structured_claims', 'citation_existence',
                 'citation_validity', 'citation_structured_support', 'available_reporting_assessable',
                 'correct_abstention_assessable', 'false_abstention_assessable'):
        counts[name]
    prose = parsed['claims'] if assessable else []
    for claim in prose:
        for sid in claim['source_ids']:
            add('prose_citation_validity', sid in source_map, 1)
    counts['prose_citation_validity']
    return {'example_id': example['example_id'], 'species_id': example['species_id'],
            'evidence_level': example['evidence_level'], 'parsed': parsed, 'errors': errors,
            'assessable': assessable, 'metrics': {k: fraction(*v) for k,v in counts.items()},
            'field_labels': field_labels, 'prose_claims_pending_annotation': len(prose),
            'prose_support': 'pending_human_review' if prose else 'no_prose_claims',
            'error': error, 'truncated': truncated}


def aggregate(scored):
    totals = defaultdict(lambda: [0,0])
    species = defaultdict(lambda: defaultdict(list))
    for row in scored:
        for key, metric in row['metrics'].items():
            totals[key][0] += metric['numerator']
            totals[key][1] += metric['denominator']
            if metric['value'] is not None:
                species[row['species_id']][key].append(metric['value'])
    # Equal species weight; variants contribute within species, never independent N.
    means = defaultdict(list)
    for metrics in species.values():
        for key, values in metrics.items():
            means[key].append(sum(values)/len(values))
    return {'outputs': len(scored), 'species': len({r['species_id'] for r in scored}),
            'micro': {k:fraction(*v) for k,v in totals.items()},
            'species_macro': {k:{'value':sum(v)/len(v), 'assessable_species':len(v)} for k,v in means.items()},
            'prose_claims_pending_annotation': sum(r['prose_claims_pending_annotation'] for r in scored)}
