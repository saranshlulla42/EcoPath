"""Split species first, then construct sealed evidence variants and targets."""
from __future__ import annotations

import copy
import random
import re
from collections import defaultdict

from .contract import FIELDS, VERSION, canonical, digest, template, validate_record


def assign_splits(records, seed, validation_fraction, test_fraction, group_genus=True, pilot_ids=()):
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1 or validation_fraction + test_fraction >= 1:
        raise ValueError("split fractions must be positive and sum to less than 1")
    ids, names = set(), set()
    for row in records:
        validate_record(row)
        if row["species_id"] in ids or row["scientific_name"].casefold() in names:
            raise ValueError("duplicate species identity")
        ids.add(row["species_id"])
        names.add(row["scientific_name"].casefold())
    if not set(pilot_ids) <= ids:
        raise ValueError("unknown pilot species")
    pilot_groups = {r['genus'] if group_genus else r['species_id'] for r in records if r['species_id'] in pilot_ids}
    groups = defaultdict(list)
    out = {}
    for row in records:
        group = row["genus"] if group_genus else row["species_id"]
        if group in pilot_groups:
            out[row['species_id']] = 'pilot'
        else:
            groups[group].append(row["species_id"])
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    n = len(keys)
    if n == 0 and out:
        return out  # pilot-only collection; no training or final test is implied
    if n < 3:
        raise ValueError("need at least three non-pilot groups for train/validation/test")
    n_test = max(1, round(n * test_fraction))
    n_val = max(1, round(n * validation_fraction))
    if n_test + n_val >= n:
        raise ValueError("not enough independent groups")
    for i, group in enumerate(keys):
        split = 'test' if i < n_test else 'validation' if i < n_test + n_val else 'train'
        out.update({species: split for species in groups[group]})
    return out


def select_pilot(records, count, seed):
    """Select only a curator-verified India sampling frame, round-robin by genus."""
    eligible = []
    excluded = []
    for r in records:
        validate_record(r)
        s = r['sampling']
        if s.get('country_code') != 'IN' or s.get('membership_review') != 'verified' or not s.get('frame_source_url'):
            excluded.append({'species_id': r['species_id'], 'reason': 'India sampling-frame membership unverified'})
        elif not any(e['availability'] == 'available' for e in r['fields'].values()):
            excluded.append({'species_id': r['species_id'], 'reason': 'no collected ecological fields'})
        else:
            eligible.append(r)
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for r in sorted(eligible, key=lambda r:r['species_id']):
        buckets[r['genus']].append(r)
    genera = sorted(buckets)
    rng.shuffle(genera)
    for values in buckets.values():
        rng.shuffle(values)
    picked = []
    while len(picked) < count and any(buckets.values()):
        for genus in genera:
            if buckets[genus] and len(picked) < count:
                picked.append(buckets[genus].pop()['species_id'])
    return {'selected_ids': picked, 'requested': count, 'available': len(eligible), 'excluded': excluded,
            'seed': seed, 'policy': 'verified India frame; >=1 ecological field; seeded genus round robin',
            'status': 'ready' if len(picked) == count else 'insufficient_coverage'}


def make_variant(record, level, split, seed, partial_fraction):
    validate_record(record)
    if level not in {'complete', 'partial', 'minimal'} or not 0 < partial_fraction < 1:
        raise ValueError('invalid masking configuration')
    fields = sorted(k for k, e in record['fields'].items() if e['availability'] == 'available')
    rng = random.Random(f"{seed}:{record['species_id']}")
    shuffled = fields[:]
    rng.shuffle(shuffled)
    masked = set() if level == 'complete' else set(fields) if level == 'minimal' else set(shuffled[:max(1, round(len(fields)*partial_fraction))])
    initially_masked = set(masked)
    # Remove direct value echoes in other structured fields too. Raw summaries
    # never enter the payload. Curators must also review semantic dependencies.
    changed = True
    while changed:
        changed = False
        hidden=[]
        for field in masked:
            value=record['fields'][field]['value']
            hidden.extend(value if isinstance(value,list) else [str(value)])
        for field in fields:
            if field in masked:
                continue
            text=canonical(record['fields'][field]['value']).casefold()
            if any(re.search(r'(?<!\w)'+re.escape(str(value).casefold())+r'(?!\w)',text) for value in hidden):
                masked.add(field);changed=True
    # Project a whitelist. Never pass queries, notes, summaries, raw excerpts,
    # source titles/URLs or hidden references into the model. Canonical source
    # assertions are generated from reviewed extractions, independently per field.
    visible_fields = {}
    visible_sources = []
    provenance = copy.deepcopy(record['sources'])
    for field in FIELDS:
        entry = record['fields'][field]
        if field in masked or entry['availability'] != 'available':
            visible_fields[field] = {'value': None, 'availability': 'missing', 'source_ids': []}
        else:
            source_ids = []
            for sid in entry['source_ids']:
                opaque = 's-' + digest([record['species_id'], field, sid])[:20]
                source_ids.append(opaque)
                visible_sources.append({'source_id': opaque, 'field': field, 'value': copy.deepcopy(entry['value']),
                                        'excerpt': canonical({field:entry['value']})})
            visible_fields[field] = {'value': copy.deepcopy(entry['value']), 'availability': 'available', 'source_ids': source_ids}
    example_id = f"{record['species_id']}:{level}"
    payload = {'schema_version': VERSION, 'example_id': example_id,
               'scientific_name': record['scientific_name'], 'fields': visible_fields, 'sources': visible_sources}
    return {'example_id': example_id, 'species_id': record['species_id'], 'genus': record['genus'],
            'split': split, 'dataset_version': record['dataset_version'], 'evidence_level': level,
            'mask': {'seed': seed, 'partial_fraction': partial_fraction, 'withheld_fields': sorted(masked),
                     'initially_masked_fields': sorted(initially_masked),
                     'dependency_masked_fields': sorted(masked-initially_masked),
                     'policy': 'structured-projection-v1'},
            'payload': payload, 'expected': template(payload),
            'private_reference': {'original_record': copy.deepcopy(record), 'provenance': provenance,
                                  'source_map': {'s-' + digest([record['species_id'], s['field'], s['source_id']])[:20]: s['source_id'] for s in provenance}}}


def build_dataset(records, assignments, seed, partial_fraction, group_genus=True):
    if set(assignments) != {r['species_id'] for r in records}:
        raise ValueError('split assignment coverage mismatch')
    examples = [make_variant(r, level, assignments[r['species_id']], seed, partial_fraction)
                for r in sorted(records, key=lambda x:x['species_id']) for level in ('complete','partial','minimal')]
    validate_examples(examples, group_genus=group_genus)
    return examples


def validate_examples(examples, group_genus=True):
    seen = set()
    splits = defaultdict(set)
    genera = defaultdict(set)
    original_hashes = defaultdict(set)
    names = defaultdict(set)
    for e in examples:
        if e['example_id'] in seen:
            raise ValueError('duplicate example')
        seen.add(e['example_id'])
        splits[e['species_id']].add(e['split'])
        genera[e['genus']].add(e['split'])
        original=e['private_reference']['original_record']
        original_hashes[e['species_id']].add(digest(original))
        names[original['scientific_name'].casefold()].add(e['species_id'])
        if e['split'] not in {'train', 'validation', 'test', 'pilot'}:
            raise ValueError('unknown split')
        # Rebuild from the sealed record rather than substring-based leakage tests.
        m = e['mask']
        rebuilt = make_variant(e['private_reference']['original_record'], e['evidence_level'], e['split'], m['seed'], m['partial_fraction'])
        if canonical(rebuilt) != canonical(e):
            raise ValueError('example differs from deterministic projection; possible leakage')
    if any(len(s) != 1 for s in splits.values()):
        raise ValueError('species leakage')
    if any(len(s) != 1 for s in original_hashes.values()):
        raise ValueError('variants of a species disagree about the collected record')
    if any(len(s) != 1 for s in names.values()):
        raise ValueError('same scientific identity has multiple species IDs')
    if group_genus and any(len(s) != 1 for s in genera.values()):
        raise ValueError('genus leakage')
    return examples
