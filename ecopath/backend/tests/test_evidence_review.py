"""Network-free application checks for fixed-evidence drafts."""
import copy
import json
from types import SimpleNamespace

import pytest

from evidence_contract import FIELDS, VERSION, canonical, template
from services.evidence_review_service import EvidencePreviewRequest, preview


def payload():
    fields={f:{'value':None,'availability':'missing','source_ids':[]} for f in FIELDS}
    fields['diet']={'value':'FIXTURE_TOKEN_A','availability':'available','source_ids':['s1']}
    return {'schema_version':VERSION,'example_id':'fixture:complete','scientific_name':'Synthetic fixture',
            'fields':fields,'sources':[{'source_id':'s1','field':'diet','value':'FIXTURE_TOKEN_A',
                                       'excerpt':canonical({'diet':'FIXTURE_TOKEN_A'})}]}


@pytest.mark.asyncio
async def test_template_no_network_and_correct_missing_display(monkeypatch):
    async def forbidden(*a,**kw):raise AssertionError('network called')
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',forbidden)
    result=await preview(EvidencePreviewRequest(payload=payload()))
    assert result['validation_status']=='structured_valid'
    assert result['draft_for_review']
    assert 'diet' not in result['missing_fields']
    assert 'iucn_status' in result['missing_fields']
    assert result['report']['fields']['diet']['source_ids']==['s1']


@pytest.mark.asyncio
@pytest.mark.parametrize('raw',['bad-json','{}',None])
async def test_invalid_incomplete_or_unavailable_is_visible(monkeypatch,raw):
    async def fake(*a,**kw):return SimpleNamespace(ok=raw is not None,data=raw)
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',fake)
    result=await preview(EvidencePreviewRequest(payload=payload(),method='engineered'))
    assert result['report'] is None and result['validation_errors']


@pytest.mark.asyncio
async def test_schema_request_and_unsupported_value_rejection(monkeypatch):
    calls=[]
    async def fake(messages,**kwargs):
        calls.append((messages,kwargs))
        report=template(payload());report['fields']['diet']['value']='UNSUPPORTED_FIXTURE'
        return SimpleNamespace(ok=True,data=canonical(report))
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',fake)
    result=await preview(EvidencePreviewRequest(payload=payload(),method='constrained'))
    assert calls[0][1]['output_schema']['type']=='object'
    assert result['report'] is None
    assert 'unsupported' in result['validation_errors'][0]


@pytest.mark.asyncio
async def test_available_field_false_abstention_flagged(monkeypatch):
    report=template(payload());report['fields']['diet']={'value':None,'kind':'unavailable','source_ids':[]}
    async def fake(*a,**kw):return SimpleNamespace(ok=True,data=canonical(report))
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',fake)
    result=await preview(EvidencePreviewRequest(payload=payload(),method='engineered'))
    assert result['false_abstention_fields']==['diet']


@pytest.mark.asyncio
async def test_token_limit_is_visible_even_if_partial_content_parses(monkeypatch):
    async def fake(*a,**kw):
        return SimpleNamespace(ok=True,data={'content':canonical(template(payload())),'done_reason':'length','eval_count':1400})
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',fake)
    result=await preview(EvidencePreviewRequest(payload=payload(),method='constrained'))
    assert result['report'] is None and 'token limit' in result['validation_errors'][0]


@pytest.mark.asyncio
async def test_private_references_are_rejected():
    p=payload();p['private_reference']={'diet':'HIDDEN_FIXTURE'}
    with pytest.raises(ValueError,match='only'):
        await preview(EvidencePreviewRequest(payload=p))


@pytest.mark.asyncio
async def test_primary_preview_methods_receive_identical_evidence(monkeypatch):
    calls=[]
    async def fake(messages,**kwargs):
        calls.append(messages);return SimpleNamespace(ok=True,data=canonical(template(payload())))
    monkeypatch.setattr('services.evidence_review_service.ollama.chat',fake)
    for method in ('engineered','constrained','qlora'):
        await preview(EvidencePreviewRequest(payload=payload(),method=method))
    assert calls[0]==calls[1]==calls[2]


@pytest.mark.asyncio
async def test_ollama_schema_sent_as_format(monkeypatch):
    from data.sources import ollama
    from data.envelope import ok
    seen=[]
    async def fake(*a,**kwargs):
        seen.append(kwargs['json_body'])
        return ok({'message':{'content':'{}'}},'ollama','chat')
    monkeypatch.setattr(ollama,'fetch',fake)
    result=await ollama.chat([],output_schema={'type':'object'})
    assert result.ok and seen[0]['format']=={'type':'object'}


@pytest.mark.asyncio
async def test_http_preview_validates_request_without_live_startup():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from routers.extinction_risk import router
    app=FastAPI();app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/evidence-preview',json={'payload':payload(),'method':'template'})
        assert response.status_code==200 and response.json()['validation_status']=='structured_valid'
        bad=payload();bad['private_reference']={}
        assert (await client.post('/evidence-preview',json={'payload':bad})).status_code==422
