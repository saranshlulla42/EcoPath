"""Generate traceable tables and blinded annotation packets from saved runs."""
from collections import Counter, defaultdict
import csv
from pathlib import Path
import random

from .contract import digest, read_jsonl, write_jsonl_new, write_new
from .metrics import aggregate
from .runner import latest_attempts


def summarize(run_path, output):
    rows = list(latest_attempts(read_jsonl(run_path)).values())
    groups = defaultdict(list)
    for row in rows:
        groups[(row['phase'],row['method_id'],'all')].append(row)
        groups[(row['phase'],row['method_id'],row['evidence_level'])].append(row)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    summaries = []
    errors = []
    for (phase,method,level),values in sorted(groups.items()):
        a = aggregate([r['score'] for r in values])
        latencies = sorted(r['result']['wall_seconds'] for r in values if not r['error'])
        tokens = [r['result'].get('output_tokens') for r in values]
        summaries.append({'phase':phase,'method_id':method,'level':level,'metrics':a,
                          'failures':sum(bool(r['error']) for r in values),
                          'latency_scope':'single-example wall time; excludes model loading and warmups',
                          'mean_wall_seconds':sum(latencies)/len(latencies) if latencies else None,
                          'output_tokens':sum(x for x in tokens if x is not None) if any(x is not None for x in tokens) else None,
                          'training_seed':values[0]['training_seed'],
                          'configuration':values[0]['generation']})
    for row in rows:
        labels = []
        if row['error']: labels.append('execution_error')
        if row['score']['truncated']: labels.append('truncation')
        if not row['score']['metrics']['json_validity']['value']: labels.append('invalid_json')
        elif not row['score']['metrics']['schema_compliance']['value']: labels.append('schema_failure')
        labels += [l['label'] for l in row['score']['field_labels'] if l['label'] not in {'correct_supported','unassessable'}]
        if row['score']['prose_claims_pending_annotation']: labels.append('prose_pending_human_review')
        for label in labels:
            errors.append({'method_id':row['method_id'],'example_id':row['example_id'],'attempt':row['attempt'],
                           'error_type':label,'run_path':str(Path(run_path).resolve())})
    write_new(output/'summary.json',{'results':summaries,'error_counts':dict(Counter(e['error_type'] for e in errors)),
                                    'scope':'structured extraction support; unrestricted prose is not automatically verified'})
    write_jsonl_new(output/'errors.jsonl',errors)
    with (output/'metrics.csv').open('x') as handle:
        w = csv.writer(handle); w.writerow(['phase','method_id','level','outputs','species','metric','numerator','denominator','micro_value','species_macro_value'])
        for r in summaries:
            for key,m in r['metrics']['micro'].items():
                w.writerow([r['phase'],r['method_id'],r['level'],r['metrics']['outputs'],r['metrics']['species'],key,
                            m['numerator'],m['denominator'],m['value'],r['metrics']['species_macro'].get(key,{}).get('value')])
    lines = ['# Saved-run results','', 'Generated from '+str(Path(run_path).resolve()),'',
             '| Phase | Method | Evidence | Species | Outputs | JSON valid | Schema compliant | Field success (end to end) |',
             '|---|---|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        metrics=r['metrics']['micro']
        fmt=lambda key: f"{metrics[key]['numerator']}/{metrics[key]['denominator']}"
        lines.append(f"| {r['phase']} | {r['method_id']} | {r['level']} | {r['metrics']['species']} | {r['metrics']['outputs']} | {fmt('json_validity')} | {fmt('schema_compliance')} | {fmt('structured_field_success_e2e')} |")
    lines += ['', 'No automatic semantic-support judgement is made for unrestricted prose.',
              'Template results establish contract behavior; they do not establish model improvement.']
    (output/'tables.md').write_text('\n'.join(lines)+'\n')
    return summaries


def annotation_export(run_path, dataset_path, output, seed):
    rows = list(latest_attempts(read_jsonl(run_path)).values())
    examples = {e['example_id']:e for e in read_jsonl(dataset_path)}
    rng = random.Random(seed)
    rng.shuffle(rows)
    blind, key = [], []
    for i,row in enumerate(rows):
        # IDs do not encode method/seed/example. The private key stays separate.
        aid = digest([seed,i,row['protocol_hash'],row['method_id'],row['example_id']])[:24]
        e = examples[row['example_id']]
        visible = {s['source_id'] for s in e['payload']['sources']}
        original_ids = {e['private_reference']['source_map'][sid] for sid in visible}
        blind.append({'annotation_id':aid,'evidence':e['payload'],
                      'reviewer_provenance':[s for s in e['private_reference']['provenance'] if s['source_id'] in original_ids],
                      'source_map':{k:v for k,v in e['private_reference']['source_map'].items() if k in visible},
                      'raw_response':row['result']['raw'], 'parsed_response':row['score']['parsed'],
                      'structural_status':'assessable' if row['score']['assessable'] else 'unassessable',
                      'reviewer_id':None,'labels':[], 'overall_evidence_use':None,
                      'adjudication':None,'label_origin':'human_pending'})
        key.append({'annotation_id':aid,'method_id':row['method_id'],'training_seed':row['training_seed'],
                    'example_id':row['example_id'],'attempt':row['attempt'],'protocol_hash':row['protocol_hash']})
    output = Path(output)
    write_jsonl_new(output/'blind_review.jsonl',blind)
    write_jsonl_new(output/'PRIVATE_blinding_key.jsonl',key)
    return len(blind)


def adjudicate(review_paths, output):
    records = defaultdict(list)
    origins = {'human','llm_assisted','automated'}
    labels = {'supported','unsupported','contradicted','unverifiable','not_factual','unassessable'}
    for path in review_paths:
        for row in read_jsonl(path):
            if row.get('label_origin') not in origins or not row.get('reviewer_id'):
                raise ValueError('completed reviews need explicit origin and reviewer identity')
            for label in row.get('labels',[]):
                if label.get('label') not in labels or not label.get('claim_text') or not label.get('rationale'):
                    raise ValueError('claim labels require text, label and rationale')
            records[row['annotation_id']].append(row)
    results=[]
    for aid, reviews in records.items():
        reviewer_ids=[r['reviewer_id'] for r in reviews]
        if len(reviewer_ids)!=len(set(reviewer_ids)):
            raise ValueError('duplicate reviewer for annotation')
        human=[r for r in reviews if r['label_origin']=='human']
        signatures={digest({'labels':r['labels'],'overall_evidence_use':r.get('overall_evidence_use')}) for r in human}
        results.append({'annotation_id':aid,'human_reviews':human,
                        'supplementary_reviews':[r for r in reviews if r['label_origin']!='human'],
                        'adjudication_required':len(human)<2 or len(signatures)>1,
                        'adjudicator_id':None,'adjudicated_labels':None,
                        'status':'pending_adjudication' if len(human)<2 or len(signatures)>1 else 'human_agreement'})
    write_jsonl_new(output,results)
    return results


def annotation_summary(adjudication_path,output):
    """Summarise completed human decisions; pending reviews never become labels."""
    rows=read_jsonl(adjudication_path)
    counts=Counter();citation_counts=Counter();pending=[];assessed=0;success=0;no_claims=0
    allowed={'supported','unsupported','contradicted','unverifiable','not_factual','unassessable'}
    for row in rows:
        if row.get('adjudicator_id') and row.get('adjudicated_labels') is not None:
            labels=row['adjudicated_labels']
            overall=row.get('adjudicated_overall_evidence_use')
        elif row.get('status')=='human_agreement' and len(row['human_reviews'])>=2:
            labels=row['human_reviews'][0]['labels']
            overall=row['human_reviews'][0].get('overall_evidence_use')
        else:
            pending.append(row['annotation_id']);continue
        if overall not in {'supported_and_complete','unsupported_or_incomplete','unassessable'}:
            pending.append(row['annotation_id']);continue
        if any(l.get('label') not in allowed for l in labels):
            raise ValueError('unknown adjudicated claim label')
        assessed+=1;success+=overall=='supported_and_complete'
        factual=0
        for label in labels:
            counts[label['label']]+=1
            factual+=label['label'] in {'supported','unsupported','contradicted','unverifiable'}
            if label['label'] in {'supported','unsupported','contradicted','unverifiable'}:
                citation_counts[label.get('citation_label','not_recorded')]+=1
        no_claims+=factual==0
    denominator=sum(counts[k] for k in ('supported','unsupported','contradicted','unverifiable'))
    from .metrics import fraction
    result={'origin':'human_agreement_or_named_adjudication','packets':len(rows),'assessed_packets':assessed,
            'pending_annotation_ids':pending,'claim_counts':dict(counts),'packets_without_factual_claims':no_claims,
            'human_citation_labels':dict(citation_counts),
            'human_claim_support_conditional':fraction(counts['supported'],denominator),
            'human_report_success_assessed':fraction(success,assessed),
            'final_reporting_ready':not pending and bool(rows),
            'scope':'No-claim packets have no factual-claim precision; structural unassessability counts as report failure. Supplementary automated labels are excluded.'}
    write_new(output,result)
    return result


def dataset_summary(examples,output):
    """Composition counts use unique collected species; variants are separate."""
    records={e['species_id']:e['private_reference']['original_record'] for e in examples}
    splits={e['species_id']:e['split'] for e in examples}
    by_level={}
    for level in ('complete','partial','minimal'):
        selected=[e for e in examples if e['evidence_level']==level]
        by_level[level]={'examples':len(selected),'available_fields':{
            field:sum(e['payload']['fields'][field]['availability']=='available' for e in selected)
            for field in next(iter(records.values()))['fields']} if records else {}}
    result={'species':len(records),'genera':len({r['genus'] for r in records.values()}),
            'split_species_counts':dict(Counter(splits.values())),
            'families':dict(Counter(str(r['taxonomy'].get('family','unavailable')) for r in records.values())),
            'orders':dict(Counter(str(r['taxonomy'].get('order','unavailable')) for r in records.values())),
            'collected_availability':{field:dict(Counter(r['fields'][field]['availability'] for r in records.values()))
                                      for field in next(iter(records.values()))['fields']} if records else {},
            'by_level':by_level,
            'partial_equals_minimal_species':sum(
                {f:e['payload']['fields'][f]['value'] for f in e['payload']['fields']}==
                {f:None for f in e['payload']['fields']} for e in examples if e['evidence_level']=='partial'),
            'source_assertions':sum(len(r['sources']) for r in records.values()),
            'source_missing_retrieval_dates':sum(s['retrieved_at'] is None for r in records.values() for s in r['sources'])}
    write_new(output,result)
    return result
