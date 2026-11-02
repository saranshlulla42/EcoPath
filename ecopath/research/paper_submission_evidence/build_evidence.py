"""Re-score saved EcoPath outputs and export a traceable manuscript supplement.

This is a read-only audit of the frozen experiment. The post-hoc sensitivity
analysis changes only terminal-period normalization; it never changes the frozen
protocol, raw responses, or original scores.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.contract import REPORT_SCHEMA, digest, file_hash, normalize, read_jsonl
from research.dataset import validate_examples
import research.metrics as metrics
from research.runner import code_hashes, latest_attempts
from research.statistics import paired_bootstrap

DIR = ROOT/'research/paper_submission_evidence'
DATA = ROOT/'research/data_collection/soib2023-v1/reviewed-v4/all_variants.PRIVATE.jsonl'
RUN = ROOT/'research/artifacts/final-qwen-a09a354-v1/run.jsonl'
PROTOCOL = RUN.parent/'protocol.json'
METHODS = ('constrained', 'qlora-42')


def write_json(name, data):
    (DIR/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def write_csv(name, rows, columns):
    with (DIR/name).open('w', encoding='utf-8', newline='') as handle:
        out=csv.DictWriter(handle, fieldnames=columns)
        out.writeheader(); out.writerows(rows)


def normalized_terminal_period(value, field=''):
    if isinstance(value, str):
        value=value.rstrip().rstrip('.').rstrip()
    elif isinstance(value, list):
        value=[v.rstrip().rstrip('.').rstrip() if isinstance(v, str) else v for v in value]
    return normalize(value,field)


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    ex=read_jsonl(DATA);validate_examples(ex)
    examples={e['example_id']:e for e in ex}
    frozen=json.loads(PROTOCOL.read_text()); body={k:v for k,v in frozen.items() if k!='protocol_hash'}
    if digest(body)!=frozen['protocol_hash'] or file_hash(DATA)!=frozen['dataset_sha256']:
        raise ValueError('frozen protocol or dataset checksum mismatch')
    code=code_hashes()
    code_changed=[k for k,v in frozen['code_sha256'].items() if code.get(k)!=v]
    all_rows=list(latest_attempts(read_jsonl(RUN)).values())
    rows=[r for r in all_rows if r['method_id'] in METHODS]
    index={(r['method_id'],r['example_id']):r for r in rows}
    planned=set(frozen['planned_examples'])
    for m in METHODS:
        selected={eid for mid,eid in index if mid==m}
        if selected!=planned or len(selected)!=180:
            raise ValueError(f'{m} has an incomplete or different test set')
    comparisons=Counter()
    for eid in planned:
        a,b=(index[m,eid] for m in METHODS)
        for k in ('messages','generation','payload_sha256'):
            comparisons[k+'_equal']+=int(a[k]==b[k])
        comparisons['prompt_token_ids_equal']+=int(a['result']['prompt_token_ids']==b['result']['prompt_token_ids'])
        for row in (a,b):
            comparisons[f"{row['method_id']}_constraints_requested"]+=int(row['result']['constraints_requested'])
            comparisons[f"{row['method_id']}_constraint_backend"]+=int(row['result']['backend']['constraint_backend']=='lm-format-enforcer')
    mismatches=[]; rescored=[]
    for row in rows:
        new_score=metrics.score(examples[row['example_id']],row['result']['raw'],error=row['error'],truncated=row['result']['truncated'])
        if new_score!=row['score']:
            mismatches.append({'method':row['method_id'],'example_id':row['example_id']})
        rescored.append(dict(row, method=row['method_id'],score=new_score))
    if mismatches:
        raise ValueError(f'saved scores do not reproduce: {mismatches[:5]}')
    seeds={'constrained':[None],'qlora-42':[42]}
    test=[examples[eid] for eid in frozen['planned_examples']]
    strict=paired_bootstrap(rescored,test,*METHODS,'structured_field_success_e2e',seeds,2000,42)
    aggregates={m:metrics.aggregate([r['score'] for r in rescored if r['method_id']==m]) for m in METHODS}
    mismatched_fields=[]
    for row in rescored:
        if row['method_id']!='constrained' or not row['score']['assessable']:
            continue
        e=examples[row['example_id']]
        for field,target in e['expected']['fields'].items():
            if target['kind']!='source_reported': continue
            actual=row['score']['parsed']['fields'][field]
            target_value,actual_value=target['value'],actual['value']
            strict_equal=normalize(target_value,field)==normalize(actual_value,field)
            relaxed_equal=normalized_terminal_period(target_value,field)==normalized_terminal_period(actual_value,field)
            if not strict_equal:
                category='terminal_period_only' if relaxed_equal else 'other_value_difference'
                source_ids=target['source_ids']
                source=e['private_reference']['original_record']['sources']
                full_id=e['private_reference']['source_map'].get(source_ids[0]) if source_ids else None
                provenance=next((s for s in source if s['source_id']==full_id),{})
                other=index['qlora-42',row['example_id']]
                adapted=other['score']['parsed']['fields'][field] if other['score']['assessable'] else None
                mismatched_fields.append({'example_id':row['example_id'],'scientific_name':e['payload']['scientific_name'],
                    'variant':e['evidence_level'],'field':field,'category':category,
                    'expected_value':target_value,'baseline_value':actual_value,'expected_source_ids':source_ids,
                    'baseline_source_ids':actual['source_ids'],'baseline_kind':actual['kind'],
                    'adapted_value':adapted['value'] if adapted else None,
                    'adapted_source_ids':adapted['source_ids'] if adapted else [],
                    'source_record_id':provenance.get('record_id'),'source_url':provenance.get('url'),
                    'source_excerpt':provenance.get('excerpt')})
    write_json('baseline_mismatched_fields.json',mismatched_fields)
    breakdown=Counter(x['category'] for x in mismatched_fields)
    sensitivity_rows=[]
    metrics.normalize=normalized_terminal_period
    try:
        for row in rows:
            sc=metrics.score(examples[row['example_id']],row['result']['raw'],error=row['error'],truncated=row['result']['truncated'])
            sensitivity_rows.append(dict(row,method=row['method_id'],score=sc))
    finally:
        metrics.normalize=normalize
    relaxed=paired_bootstrap(sensitivity_rows,test,*METHODS,'structured_field_success_e2e',seeds,2000,42)
    relaxed_aggregates={m:metrics.aggregate([r['score'] for r in sensitivity_rows if r['method_id']==m]) for m in METHODS}
    sensitivity={'scope':'post-hoc sensitivity; strips terminal full stops before the existing case/whitespace/IUCN alias normalization; not an independent semantic correctness assessment',
                 'baseline_mismatch_breakdown':dict(breakdown),'strict':strict,'relaxed':relaxed,
                 'strict_aggregates':aggregates,'relaxed_aggregates':relaxed_aggregates}
    write_json('sensitivity_analysis.json',sensitivity)
    species=[]; fieldmasks=[]; seen={}
    for e in ex:
        seen[e['species_id']]=e
        fieldmasks.append({'species_id':e['species_id'],'scientific_name':e['payload']['scientific_name'],
            'split':e['split'],'variant':e['evidence_level'],'visible_fields':';'.join(sorted(k for k,v in e['payload']['fields'].items() if v['availability']=='available')),
            'initially_masked_fields':';'.join(e['mask']['initially_masked_fields']),
            'dependency_masked_fields':';'.join(e['mask']['dependency_masked_fields']), 'mask_seed':e['mask']['seed']})
    for sid,e in sorted(seen.items()):
        rec=e['private_reference']['original_record'];source=rec['sources'][0]
        species.append({'species_id':sid,'scientific_name':e['payload']['scientific_name'],'genus':e['genus'],
            'split':'development' if e['split']=='pilot' else e['split'],
            'source_record_id':source['record_id'],'source_url':source['url'],
            'selection_stratum':rec['sampling'].get('source_current_trend_stratum','')})
    write_csv('species_split_manifest.csv',species,list(species[0]))
    write_csv('variant_field_masks.csv',fieldmasks,list(fieldmasks[0]))
    selected=index['constrained','soib2023:Hemipus_picatus:complete']
    demonstration=frozen['config']['demo_ids']
    write_json('exact_messages_example.json',{'example_id':selected['example_id'],'method_id':selected['method_id'],
         'protocol_hash':frozen['protocol_hash'],'demonstration_ids':demonstration,'messages':selected['messages']})
    write_json('exact_json_schema.json',REPORT_SCHEMA)
    write_json('exact_prompt_token_ids.json',{'example_id':selected['example_id'],
         'token_ids':selected['result']['prompt_token_ids'],'tokenizer_revision':frozen['config']['model']['tokenizer_revision']})
    (DIR/'exact_chat_template.jinja').write_text(selected['result']['backend']['chat_template'])
    example=next(x for x in mismatched_fields if x['example_id']=='soib2023:Hemipus_picatus:complete' and x['field']=='diet')
    short=[x for x in mismatched_fields if x['category']=='other_value_difference']
    bad=next(r for r in rows if r['method_id']=='constrained' and not r['score']['assessable'])
    write_json('illustrative_examples.json',{'punctuation_example':example,'other_value_differences':short,
         'unassessable':{'example_id':bad['example_id'],'finish_reason':bad['result']['finish_reason'],
                         'truncated':bad['result']['truncated'],'parse_errors':bad['score']['errors'],
                         'output_tokens':bad['result']['output_tokens']}})
    runtime={}
    for method in METHODS:
        selected=[r for r in rows if r['method_id']==method]; wall=[r['result']['wall_seconds'] for r in selected]
        runtime[method]={'reports':len(selected),'mean_wall_seconds':statistics.mean(wall),
             'median_wall_seconds':statistics.median(wall),'total_wall_seconds':sum(wall),
             'load_seconds_recorded':selected[0]['result']['backend']['load_seconds'],
             'warmup_records_on_first_example':len(selected[0]['warmup_records']),
             'truncated':sum(r['result']['truncated'] for r in selected),
             'execution_errors':sum(bool(r['error']) for r in selected),
             'output_tokens_total':sum(r['result']['output_tokens'] for r in selected)}
    split_genera=defaultdict(set)
    for e in seen.values():split_genera[e['split']].add(e['genus'])
    overlaps={f'{a}/{b}':sorted(split_genera[a]&split_genera[b]) for a,b in [('pilot','validation'),('pilot','test'),('validation','test')]}
    summary={'created_utc':datetime.now(timezone.utc).isoformat(),'source_scope':'post-hoc audit of saved outputs; no new model inference',
        'dataset_sha256':file_hash(DATA),'run_sha256':file_hash(RUN),'protocol_canonical_body_sha256':digest(body),
        'protocol_file_byte_sha256':file_hash(PROTOCOL),'code_files_changed_since_freeze':code_changed,
        'methods':list(METHODS),'outputs_per_method':180,'species':len(seen),
        'species_per_split':dict(Counter(e['split'] for e in seen.values())),
        'genus_overlap':overlaps,'variant_availability':dict(Counter(f"{e['evidence_level']}:{sum(v['availability']=='available' for v in e['payload']['fields'].values())}" for e in ex)),
        'mask_seeds':dict(Counter(str(e['mask']['seed']) for e in ex)),
        'dependency_mask_counts':dict(Counter(str(len(e['mask']['dependency_masked_fields'])) for e in ex)),
        'prompt_comparisons':dict(comparisons),'saved_score_differences':mismatches,'mismatch_breakdown':dict(breakdown),
        'strict_primary':{k:strict[k] for k in ('estimate','ci95','eligible_species','draws','bootstrap_seed')},
        'relaxed_primary':{k:relaxed[k] for k in ('estimate','ci95','eligible_species','draws','bootstrap_seed')},
        'strict_metrics':{m:aggregates[m]['micro'] for m in METHODS},
        'relaxed_metrics':{m:relaxed_aggregates[m]['micro'] for m in METHODS},'runtime':runtime}
    write_json('audit_summary.json',summary)
    print(json.dumps({k:summary[k] for k in ('protocol_canonical_body_sha256','protocol_file_byte_sha256',
         'code_files_changed_since_freeze','species_per_split','genus_overlap','variant_availability','prompt_comparisons',
         'mismatch_breakdown','strict_primary','relaxed_primary','runtime')},indent=2))


if __name__=='__main__':main()
