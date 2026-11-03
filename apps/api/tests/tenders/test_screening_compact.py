"""Compact producer references retain evidence and never bypass domain validation."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from app.tenders.policy import DomainError
from app.tenders.screening import validate_interpretation
from app.tenders.screening_workflow import ScreeningReasoner
from app.tenders.usage_budget import PaidCall
from test_screening import candidate,context,finding,run


def unchanged_context(count=1):
    ctx=context();ctx['pins']['source_index_version']=str(uuid4())
    ctx['pins']['answer_version_ids']=[]
    rows=[finding('F'+str(i+1),status='unconfirmed',company_citations=[]) for i in range(count)]
    ctx['previous']={'pins':deepcopy(ctx['pins']),'findings':rows,'overview_issues':[]}
    return ctx


def interpret(monkeypatch,ctx,raw,status='completed'):
    captured={}
    async def provider(self,client,request,prices):
        captured.update(request)
        return SimpleNamespace(status=status,output_text=json.dumps(raw))
    monkeypatch.setattr(PaidCall,'create_response',provider)
    reasoner=ScreeningReasoner(None,None,{'id':uuid4(),'attempt':1,'tender_id':uuid4()}, {},'controlled',object())
    result=asyncio.run(reasoner.interpret(ctx,[]))
    return result,captured


def test_twelve_references_expand_to_original_findings_and_keep_critical_blockers(monkeypatch):
    ctx=unchanged_context(12);before=deepcopy(ctx)
    raw=candidate(*[{'retain_id':f['id']} for f in ctx['previous']['findings']])
    result,request=interpret(monkeypatch,ctx,raw)
    Draft202012Validator(request['text']['format']['schema']).validate(raw)
    accepted=validate_interpretation(result,ctx)
    assert accepted['findings']==before['previous']['findings'] and ctx==before
    assert run(ctx,result)['recommendation']=='needs_information'
    assert 'CRITICAL_CONDITION_UNRESOLVED' in run(ctx,result)['approval_blockers']
    assert len(json.dumps(raw)) < len(json.dumps(candidate(*before['previous']['findings'])))/4
    assert request['max_output_tokens']==6000


@pytest.mark.parametrize('change',['source','company','notice','index','evidence','revision','answers','scoped','unknown_pin',
    'unknown_previous_answers','unknown_current_answers'])
def test_changed_or_unknown_inputs_cannot_retain_a_previous_assessment(monkeypatch,change):
    ctx=unchanged_context()
    keys={'source':'source_signature','company':'company_version_id','notice':'notice_version_id',
        'index':'source_index_version','evidence':'evidence_revision','revision':'input_revision'}
    if change in keys: ctx['pins'][keys[change]]=str(uuid4()) if change=='index' else 'changed'
    elif change=='answers': ctx['pins']['answer_version_ids']=['new-answer']
    elif change=='scoped': ctx['affected_ids']=['F1']
    elif change=='unknown_previous_answers': del ctx['previous']['pins']['answer_version_ids']
    elif change=='unknown_current_answers': del ctx['pins']['answer_version_ids']
    else: del ctx['previous']['pins']['evidence_revision']
    with pytest.raises(DomainError) as error:
        result,_=interpret(monkeypatch,ctx,candidate({'retain_id':'F1'}))
        validate_interpretation(result,ctx)
    assert error.value.code=='SCREENING_INVALID'


@pytest.mark.parametrize('rows',[[{'retain_id':'unknown'}],[{'retain_id':'F1'},{'retain_id':'F1'}],
    [{'retain_id':'F1'},finding('F1')],[{'retain_id':'F1','critical':False}]])
def test_unknown_duplicate_and_modified_references_are_rejected(monkeypatch,rows):
    ctx=unchanged_context()
    with pytest.raises(DomainError):
        result,_=interpret(monkeypatch,ctx,candidate(*rows))
        validate_interpretation(result,ctx)


def test_reference_does_not_hide_missing_source_support(monkeypatch):
    ctx=unchanged_context();ctx['excerpts']=[]
    result,_=interpret(monkeypatch,ctx,candidate({'retain_id':'F1'}))
    with pytest.raises(DomainError) as error: validate_interpretation(result,ctx)
    assert error.value.code=='SCREENING_INVALID'


def test_retained_company_support_is_rechecked_for_expiry(monkeypatch):
    ctx=unchanged_context();ctx['previous']['findings']=[finding('F1')]
    ctx['company_excerpts'][0]['expires_on']='2000-01-01'
    result,_=interpret(monkeypatch,ctx,candidate({'retain_id':'F1'}))
    assert validate_interpretation(result,ctx)['findings'][0]['status']=='unconfirmed'


def test_first_assessment_still_accepts_full_findings(monkeypatch):
    ctx=unchanged_context();ctx['previous']=None
    result,_=interpret(monkeypatch,ctx,candidate(finding('F1')))
    assert validate_interpretation(result,ctx)['findings'][0]['id']=='F1'


def test_incomplete_response_cannot_publish_even_with_references(monkeypatch):
    with pytest.raises(DomainError) as error:
        interpret(monkeypatch,unchanged_context(),candidate({'retain_id':'F1'}),status='incomplete')
    assert error.value.code=='SCREENING_INVALID'


def test_omitted_critical_reference_still_requires_wider_review(monkeypatch):
    ctx=unchanged_context(2)
    result,_=interpret(monkeypatch,ctx,candidate({'retain_id':'F1'}))
    with pytest.raises(DomainError) as error: validate_interpretation(result,ctx)
    assert error.value.code=='SCREENING_DEPENDENCY_WIDER_REQUIRED'


def test_reference_limit_and_new_finding_evidence_are_still_checked(monkeypatch):
    ctx=unchanged_context(24)
    raw=candidate(*[{'retain_id':f['id']} for f in ctx['previous']['findings']],finding('new'))
    result,_=interpret(monkeypatch,ctx,raw)
    with pytest.raises(DomainError): validate_interpretation(result,ctx)
    ctx=unchanged_context()
    new=finding('new',tender_citations=[{'anchor_id':'foreign','quote':'Invented obligation'}])
    result,_=interpret(monkeypatch,ctx,candidate({'retain_id':'F1'},new))
    with pytest.raises(DomainError): validate_interpretation(result,ctx)
