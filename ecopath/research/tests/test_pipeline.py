import copy
import json
import os
from pathlib import Path

import pytest

from research.contract import (FIELDS, canonical, digest, read_jsonl, report_errors, strict_json,
                               template, validate_payload, validate_record, write_jsonl_new, write_new)
from research.dataset import assign_splits, build_dataset, make_variant, select_pilot, validate_examples
from research.fixtures import records, template_config
from research.metrics import aggregate, score
from research.prompts import messages_for
from research.reporting import annotation_export, annotation_summary, adjudicate
from research.runner import freeze, latest_attempts, run, verify_protocol
from research.statistics import paired_bootstrap
from research.train import encode_example


@pytest.fixture
def example():
    return make_variant(records(1)[0],'complete','pilot',42,.5)


def test_schema_provenance_and_projection(example):
    assert validate_record(example['private_reference']['original_record'])
    assert not report_errors(example['expected'],example['payload'])
    assert validate_payload(example['payload'])
    assert example['private_reference']['provenance'][0]['retrieved_at']
    assert 'example.invalid' not in canonical(example['payload'])


def test_masking_and_targets_are_reproducible_and_no_hidden_values(example):
    record=example['private_reference']['original_record']
    record['sources'][0]['excerpt']='FIXTURE_TOKEN_0_0 plus FIXTURE_TOKEN_0_1: deliberately mixed raw excerpt'
    a=make_variant(record,'partial','pilot',42,.5)
    assert a==make_variant(record,'partial','pilot',42,.5)
    for field in a['mask']['withheld_fields']:
        secret=record['fields'][field]['value']
        assert secret not in canonical(a['payload'])
        assert secret not in canonical(a['expected'])
    minimal=make_variant(record,'minimal','pilot',42,.5)
    assert minimal['payload']['sources']==[]
    assert all(e['value'] is None for e in minimal['expected']['fields'].values())


def test_value_echo_dependencies_are_masked(example):
    record=copy.deepcopy(example['private_reference']['original_record'])
    # Equal fixture values in different fields must not expose a withheld cell.
    for field in ('diet','habitat','population_size'):
        record['fields'][field]['value']='SHARED_FIXTURE_TOKEN'
    for source in record['sources']:source['value']='SHARED_FIXTURE_TOKEN'
    e=make_variant(record,'partial','pilot',42,.5)
    assert len(e['mask']['withheld_fields'])==3
    assert 'SHARED_FIXTURE_TOKEN' not in canonical(e['payload'])


def test_split_species_and_genus_and_pilot_exclusion():
    rows=records(12)
    rows[1]['genus']=rows[0]['genus']; rows[1]['scientific_name']=rows[0]['genus']+' fixture_other'
    a=assign_splits(rows,42,.2,.2,True,[rows[0]['species_id']])
    assert a==assign_splits(rows,42,.2,.2,True,[rows[0]['species_id']])
    assert a[rows[0]['species_id']]==a[rows[1]['species_id']]=='pilot'
    ex=build_dataset(rows,a,42,.5)
    assert validate_examples(ex)
    assert all(e['split']!='test' for e in ex if e['genus']==rows[0]['genus'])


@pytest.mark.parametrize('mutation',[
    lambda r:r['fields'].pop('diet'),
    lambda r:r['sources'].append(copy.deepcopy(r['sources'][0])),
    lambda r:r['sources'][0].update(value='DIFFERENT_FIXTURE'),
    lambda r:r['fields']['diet'].update(source_ids=['missing']),
    lambda r:r['fields']['diet'].update(value=True),
    lambda r:r['sources'][0].update(retrieved_at='bad-date'),
    lambda r:r.update(unapproved_notes='hidden'),
])
def test_malformed_conflicting_duplicate_records_rejected(mutation):
    row=records(1)[0]; mutation(row)
    with pytest.raises((ValueError,TypeError)):
        validate_record(row)


def test_conflicts_abstain_without_resolving_by_guess():
    row=records(1)[0]
    other=dict(row['sources'][0],source_id='conflict',value='CONFLICT_FIXTURE')
    row['sources'].append(other)
    row['fields']['diet']={'value':None,'availability':'conflicting','source_ids':[row['sources'][0]['source_id'],'conflict']}
    validate_record(row)
    assert make_variant(row,'complete','pilot',42,.5)['expected']['fields']['diet']['kind']=='unavailable'


def test_duplicate_species_rejected():
    rows=records(9); rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError,match='duplicate'):
        assign_splits(rows,42,.2,.2)


def test_tampered_examples_and_genus_leakage_rejected():
    rows=records(9); a=assign_splits(rows,42,.2,.2)
    ex=build_dataset(rows,a,42,.5)
    ex[0]['payload']['fields']['diet']['value']='HIDDEN_INJECTION'
    with pytest.raises(ValueError,match='projection'):
        validate_examples(ex)
    ex=build_dataset(rows,a,42,.5)
    ex[0]['split']='test' if ex[0]['split']!='test' else 'train'
    with pytest.raises(ValueError): validate_examples(ex)


def test_pilot_does_not_infer_india_membership_or_ecological_data():
    rows=records(9)
    assert select_pilot(rows,30,42)['status']=='insufficient_coverage'
    for r in rows:
        r['sampling']={'country_code':'IN','membership_review':'verified','frame_source_url':'https://example.invalid/frame'}
    assert len(select_pilot(rows,5,42)['selected_ids'])==5


def test_supported_value_and_abstention_metrics(example):
    s=score(example,canonical(example['expected']))
    assert s['metrics']['available_reporting_e2e']['value']==1
    assert s['metrics']['correct_abstention_e2e']['value']==1
    assert s['metrics']['structured_field_success_e2e']['numerator']==len(FIELDS)
    assert s['metrics']['false_abstention_assessable']['value']==0


def test_false_abstention_and_wrong_value_are_errors(example):
    report=copy.deepcopy(example['expected'])
    report['fields']['diet']={'value':None,'kind':'unavailable','source_ids':[]}
    s=score(example,canonical(report))
    assert s['metrics']['false_abstention_assessable']['numerator']==1
    assert s['metrics']['available_reporting_e2e']['numerator']==2
    report=copy.deepcopy(example['expected'])
    report['fields']['diet']['value']='WRONG_FIXTURE'
    s=score(example,canonical(report))
    assert s['metrics']['unsupported_structured_claims']['numerator']==1


def test_existing_citation_without_support_is_not_grounded(example):
    report=copy.deepcopy(example['expected'])
    report['fields']['diet']['source_ids']=report['fields']['habitat']['source_ids']
    s=score(example,canonical(report))
    assert s['metrics']['citation_validity']['value']==1
    assert s['metrics']['citation_structured_support']['value']<1
    assert s['metrics']['structured_field_success_e2e']['value']<1


def test_real_world_or_hidden_correctness_is_not_supplied_support(example):
    hidden=make_variant(example['private_reference']['original_record'],'minimal','pilot',42,.5)
    report=copy.deepcopy(hidden['expected'])
    report['fields']['diet']=copy.deepcopy(example['expected']['fields']['diet'])
    s=score(hidden,canonical(report))
    assert s['metrics']['unsupported_structured_claims']['numerator']==1
    assert s['metrics']['correct_abstention_e2e']['numerator']==len(FIELDS)-1


@pytest.mark.parametrize('raw',['','not-json','{}','[]','{"x":1,"x":2}','{"x":NaN}'])
def test_invalid_or_incomplete_outputs_are_end_to_end_failures(example,raw):
    s=score(example,raw)
    assert not s['assessable']
    assert s['metrics']['structured_field_success_e2e']['value']==0
    assert s['metrics']['structured_field_success_e2e']['denominator']==len(FIELDS)
    assert s['metrics']['false_abstention_assessable']['value'] is None


def test_truncation_and_empty_no_claim_not_perfect_evidence_use(example):
    s=score(example,canonical(example['expected']),truncated=True)
    assert s['metrics']['json_validity']['value']==1
    assert s['metrics']['structured_field_success_e2e']['value']==0
    minimal=make_variant(example['private_reference']['original_record'],'minimal','pilot',42,.5)
    s=score(minimal,canonical(minimal['expected']))
    assert s['metrics']['available_reporting_e2e']['value'] is None
    assert s['metrics']['citation_structured_support']['value'] is None


def test_prose_citation_existence_is_separate_from_semantic_support(example):
    r=copy.deepcopy(example['expected'])
    r['claims']=[{'text':'AN_UNVERIFIED_FIXTURE_SENTENCE','source_ids':r['fields']['diet']['source_ids']}]
    s=score(example,canonical(r))
    assert s['metrics']['prose_citation_validity']['value']==1
    assert s['prose_support']=='pending_human_review'


def test_schema_enforces_abstention_and_identity(example):
    r=copy.deepcopy(example['expected']); r['fields']['diet']['kind']='unavailable'
    assert report_errors(r,example['payload'])
    r=copy.deepcopy(example['expected']);r['scientific_name']='OTHER_FIXTURE'
    assert report_errors(r,example['payload'])


def test_prompt_equivalence_and_no_private_payload(example):
    prompts=[messages_for(example['payload'],m) for m in ('engineered','constrained','qlora')]
    assert prompts[0]==prompts[1]==prompts[2]
    assert all('private_reference' not in canonical(p) for p in prompts)
    with pytest.raises(ValueError): messages_for(example['payload'],'engineered',[example])


def prepared(tmp_path,config=None):
    rows=records(3)
    examples=build_dataset(rows,{r['species_id']:'pilot' for r in rows},42,.5)
    data=tmp_path/'examples.jsonl';write_jsonl_new(data,examples)
    cp=tmp_path/'config.json';write_new(cp,config or template_config())
    pp=tmp_path/'protocol.json';freeze(cp,data,pp)
    return data,pp,examples


def test_freeze_resume_no_duplicates_no_overwrite(tmp_path):
    data,protocol,ex=prepared(tmp_path)
    out=tmp_path/'run.jsonl'
    run(protocol,data,out)
    before=out.read_bytes()
    assert len(run(protocol,data,out))==len(ex)
    assert out.read_bytes()==before
    with pytest.raises(FileExistsError):freeze(tmp_path/'config.json',data,protocol)
    data.write_text(data.read_text()+'\n')
    with pytest.raises(ValueError,match='changed'):run(protocol,data,out)


def test_protocol_tampering_and_model_opt_in(tmp_path):
    config=template_config();config['model']={'id':'fixture-model','revision':'a'*40,'tokenizer_revision':'a'*40}
    config['methods']=[{'id':'engineered','method':'engineered','training_seed':None}]
    data,protocol,ex=prepared(tmp_path,config)
    with pytest.raises(ValueError,match='execute-models'):run(protocol,data,tmp_path/'r.jsonl')
    content=json.loads(protocol.read_text());content['config']['generation']['max_new_tokens']=1
    with pytest.raises(ValueError,match='modified'):verify_protocol(content,data)


def test_runtime_errors_saved_and_explicit_retry_appends(tmp_path):
    config=template_config();config['model']={'id':'fixture-model','revision':'a'*40,'tokenizer_revision':'a'*40}
    config['methods']=[{'id':'engineered','method':'engineered','training_seed':None}]
    data,protocol,ex=prepared(tmp_path,config)
    class Broken:
        def __init__(self,*a):raise RuntimeError('SYNTHETIC_LOAD_FAILURE')
    out=tmp_path/'r.jsonl'
    rows=run(protocol,data,out,True,backend_factory=Broken)
    assert all(r['error'] for r in rows)
    assert all(r['score']['metrics']['structured_field_success_e2e']['value']==0 for r in rows)
    run(protocol,data,out,True,backend_factory=Broken)
    assert len(read_jsonl(out))==len(ex)
    run(protocol,data,out,True,True,backend_factory=Broken)
    assert len(read_jsonl(out))==2*len(ex)
    assert all(r['attempt']==2 for r in latest_attempts(read_jsonl(out)).values())


def test_annotation_is_blind_and_separates_origins(tmp_path):
    data,protocol,ex=prepared(tmp_path)
    out=tmp_path/'r.jsonl';run(protocol,data,out)
    annotation_export(out,data,tmp_path/'ann',42)
    packets=read_jsonl(tmp_path/'ann/blind_review.jsonl')
    assert all('method_id' not in p and 'training_seed' not in p for p in packets)
    assert all(not p['reviewer_provenance'] for p in packets if not p['evidence']['sources'])
    reviews=[]
    for reviewer,origin in [('one','human'),('two','human'),('judge','llm_assisted')]:
        r=copy.deepcopy(packets[0]);r.update(reviewer_id=reviewer,label_origin=origin,labels=[]);reviews.append(r)
    paths=[]
    for i,r in enumerate(reviews):
        p=tmp_path/f'review{i}.jsonl';write_jsonl_new(p,[r]);paths.append(p)
    result=adjudicate(paths,tmp_path/'adjudication.jsonl')[0]
    assert len(result['human_reviews'])==2
    assert len(result['supplementary_reviews'])==1


def test_unreviewed_and_empty_claims_do_not_become_perfect_human_support(tmp_path):
    path=tmp_path/'adjudicated.jsonl'
    write_jsonl_new(path,[{'annotation_id':'a','status':'pending_adjudication','human_reviews':[]},
                          {'annotation_id':'b','status':'human_agreement','human_reviews':[
                              {'labels':[],'overall_evidence_use':'unassessable'},
                              {'labels':[],'overall_evidence_use':'unassessable'}]}])
    result=annotation_summary(path,tmp_path/'summary.json')
    assert result['human_claim_support_conditional']['value'] is None
    assert result['human_report_success_assessed']['value']==0
    assert not result['final_reporting_ready']


def test_species_cluster_bootstrap_preserves_variants_and_seeds():
    examples=[];scores=[]
    for i in range(4):
        for variant in ('complete','partial','minimal'):
            eid=f'{i}:{variant}'; examples.append({'example_id':eid,'species_id':str(i)})
            for method,seeds in [('base',[None]),('adapted',[42,43,44])]:
                for seed in seeds:
                    value=.1*i if method=='base' else .1*i+.2
                    scores.append({'example_id':eid,'species_id':str(i),'method':method,'training_seed':seed,
                                   'score':{'metrics':{'m':{'value':value}}}})
    kwargs=dict(examples=examples,method_a='base',method_b='adapted',metric='m',seeds={'base':[None],'adapted':[42,43,44]},draws=200,seed=42)
    result=paired_bootstrap(scores,**kwargs)
    assert result==paired_bootstrap(scores,**kwargs)
    assert result['eligible_species']==4
    assert result['estimate']==pytest.approx(.2)
    assert all(len(v)==3 for v in result['variants_by_species'].values())
    scores.pop()
    missing=paired_bootstrap(scores,**kwargs)
    assert missing['eligible_species']==3 and missing['excluded_species']==['3']


def test_bootstrap_zero_denominators_and_missing_methods():
    result=paired_bootstrap([], [{'species_id':'s','example_id':'x'}], 'a','b','m',{'a':[None],'b':[42]},10,42)
    assert result['ci95'] is None and result['eligible_species']==0


def test_assistant_only_training_and_reject_truncation(example):
    class FakeTokenizer:
        def apply_chat_template(self,messages,tokenize,add_generation_prompt,return_dict):
            base=[10,11,12]
            return base if add_generation_prompt else base+[99,100]
    encoded=encode_example(FakeTokenizer(),example,10)
    assert encoded['labels']==[-100,-100,-100,99,100]
    with pytest.raises(ValueError,match='budget'):encode_example(FakeTokenizer(),example,4)


@pytest.mark.skipif(os.environ.get('ECOPATH_CONSTRAINT_TESTS')!='1',reason='opt-in: requires lm-format-enforcer; no GPU required')
def test_actual_constraint_parser_rejects_invalid_schema(example):
    from lmformatenforcer import JsonSchemaParser
    from research.contract import REPORT_SCHEMA
    def accepts(text):
        parser=JsonSchemaParser(REPORT_SCHEMA)
        for char in text:
            if char not in parser.get_allowed_characters():return False
            parser=parser.add_character(char)
        return parser.can_end()
    assert accepts(canonical(example['expected']))
    assert not accepts('{}')
    wrong=copy.deepcopy(example['expected']);wrong['fields']['diet']['kind']='unavailable'
    assert not accepts(canonical(wrong))


@pytest.mark.skipif(os.environ.get('ECOPATH_CONSTRAINT_TESTS')!='1',reason='opt-in CPU tokenizer and token-constraint integration')
def test_actual_qwen_template_and_token_constraints(example):
    import torch
    from transformers import AutoTokenizer
    from lmformatenforcer import JsonSchemaParser
    from research.constraints import prefix_allowed_tokens
    from research.contract import REPORT_SCHEMA
    tokenizer=AutoTokenizer.from_pretrained(Path(__file__).parents[2]/'final',local_files_only=True)
    messages=messages_for(example['payload'],'constrained')
    text=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    prefix=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
    assert prefix==tokenizer(text,add_special_tokens=False)['input_ids']
    assert text.startswith('<|im_start|>system') and text.endswith('<|im_start|>assistant\n')
    assert '<|system|>' not in tokenizer.all_special_tokens
    callback=prefix_allowed_tokens(tokenizer,REPORT_SCHEMA)
    for token in tokenizer.encode(canonical(example['expected']),add_special_tokens=False):
        allowed=callback(0,torch.tensor(prefix))
        assert token in allowed
        prefix.append(token)
    assert tokenizer.eos_token_id in callback(0,torch.tensor(prefix))
