"""Preview fixed-evidence methods. This endpoint performs no external retrieval.

Ollama previews are operational checks, not the frozen HF experiment: exported
model revisions and GGUF quantization must be verified separately.
"""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from config import get_settings
from data.sources import ollama
from evidence_contract import REPORT_SCHEMA, canonical, strict_json, supported_report_errors, template, validate_payload
from evidence_prompts import messages_for


class EvidencePreviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    payload: dict
    method: Literal['template','original','engineered','constrained','qlora']='template'
    source_catalog: list[dict]=Field(default_factory=list)


async def preview(request: EvidencePreviewRequest):
    payload=validate_payload(request.payload)
    settings=get_settings()
    raw=''
    error=None
    model_name='deterministic-copy'
    inference_metadata={}
    try:
        if request.method=='template':
            raw=canonical(template(payload))
        else:
            model_name=settings.ollama_report_model if request.method=='qlora' else settings.ollama_comparison_base_model
            result=await ollama.chat(messages_for(payload,request.method), model=model_name,
                temperature=0.0,num_predict=1400,
                output_schema=REPORT_SCHEMA if request.method in {'constrained','qlora'} else None,
                include_metadata=True)
            if not result.ok:
                raise RuntimeError('Local model request failed; check the configured model and Ollama service')
            if isinstance(result.data,dict):
                raw=result.data['content']
                inference_metadata={k:v for k,v in result.data.items() if k!='content'}
                if inference_metadata.get('done_reason')=='length':
                    raise ValueError('Model output reached its token limit; response may be truncated')
            else:
                raw=result.data
        report=strict_json(raw)
        errors=supported_report_errors(report,payload)
    except Exception as exc:
        report=None
        errors=[f'{type(exc).__name__}: {exc}']
        error='generation_or_validation_failure'
    if errors:
        report=None
    visible_ids={s['source_id'] for s in payload['sources']}
    catalog=[]
    for s in request.source_catalog:
        if s.get('source_id') in visible_ids:
            catalog.append({k:s.get(k) for k in ('source_id','record_id','url','retrieved_at','excerpt')})
    false_abstention=[]
    if report:
        false_abstention=[f for f,e in payload['fields'].items() if e['availability']=='available' and report['fields'][f]['kind']=='unavailable']
    return {'phase':'application-preview','method':request.method,'model_name':model_name,
            'example_id':payload['example_id'],
            'draft_for_review':True,'report':report,'raw_response':raw,'validation_errors':errors,
            'validation_status':'invalid' if errors else 'structured_valid_prose_pending_review' if report['claims'] else 'structured_valid',
            'missing_fields':[f for f,e in payload['fields'].items() if e['availability']=='missing'],
            'false_abstention_fields':false_abstention, 'sources':payload['sources'],'source_catalog':catalog,
            'error':error,'inference_metadata':inference_metadata,
            'disclaimer':'Draft for human review. Structured support is checked against supplied assertions; source extraction and prose require review. This preview is not a frozen experiment.'}
