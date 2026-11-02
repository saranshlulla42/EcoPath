"""Read-only audit of saved legacy records. Never load pickle or call a judge."""
from __future__ import annotations

import ast
import collections
import csv
import json
from pathlib import Path
import pickletools
import re
import random
import zipfile

from .contract import FIELDS, canonical, digest, file_hash, read_jsonl, write_jsonl_new, write_new

REPO = Path(__file__).resolve().parents[2]
LEGACY = REPO / 'ecopath_afterJudge-20260902T160124Z-1-001/ecopath_afterJudge'
RUN = LEGACY / 'extinction_risk/ecopath_gemini100_run1'


def scalar_training_args(path):
    """Extract only direct scalar pickle opcodes; never execute unpickling code."""
    with zipfile.ZipFile(path) as archive:
        member = next(n for n in archive.namelist() if n.endswith('/data.pkl'))
        ops = list(pickletools.genops(archive.read(member)))
    values = {}
    scalar = {'BININT','BININT1','BININT2','BINFLOAT','BINUNICODE','SHORT_BINUNICODE','NONE','NEWTRUE','NEWFALSE'}
    for i, (op, key, _) in enumerate(ops):
        if op.name not in {'BINUNICODE','SHORT_BINUNICODE'} or not isinstance(key,str):
            continue
        j = i+1
        while j < len(ops) and ops[j][0].name in {'BINPUT','LONG_BINPUT','MEMOIZE'}:
            j += 1
        if j < len(ops) and ops[j][0].name in scalar:
            operation, value, _ = ops[j]
            values[key] = True if operation.name == 'NEWTRUE' else False if operation.name == 'NEWFALSE' else value
    keys = ['per_device_train_batch_size','gradient_accumulation_steps','num_train_epochs','learning_rate',
            'seed','data_seed','bf16','fp16','gradient_checkpointing','save_steps','logging_steps',
            'load_best_model_at_end','max_steps','warmup_steps','warmup_ratio','weight_decay','optim']
    return {'extraction':'static pickle opcode inspection, no deserialization',
            'scalars':{k:values.get(k,'unavailable_as_direct_scalar') for k in keys}}


def legacy_grader():
    tree = ast.parse((LEGACY/'scripts/grade_results.py').read_text())
    selected = [node for node in tree.body if
                isinstance(node, ast.FunctionDef) and node.name in {'is_valid_json','check_schema'}]
    namespace = {'json':json,'re':re,'Any':object,
                 'REQUIRED_KEYS':{'decision_support_draft':{'species','current_conservation_status','key_threats',
                                                          'survivability_assessment','mitigation_actions','sources'}}}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<legacy metric functions>','exec'),namespace)
    return namespace


def extract(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    data = read_jsonl(LEGACY/'data/extinction_risk_dataset_gemini_100.jsonl')
    train, test = (read_jsonl(RUN/f'splits/{s}.jsonl') for s in ['train','eval'])
    split_map = {r['input']['species']['scientific_name']:s for s, rows in [('train',train),('legacy_eval',test)] for r in rows}
    grader = legacy_grader()
    results = read_jsonl(RUN/'eval_results.jsonl')
    scored = []
    for r in results:
        for method,key in [('base','base_model_output'),('adapted','ft_model_output')]:
            raw = r.get(key)
            ok, parsed = grader['is_valid_json'](raw)
            try:
                json.loads(raw)
                strict = True
            except (TypeError,ValueError):
                strict = False
            scored.append({'idx':r['idx'],'scientific_name':r['scientific_name'],'method':method,
                           'strict_json_valid':strict,'legacy_relaxed_json_valid':ok,
                           'legacy_required_keys_present':grader['check_schema'](parsed)[0] if ok else False,
                           'characters':len(raw or ''),'starts_with':(raw or '')[:100],
                           'raw_source':str((RUN/'eval_results.jsonl').relative_to(REPO)),
                           'truncation':'unavailable: token IDs, finish reason and effective run arguments not recorded'})
    fields = list(data[0]['input']['species'])
    availability = {field:sum(bool(r['input']['species'].get(field)) for r in data) for field in fields}
    train_names = {r['input']['species']['scientific_name'] for r in train}
    test_names = {r['input']['species']['scientific_name'] for r in test}
    genera_overlap = sorted({n.split()[0] for n in train_names} & {n.split()[0] for n in test_names})
    species = []
    diagnostic_records = []
    for r in data:
        s = r['input']['species']
        species.append({'species_id':f"gbif:{s['gbif_key']}", 'scientific_name':s['scientific_name'],
                        'common_name':s['common_name'],'genus':s['scientific_name'].split()[0],
                        'family':s['family'],'order':s['order_name'],'split':split_map.get(s['scientific_name'],'unassigned'),
                        'created_at':r.get('metadata',{}).get('created_at'),
                        'evidence_source_count':len(r.get('search_results',[])),
                        'source_urls':[x.get('url') for x in r.get('search_results',[])],
                        'retrieval_dates':[x.get('seendate') for x in r.get('search_results',[])],
                        'input_sha256':digest(r['input']),'target_sha256':digest(r.get('output')),
                        'ecological_fields_available':sum(bool(s.get(f)) for f in FIELDS)})
        # No ecological values are manufactured from taxonomy or teacher output.
        diagnostic_records.append({'species_id':f"gbif:{s['gbif_key']}",'scientific_name':s['scientific_name'],
            'genus':s['scientific_name'].split()[0], 'taxonomy':{'family':s['family'],'order':s['order_name']},
            'dataset_version':'legacy-taxonomy-diagnostic-v1',
            'sampling':{'country_code':None,'membership_review':'unavailable','frame_source_url':None,
                        'selection':'original species selection procedure unavailable'},
            'fields':{f:{'value':None,'availability':'missing','source_ids':[]} for f in FIELDS},'sources':[]})
    args = scalar_training_args(REPO/'ecopath/final/training_args.bin')
    adapter = json.loads((REPO/'ecopath/final/adapter_config.json').read_text())
    saved_args = scalar_training_args(RUN/'final/training_args.bin')
    state = json.loads((RUN/'checkpoints/checkpoint-33/trainer_state.json').read_text())
    summary = {'phase':'original-record-audit','new_model_inference_executed':False,
        'dataset_records':len(data),'unique_species':len({s['scientific_name'] for s in species}),
        'availability':availability,'sources':dict(collections.Counter(s.get('source') for r in data for s in r.get('search_results',[]))),
        'training_records':len(train),'legacy_eval_records':len(test),'species_overlap':sorted(train_names & test_names),
        'genus_overlap':genera_overlap,'families':dict(collections.Counter(s['family'] for s in species)),
        'orders':dict(collections.Counter(s['order'] for s in species)),
        'teacher_metadata_keys':sorted({k for r in data for k in r.get('metadata',{})}),
        'teacher_identifier':'unavailable; filename suggests Gemini, not an exact model record',
        'judge_script_default':'gemini-3.6-flash; actual executed judge identity/settings not saved per score',
        'judge_context_limit':'score_row passes first 600 characters of prompt_user; actual SEARCH RESULTS generally omitted',
        'local_adapter':adapter,'training_args_local':args,'training_args_archived':saved_args,
        'training_state':state,
        'unavailable':['teacher prompt/model/settings/retries and processing code','species sampling frame and exclusions',
                       'source retrieval timestamps','base/tokenizer immutable training revision',
                       'original training hardware/software environment, wall time and peak memory',
                       'effective evaluation CLI configuration, token counts, finish reasons, latencies and random seed',
                       'human annotations and adjudication','validation-set checkpoint selection records'],
        'legacy_metrics':{method:{'n':sum(s['method']==method for s in scored),
            'strict_json_valid':sum(s['strict_json_valid'] for s in scored if s['method']==method),
            'legacy_relaxed_json_valid':sum(s['legacy_relaxed_json_valid'] for s in scored if s['method']==method),
            'required_keys_present':sum(s['legacy_required_keys_present'] for s in scored if s['method']==method)} for method in ['base','adapted']},
        'artifact_equality':{'local_vs_archive_adapter_sha256_equal':file_hash(REPO/'ecopath/final/adapter_model.safetensors') == file_hash(RUN/'final/adapter_model.safetensors')},
        'evidence_warning':'Teacher targets contain heuristic risk-language absent from taxonomy-only input. Targets are not verified ecological reference answers.'}
    write_new(output/'audit.json',summary)
    write_jsonl_new(output/'species_inventory.jsonl',species)
    write_jsonl_new(output/'legacy_structure_recomputed.jsonl',scored)
    write_jsonl_new(output/'legacy_diagnostic_records.jsonl',diagnostic_records)
    with (output/'availability.csv').open('x') as handle:
        writer = csv.writer(handle); writer.writerow(['field','available_records','total_records'])
        writer.writerows((k,v,len(data)) for k,v in availability.items())
    return summary


def legacy_annotations(output,seed):
    rows=read_jsonl(RUN/'eval_results.jsonl')
    packets=[];keys=[]
    for row in rows:
        for method,field in [('base','base_model_output'),('adapted','ft_model_output')]:
            aid=digest([seed,row['idx'],method,row[field]])[:24]
            packets.append({'annotation_id':aid,'phase':'original','scientific_name':row['scientific_name'],
                            'evidence_and_instruction_as_supplied':row['prompt_user'],'raw_response':row[field],
                            'label_origin':'human_pending','reviewer_id':None,'labels':[],
                            'overall_evidence_use':None,'adjudication':None})
            keys.append({'annotation_id':aid,'method':method,'idx':row['idx'],
                         'raw_source':str((RUN/'eval_results.jsonl').relative_to(REPO))})
    random.Random(seed).shuffle(packets)
    write_jsonl_new(Path(output)/'blind_review.jsonl',packets)
    write_jsonl_new(Path(output)/'PRIVATE_blinding_key.jsonl',keys)
    return len(packets)
