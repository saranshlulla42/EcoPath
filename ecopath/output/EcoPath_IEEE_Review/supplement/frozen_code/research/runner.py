"""Frozen, resumable local inference. No network or external retrieval paths."""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import time

from .contract import REPORT_SCHEMA, canonical, digest, file_hash, read_jsonl, template, write_new
from .dataset import validate_examples
from .metrics import score
from .prompts import messages_for

METHODS = {'template','original','engineered','constrained','qlora','qlora_unconstrained'}


def environment():
    versions = {}
    for name in ('torch','transformers','peft','bitsandbytes','accelerate','jsonschema','lm-format-enforcer','datasets','matplotlib','pytest'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'python':platform.python_version(), 'platform':platform.platform(), 'packages':versions,
            'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}


def code_hashes():
    root = Path(__file__).parent.parent
    files = list((root/'research').glob('*.py')) + [root/'backend/evidence_contract.py', root/'backend/evidence_prompts.py']
    return {str(p.relative_to(root)):file_hash(p) for p in sorted(files)}


def code_snapshot():
    root=Path(__file__).parent.parent
    return {name:(root/name).read_text() for name in code_hashes()}


def validate_config(config, examples):
    if config['phase'] not in {'synthetic-fixture','legacy-diagnostic','pilot','final'}:
        raise ValueError('explicit experiment phase required')
    methods = config['methods']
    ids = [m['id'] for m in methods]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError('duplicate/empty method IDs')
    if len({(m['method'],m.get('training_seed')) for m in methods}) != len(methods):
        raise ValueError('duplicate method/training-seed condition')
    for m in methods:
        if m['method'] not in METHODS:
            raise ValueError('unknown method')
        if m['method'].startswith('qlora'):
            if not m.get('adapter_dir') or not isinstance(m.get('training_seed'),int):
                raise ValueError('QLoRA requires an adapter and recorded training seed')
        elif m.get('training_seed') is not None:
            raise ValueError('non-adapted methods must have training_seed=null')
    if any(m['method'] != 'template' for m in methods):
        if not re.fullmatch(r'[0-9a-f]{40}', config['model'].get('revision') or ''):
            raise ValueError('pin base/tokenizer to a 40-character commit revision')
        if config['model'].get('tokenizer_revision') != config['model']['revision']:
            raise ValueError('primary models and tokenizer must use identical pinned revision')
    generation = config['generation']
    if generation['max_new_tokens'] < 1 or generation['max_input_tokens'] < 1:
        raise ValueError('invalid token budgets')
    if generation['temperature'] < 0 or config['warmup_examples'] < 0:
        raise ValueError('invalid decoding/warmup configuration')
    selected = [e for e in examples if e['split'] == config['split']]
    if not selected:
        raise ValueError('selected split is empty')
    if config['phase'] == 'final' and config['split'] != 'test':
        raise ValueError('final experiment requires test split')
    if config['phase'] != 'final' and config['split'] == 'test':
        raise ValueError('test outcomes require a final frozen protocol')
    if config['phase'] in {'pilot','final'}:
        for e in examples:
            r = e['private_reference']['original_record']
            if r['dataset_version'].startswith(('synthetic','legacy')):
                raise ValueError('diagnostic/fixture data cannot be promoted to pilot/final')
            if r['sampling'].get('country_code') != 'IN' or r['sampling'].get('membership_review') != 'verified':
                raise ValueError('unverified India sampling frame')
            if not any(f['availability']=='available' for f in r['fields'].values()):
                raise ValueError('no collected ecological evidence; report coverage instead of running pilot/final')
            for source in r['sources']:
                if not source['retrieved_at'] or source['extraction_review'] != 'verified' or source['license'] == 'unavailable':
                    raise ValueError('pilot/final sources require dated, licensed, reviewed extractions')
    example_map = {e['example_id']: e for e in examples}
    if config['phase'] in {'pilot','final'} and any(m['method'] in {'engineered','constrained','qlora'} for m in methods) and not config.get('demo_ids'):
        raise ValueError('engineered primary conditions require frozen validation-set demonstration IDs')
    for eid in config.get('demo_ids',[]):
        if eid not in example_map or example_map[eid]['split'] != 'validation':
            raise ValueError('few-shot examples must be validation examples')
        if any(e['species_id'] == example_map[eid]['species_id'] for e in selected):
            raise ValueError('demonstration overlaps evaluation species')
    return config


def adapter_fingerprints(config):
    result = {}
    for m in config['methods']:
        if m['method'].startswith('qlora'):
            directory = Path(m['adapter_dir'])
            ac = json.loads((directory/'adapter_config.json').read_text())
            if ac.get('base_model_name_or_path') != config['model']['id'] or ac.get('peft_type') != 'LORA':
                raise ValueError('adapter/base configuration mismatch')
            files = [directory/'adapter_config.json', directory/'adapter_model.safetensors']
            provenance_path=directory/'adapter_provenance.json'
            if config['phase'] in {'pilot','final'} and m['method']=='qlora':
                provenance=json.loads(provenance_path.read_text())
                if provenance['base_revision']!=config['model']['revision'] or provenance['training_seed']!=m['training_seed']:
                    raise ValueError('adapter provenance disagrees with frozen base revision/seed')
                files.append(provenance_path)
            result[m['id']] = {str(p.resolve()):file_hash(p) for p in files}
    return result


def freeze(config_path, dataset_path, output):
    config = json.loads(Path(config_path).read_text())
    examples = validate_examples(read_jsonl(dataset_path), group_genus=config.get('group_genus',True))
    validate_config(config,examples)
    for method in config['methods']:
        if method['method']=='qlora' and config['phase'] in {'pilot','final'}:
            provenance=json.loads((Path(method['adapter_dir'])/'adapter_provenance.json').read_text())
            selected=[e for e in examples if e['split']==config['split']]
            if {e['species_id'] for e in selected} & set(provenance['train_validation_species']):
                raise ValueError('adapter training/validation species overlap evaluation species')
            if config.get('group_genus',True) and {e['genus'] for e in selected} & set(provenance['train_validation_genera']):
                raise ValueError('adapter training/validation genus overlap evaluation genus')
    body = {'protocol_version':'ecopath-protocol-v2', 'config':config,
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'dataset_sha256':file_hash(dataset_path), 'code_sha256':code_hashes(),
            'code_snapshot':code_snapshot(),
            'schema_sha256':digest(REPORT_SCHEMA), 'adapters':adapter_fingerprints(config),
            'environment_at_freeze':environment(),
            'planned_examples':[e['example_id'] for e in examples if e['split'] == config['split']]}
    body['protocol_hash'] = digest(body)
    write_new(output,body)
    return body


def verify_protocol(protocol, dataset_path):
    body = {k:v for k,v in protocol.items() if k != 'protocol_hash'}
    if digest(body) != protocol['protocol_hash']:
        raise ValueError('protocol modified after freeze')
    if body['dataset_sha256'] != file_hash(dataset_path) or body['code_sha256'] != code_hashes() or body['schema_sha256'] != digest(REPORT_SCHEMA):
        raise ValueError('dataset, code or schema changed after freeze; create a new protocol')
    if body['adapters'] != adapter_fingerprints(body['config']):
        raise ValueError('adapter changed after freeze')
    if any(m['method']!='template' for m in body['config']['methods']):
        current=environment()
        frozen=body['environment_at_freeze']
        if current['python']!=frozen['python'] or current['packages']!=frozen['packages']:
            raise ValueError('Python/package environment changed after freeze; freeze on the prepared inference host')
    examples = validate_examples(read_jsonl(dataset_path),group_genus=body['config'].get('group_genus',True))
    validate_config(body['config'],examples)
    return examples


class HFBackend:
    """Optional GPU implementation; imports cannot affect credential-free tests."""
    def __init__(self, config, method):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
        self.torch = torch
        self.config = config
        self.method = method
        set_seed(config['generation']['seed'])
        mc = config['model']
        kwargs = dict(revision=mc['revision'], local_files_only=True, trust_remote_code=False)
        self.tokenizer = AutoTokenizer.from_pretrained(mc['id'], **kwargs)
        if not self.tokenizer.chat_template:
            raise ValueError('model tokenizer has no chat template')
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        dtype = getattr(torch, mc['compute_dtype'])
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype) if mc['load_in_4bit'] else None
        start = time.perf_counter()
        self.model = AutoModelForCausalLM.from_pretrained(mc['id'], **kwargs, device_map=mc['device_map'],
                                                        torch_dtype=dtype, quantization_config=quant)
        if method['method'].startswith('qlora'):
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, method['adapter_dir'], is_trainable=False, local_files_only=True)
        self.model.eval()
        self.load_seconds = time.perf_counter()-start
        self.constraint_data = None
        setup_start = time.perf_counter()
        if method['method'] in {'constrained','qlora'}:
            from .constraints import tokenizer_data
            self.constraint_data = tokenizer_data(self.tokenizer)
        constraint_setup_seconds = time.perf_counter()-setup_start
        self.metadata = {'load_seconds':self.load_seconds,'chat_template':self.tokenizer.chat_template,
                         'chat_template_sha256':digest(self.tokenizer.chat_template),
                         'hardware':[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
                         'batch_size':1, 'quantization':str(quant), 'environment':environment(),
                         'constraint_backend':'lm-format-enforcer' if method['method'] in {'constrained','qlora'} else None}
        self.metadata['constraint_setup_seconds'] = constraint_setup_seconds

    def generate(self, messages):
        torch = self.torch
        generation = self.config['generation']
        # One templating/tokenization step: never duplicate special tokens.
        inputs = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                    return_tensors='pt', return_dict=True).to(self.model.device)
        length = inputs['input_ids'].shape[1]
        if length > generation['max_input_tokens']:
            raise ValueError('prompt exceeds frozen input budget; evidence must not be truncated')
        limit = getattr(self.model.config,'max_position_embeddings',None)
        if limit and length + generation['max_new_tokens'] > limit:
            raise ValueError('input plus output budget exceeds model context')
        kwargs = dict(max_new_tokens=generation['max_new_tokens'], do_sample=generation['temperature'] > 0,
                      pad_token_id=self.tokenizer.pad_token_id, eos_token_id=self.tokenizer.eos_token_id,
                      num_beams=1, use_cache=True)
        if generation['temperature'] > 0:
            kwargs['temperature'] = generation['temperature']
        if self.method['method'] in {'constrained','qlora'}:
            from .constraints import prefix_allowed_tokens
            kwargs['prefix_allowed_tokens_fn'] = prefix_allowed_tokens(self.tokenizer,REPORT_SCHEMA,self.constraint_data)
        torch.manual_seed(generation['seed'])
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(generation['seed'])
            torch.cuda.synchronize()
            for i in range(torch.cuda.device_count()):
                torch.cuda.reset_peak_memory_stats(i)
        start = time.perf_counter()
        with torch.inference_mode():
            output = self.model.generate(**inputs, **kwargs)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = time.perf_counter()-start
        generated = output[0][length:]
        token_ids = generated.tolist()
        eos = self.tokenizer.eos_token_id
        eos_ids = eos if isinstance(eos,list) else [eos]
        truncated = len(token_ids) >= generation['max_new_tokens'] and (not token_ids or token_ids[-1] not in eos_ids)
        return {'raw':self.tokenizer.decode(generated,skip_special_tokens=True),
                'raw_with_special_tokens':self.tokenizer.decode(generated,skip_special_tokens=False),
                'input_tokens':length,'output_tokens':len(token_ids),'output_token_ids':token_ids,
                'prompt_token_ids':inputs['input_ids'][0].tolist(), 'generation_seconds':elapsed,
                'truncated':truncated, 'finish_reason':'length' if truncated else 'eos_or_generation_stop',
                'peak_memory_bytes':{str(i):{'allocated':torch.cuda.max_memory_allocated(i),'reserved':torch.cuda.max_memory_reserved(i)}
                                     for i in range(torch.cuda.device_count())},
                'memory_scope':'per-call peak device allocation including resident weights; excludes model load peak',
                'backend':self.metadata, 'constraints_requested':self.method['method'] in {'constrained','qlora'}}

    def close(self):
        del self.model
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()


def latest_attempts(rows):
    selected = {}
    for row in rows:
        key = (row['method_id'],row['example_id'])
        previous = selected.get(key)
        if previous and row['attempt'] != previous['attempt']+1:
            raise ValueError('duplicate or nonsequential attempt')
        if not previous and row['attempt'] != 1:
            raise ValueError('first attempt must be 1')
        selected[key] = row
    return selected


def run(protocol_path, dataset_path, output, execute_models=False, retry_errors=False,
        backend_factory=HFBackend, method_ids=None):
    protocol = json.loads(Path(protocol_path).read_text())
    examples = verify_protocol(protocol,dataset_path)
    config = protocol['config']
    if any(m['method'] != 'template' for m in config['methods']) and not execute_models:
        raise ValueError('model execution requires --execute-models; only cached local weights are loaded')
    configured_ids = {m['id'] for m in config['methods']}
    if method_ids is not None:
        if not method_ids or len(set(method_ids)) != len(method_ids) or not set(method_ids) <= configured_ids:
            raise ValueError('method filter must name unique IDs from the frozen protocol')
        selected_methods = [m for m in config['methods'] if m['id'] in set(method_ids)]
    else:
        selected_methods = config['methods']
    selected = [e for e in examples if e['split'] == config['split']]
    by_id = {e['example_id']:e for e in examples}
    demos = [by_id[eid] for eid in config.get('demo_ids',[])]
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Hold a process lock over read + inference + append, preventing duplicate work.
    with output.with_suffix(output.suffix+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        metadata_path = output.with_suffix(output.suffix+'.manifest.json')
        metadata = {'protocol_hash':protocol['protocol_hash'],'dataset_sha256':protocol['dataset_sha256'],
                    'environment':environment(), 'phase':config['phase'],'warmup_examples':config['warmup_examples'],
                    'planned_examples':protocol['planned_examples'],'methods':config['methods']}
        if metadata_path.exists():
            saved_metadata=json.loads(metadata_path.read_text())
            if {k:v for k,v in saved_metadata.items() if k!='created_at_utc'} != metadata:
                raise ValueError('run metadata/environment changed; use a new output path')
        else:
            if output.exists() and output.stat().st_size:
                raise ValueError('existing results lack manifest')
            write_new(metadata_path,dict(metadata,created_at_utc=datetime.now(timezone.utc).isoformat()))
        rows = read_jsonl(output) if output.exists() else []
        if any(r['protocol_hash'] != protocol['protocol_hash'] for r in rows):
            raise ValueError('mixed protocols')
        latest = latest_attempts(rows)
        for method in selected_methods:
            pending = [e for e in selected if (method['id'],e['example_id']) not in latest or
                       (retry_errors and latest[(method['id'],e['example_id'])].get('error'))]
            if not pending:
                continue
            backend = None
            load_error = None
            warmups = []
            try:
                if method['method'] != 'template':
                    backend = backend_factory(config,method)
                    for _ in range(config['warmup_examples']):
                        warmups.append(backend.generate(messages_for(pending[0]['payload'],method['method'],demos)))
            except Exception as exc:
                load_error = f'{type(exc).__name__}: {exc}'
            try:
                with output.open('a',encoding='utf-8') as handle:
                    for e in pending:
                        previous = latest.get((method['id'],e['example_id']))
                        result = {'raw':'','truncated':False}
                        error = load_error
                        messages = [] if method['method'] == 'template' else messages_for(e['payload'],method['method'],demos)
                        wall_start = time.perf_counter()
                        started_at=datetime.now(timezone.utc).isoformat()
                        if not error:
                            try:
                                if method['method'] == 'template':
                                    result = {'raw':canonical(template(e['payload'])),'truncated':False,
                                              'input_tokens':None,'output_tokens':None,
                                              'finish_reason':'deterministic','backend':{'name':'deterministic-copy'},
                                              'constraints_requested':False}
                                else:
                                    result = backend.generate(messages)
                            except Exception as exc:
                                error = f'{type(exc).__name__}: {exc}'
                        result['wall_seconds'] = time.perf_counter()-wall_start
                        row = {'protocol_hash':protocol['protocol_hash'],'phase':config['phase'],
                               'method_id':method['id'],'method':method['method'],'training_seed':method.get('training_seed'),
                               'example_id':e['example_id'],'species_id':e['species_id'], 'evidence_level':e['evidence_level'],
                               'payload_sha256':digest(e['payload']),'messages':messages,'generation':config['generation'],
                               'attempt':previous['attempt']+1 if previous else 1,'error':error, 'result':result,
                               'started_at_utc':started_at,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
                               'warmup_records':warmups if e is pending[0] else [],
                               'score':score(e,result['raw'],error=error,truncated=result['truncated'])}
                        handle.write(canonical(row)+'\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                        latest[(method['id'],e['example_id'])] = row
            finally:
                if backend:
                    backend.close()
    return list(latest.values())
