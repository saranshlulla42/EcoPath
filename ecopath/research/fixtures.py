"""Explicitly synthetic, non-ecological values for offline plumbing checks."""
from .contract import FIELDS


def records(count=9):
    out=[]
    for i in range(count):
        fields={f:{'value':None,'availability':'missing','source_ids':[]} for f in FIELDS}
        sources=[]
        for j, field in enumerate(('diet','population_size','habitat')):
            value=f'FIXTURE_TOKEN_{i}_{j}'
            sid=f'fixture-{i}-{j}'
            fields[field]={'value':value,'availability':'available','source_ids':[sid]}
            sources.append({'source_id':sid,'record_id':sid,'url':f'https://example.invalid/{sid}',
                            'retrieved_at':'2026-10-20T00:00:00Z','excerpt':f'{field}={value}',
                            'field':field,'value':value,'license':'synthetic-fixture', 'extraction_review':'verified'})
        out.append({'species_id':f'synthetic:{i}','scientific_name':f'Syntheticgenus{i} fixture{i}',
                    'genus':f'Syntheticgenus{i}','taxonomy':{},'dataset_version':'synthetic-fixture-v1',
                    'sampling':{'country_code':None,'membership_review':'synthetic','frame_source_url':None},
                    'fields':fields,'sources':sources})
    return out


def template_config(phase='synthetic-fixture',split='pilot'):
    return {'phase':phase,'split':split,'group_genus':True,'model':None,
            'methods':[{'id':'template','method':'template','training_seed':None}],
            'generation':{'max_new_tokens':1400,'max_input_tokens':4096,'temperature':0.0,'seed':42},
            'demo_ids':[],'warmup_examples':0}
