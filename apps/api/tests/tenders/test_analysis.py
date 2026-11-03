import asyncio
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest

ROOT=Path(__file__).resolve().parents[4]
PACK=ROOT/'evals/fixtures/development/D1-qualification'


def implemented():
    assert (ROOT/'apps/api/app/tenders/analysis.py').exists(), 'T3 assessment pipeline is missing'
    from app.tenders import analysis
    return analysis


def fixture(stage='initial'):
    candidate=json.loads((PACK/f'mock-responses/analysis-{stage}.json').read_text())
    # Control mocks build test inputs only; these are never runtime model input.
    from pypdf import PdfReader
    manifest=json.loads((PACK/'manifest.json').read_text())
    anchors={}
    for doc in manifest['documents']:
        for number,page in enumerate(PdfReader(PACK/doc['path']).pages,1):
            anchor_id=f"{doc['version_id']}-p{number}"
            anchors[anchor_id]={'anchor_id':anchor_id,'document_version_id':doc['version_id'],
                'source_role':doc['role'],'page':number,'paragraph':None,'answer_id':None,'text':page.extract_text()}
    event=json.loads((PACK/'events/engineering-answer.json').read_text())
    if stage!='initial':
        anchors[event['anchor_id']]={'anchor_id':event['anchor_id'],'document_version_id':event['evidence_version_id'],
            'source_role':'review_answer','page':None,'paragraph':None,'answer_id':event['evidence_version_id'],'text':event['text'],'response_kind':'confirmed',
            'requirement_ids':[implemented().requirement_identity(json.loads((PACK/'mock-responses/analysis-initial.json').read_text())['requirements'][3])]}
    if stage!='amended': anchors={k:v for k,v in anchors.items() if v['source_role']!='addendum'}
    anchors={k:v for k,v in anchors.items() if v['source_role']!='reference_note'}
    context={'workspace_id':str(uuid4()),'tender_id':str(uuid4()),'input_revision':1,'source_set_id':str(uuid4()),
        'company_evidence_version_ids':['profile-v1'],'review_answer_version_ids':[event['evidence_version_id']] if stage!='initial' else [],
        'source_anchors':anchors,'as_of':'2026-10-26T10:00:00+08:00','closing_timezone':'Asia/Singapore',
        'routing_roles':['engineering_lead'],'schema_version':'m1.v1','run_id':str(uuid4()),
        'source_complete':True,'evidence_dates':{'profile-v1':{'effective_on':'2026-01-01','expires_on':'2027-12-31'}},
        'previous_assessment':None}
    return candidate,context


@pytest.mark.parametrize('stage,decision',[('initial','hold'),('answered','pursue'),('amended','hold')])
def test_d1_canonical_candidates_and_policy(stage,decision):
    module=implemented()
    candidate,context=fixture(stage)
    result=module.validate_candidate(candidate,context)
    assert result['candidate']['recommendation']['decision']==decision
    assert bool(result['blockers']) == (stage!='answered')
    assert len(result['requirements'])==6


@pytest.mark.parametrize('fault',['quote','anchor','location','offset','support','duplicate','not_assessed','pursue','role','blank_quote','duplicate_draft'])
def test_invalid_candidates_are_rejected(fault):
    module=implemented()
    candidate,context=fixture()
    if fault=='quote': candidate['requirements'][0]['tender_citations'][0]['quote']='Invented obligation'
    elif fault=='anchor': candidate['key_facts']['title']['citations'][0]['anchor_id']='foreign-workspace'
    elif fault=='location': context['source_anchors']['tender-v1-p1']['page']=0
    elif fault=='offset': candidate['key_facts']['closing_at']['value']='2026-11-20T16:00:00'
    elif fault=='support': candidate['requirements'][0]['company_citations']=[]
    elif fault=='duplicate': candidate['requirements'][1]['local_ref']='R1'
    elif fault=='not_assessed': candidate['requirements'][3]['status']='not_assessed'
    elif fault=='pursue': candidate['recommendation']['decision']='pursue'
    elif fault=='role': candidate['review_requests'][0]['suggested_role']='invented_employee'
    elif fault=='blank_quote': candidate['requirements'][0]['tender_citations'][0]['quote']=' \t '
    else: candidate['review_requests'].append(deepcopy(candidate['review_requests'][0]))
    with pytest.raises(module.CandidateError): module.validate_candidate(candidate,context)


def test_staffing_answer_cannot_remove_unrelated_requirement():
    module=implemented()
    first,context=fixture()
    extra=deepcopy(first['requirements'][3])
    extra.update(local_ref='scope-review',text='Clarify the general delivery scope',missing_information='Service scope capability is unconfirmed')
    extra['tender_citations']=[first['requirements'][0]['tender_citations'][0]]
    first['requirements'].append(extra)
    previous=module.validate_candidate(first,context)
    answered,next_context=fixture('answered')
    next_context['previous_assessment']=previous
    answered['recommendation']['decision']='hold'
    result=module.validate_candidate(answered,next_context)
    assert any(r['requirement']['local_ref']=='scope-review' for r in result['requirements'])
    assert any(b['code']=='RECONCILIATION_REQUIRED' for b in result['blockers'])
    assert any(c['kind']=='missing_or_changed' for c in result['reconciliation'])


def test_source_identity_survives_local_reference_renumbering():
    module=implemented()
    candidate,context=fixture()
    prior=module.validate_candidate(candidate,context)
    candidate['requirements'][0]['local_ref']='renumbered'
    context['previous_assessment']=prior
    result=module.validate_candidate(candidate,context)
    assert [r['id'] for r in result['requirements']]==[r['id'] for r in prior['requirements']]


def test_unchanged_evidence_cannot_optimistically_resolve_unknown():
    module=implemented()
    initial,context=fixture()
    prior=module.validate_candidate(initial,context)
    initial['requirements'][3]['status']='met'
    initial['requirements'][3]['missing_information']=None
    initial['recommendation']['decision']='hold'
    context['previous_assessment']=prior
    with pytest.raises(module.CandidateError): module.validate_candidate(initial,context)


def test_model_boundary_repairs_once_and_records_usage():
    module=implemented()
    candidate,context=fixture()
    broken=deepcopy(candidate)
    broken['requirements'][0]['tender_citations'][0]['quote']='Fabrication'
    class Scripted:
        async def generate(self,*args):
            value=[broken,candidate][len(calls)]
            calls.append(1)
            return {'candidate':value,'model':'controlled-model','usage':{'total_tokens':100},'response_id':str(len(calls))}
    calls=[]
    result=asyncio.run(module.analyse(context,Scripted()))
    assert result['run']['calls']==2
    assert result['run']['total_tokens']==200
    assert result['candidate']['recommendation']['decision']=='hold'
    assert result['run']['prompt_sha256']


def test_repair_budget_exhaustion_preserves_failure_diagnostics():
    module=implemented()
    candidate,context=fixture()
    candidate['requirements'][0]['tender_citations'][0]['quote']='Fabrication'
    class Scripted:
        async def generate(self,*args):
            calls.append(1)
            return {'candidate':candidate,'model':'controlled-model','usage':{'total_tokens':1},'response_id':str(len(calls))}
    calls=[]
    with pytest.raises(module.CandidateError) as error: asyncio.run(module.analyse(context,Scripted()))
    assert error.value.run['calls']==2
    assert len(calls)==2


def test_model_timeout_is_bounded_and_accounted_for():
    module=implemented()
    _,context=fixture()
    calls=[]
    class TimeoutModel:
        async def generate(self,*args):
            calls.append(1)
            raise TimeoutError('Fictional model timeout')
    with pytest.raises(module.CandidateError) as error: asyncio.run(module.analyse(context,TimeoutModel()))
    assert len(calls)==3
    assert error.value.run['calls']==3


def test_incomplete_provider_response_records_usage_without_schema_repair():
    module=implemented()
    from app.tenders.policy import DomainError
    _,context=fixture()
    class Incomplete:
        async def generate(self,*args):
            return {'candidate':{},'model':'controlled','response_id':'truncated','usage':{'total_tokens':77},'failure_code':'MODEL_INCOMPLETE'}
    with pytest.raises(DomainError) as error: asyncio.run(module.analyse(context,Incomplete()))
    assert error.value.code=='MODEL_INCOMPLETE'
    assert error.value.run['calls']==1
    assert error.value.run['total_tokens']==77


def test_cached_response_cannot_claim_a_different_prompt_configuration():
    module=implemented()
    candidate,context=fixture()
    class OldLedger:
        async def history(self):
            return [{'state':'completed','purpose':'initial','result':{'candidate':candidate,'model':'older',
                'usage':{'total_tokens':1},'config':{'prompt_sha256':'different-prompt'}}}]
    with pytest.raises(module.CandidateError): asyncio.run(module.analyse(context,None,OldLedger()))


def test_preserved_human_finding_is_consistent_in_candidate_and_records():
    module=implemented()
    candidate,context=fixture()
    previous=module.validate_candidate(candidate,context)
    corrected=deepcopy(previous['requirements'][3]['requirement'])
    corrected['explanation']='Human correction: the approved rota is missing.'
    previous['requirements'][3]['requirement']=corrected
    previous['manual_corrections']=[{'kind':'requirement','id':previous['requirements'][3]['id'],'value':corrected}]
    context['previous_assessment']=previous
    result=module.validate_candidate(candidate,context)
    assert result['candidate']['requirements'][3]['explanation']==corrected['explanation']

def test_unresolved_change_and_addition_remain_blocked_across_reruns():
    module=implemented()
    candidate,context=fixture()
    original=module.validate_candidate(candidate,context)
    candidate['requirements'][3]['mandatory']=False
    context['previous_assessment']=original
    first=module.validate_candidate(candidate,context)
    context['previous_assessment']=first
    second=module.validate_candidate(candidate,context)
    assert any(b['code']=='RECONCILIATION_REQUIRED' for b in second['blockers'])
    change=next(c for c in second['reconciliation'] if c['kind']=='changed')
    assert change['previous_requirement']['mandatory'] is True
    extra=deepcopy(candidate['requirements'][3])
    extra.update(local_ref='extra',text='Additional obligation')
    extra['tender_citations']=[candidate['requirements'][0]['tender_citations'][0]]
    candidate['requirements'].append(extra)
    third=module.validate_candidate(candidate,context)
    assert any(c['kind']=='added' and not c['resolved'] for c in third['reconciliation'])


@pytest.mark.parametrize('code',['MODEL_INCOMPLETE','MODEL_REFUSED'])
def test_persisted_provider_failure_is_terminal_on_replay(code):
    module=implemented()
    from app.tenders.policy import DomainError
    candidate,context=fixture()
    class Ledger:
        rows=[]
        async def history(self): return self.rows
        async def reserve(self,purpose): return 1
        async def finish(self,sequence,result,state):
            self.rows.append({'state':state,'purpose':'initial','result':result})
    class Failed:
        calls=0
        async def generate(self,*args):
            self.calls+=1
            return {'candidate':candidate,'model':'controlled','usage':{'total_tokens':77},'failure_code':code}
    ledger,model=Ledger(),Failed()
    for _ in range(2):
        with pytest.raises(DomainError) as error: asyncio.run(module.analyse(context,model,ledger))
        assert error.value.code==code
        assert error.value.run['total_tokens']==77
    assert model.calls==1

def test_completed_provider_refusal_is_not_schema_repaired(monkeypatch):
    from types import SimpleNamespace
    import openai
    from pydantic import SecretStr
    from app import config
    module=implemented()
    _,context=fixture()
    class Response:
        output_text=''
        output=[SimpleNamespace(content=[SimpleNamespace(type='refusal')])]
        status='completed'
        model='controlled'
        id='refused'
        usage=SimpleNamespace(model_dump=lambda: {'total_tokens':19})
        def model_dump(self,**kwargs): return {'status':'completed','refusal':'controlled refusal'}
    calls=[]
    class Client:
        def __init__(self,**kwargs): self.responses=self
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def create(self,**kwargs):
            calls.append(1)
            return Response()
    monkeypatch.setattr(openai,'AsyncOpenAI',Client)
    monkeypatch.setattr(config,'get_settings',lambda: SimpleNamespace(openai_api_key=SecretStr('fictional-key'),openai_model='controlled',openai_prices={}))
    from app.tenders.policy import DomainError
    class ControlledCall:
        async def create_response(self,client,request,prices): return await client.responses.create(**request)
    class Ledger:
        async def history(self): return []
        async def reserve(self,purpose): return 1
        async def finish(self,*args): pass
        async def paid_call(self,sequence): return ControlledCall()
    with pytest.raises(DomainError) as error: asyncio.run(module.analyse(context,module.OpenAIModel(),Ledger()))
    assert error.value.code=='MODEL_REFUSED'
    assert len(calls)==1


@pytest.mark.parametrize('response_kind,status',[('denied','met'),('unable_to_confirm','met'),('unable_to_confirm','unmet')])
def test_nonconfirmation_answer_cannot_support_a_definite_finding(response_kind,status):
    module=implemented()
    candidate,context=fixture('answered')
    context['source_anchors']['engineering-answer-v1-note']['response_kind']=response_kind
    candidate['requirements'][3]['status']=status
    candidate['recommendation']['decision']='hold'
    with pytest.raises(module.CandidateError): module.validate_candidate(candidate,context)


def test_scoped_answer_cannot_confirm_an_unrelated_requirement():
    module=implemented()
    initial,old_context=fixture()
    initial['requirements'][0].update(status='unconfirmed',missing_information='Current certification needs review.')
    previous=module.validate_candidate(initial,old_context)
    candidate,context=fixture('answered')
    answer=context['source_anchors']['engineering-answer-v1-note']
    answer.update(response_kind='confirmed',requirement_ids=[module.requirement_identity(candidate['requirements'][3])])
    candidate['requirements'][0]['company_citations']=[candidate['requirements'][3]['company_citations'][0]]
    context['previous_assessment']=previous
    with pytest.raises(module.CandidateError): module.validate_candidate(candidate,context)


def test_changed_requirement_needs_fresh_confirmation():
    module=implemented()
    candidate,context=fixture('amended')
    initial,_=fixture()
    context['source_anchors']['engineering-answer-v1-note'].update(response_kind='confirmed',requirement_ids=[module.requirement_identity(initial['requirements'][3])])
    candidate['requirements'][3].update(status='met',missing_information=None)
    with pytest.raises(module.CandidateError): module.validate_candidate(candidate,context)


@pytest.mark.parametrize('field,value',[('response_kind',None),('response_kind','invented'),('requirement_ids',[]),('requirement_ids',None),('requirement_ids',['invented'])])
def test_cited_answer_requires_valid_typed_scope_metadata(field,value):
    module=implemented()
    candidate,context=fixture('answered')
    answer=context['source_anchors']['engineering-answer-v1-note']
    answer.update(response_kind='confirmed',requirement_ids=[module.requirement_identity(candidate['requirements'][3])])
    answer[field]=value
    with pytest.raises(module.CandidateError): module.validate_candidate(candidate,context)


def test_preserved_human_finding_rechecks_answer_scope():
    from copy import deepcopy
    module=implemented()
    initial,old_context=fixture()
    previous=module.validate_candidate(initial,old_context)
    answered,context=fixture('answered')
    finding=answered['requirements'][3]
    previous['manual_corrections']=[{'kind':'requirement','id':previous['requirements'][3]['id'],'value':finding}]
    context['source_anchors']['engineering-answer-v1-note'].update(response_kind='confirmed',requirement_ids=[previous['requirements'][0]['id']])
    context['previous_assessment']=previous
    result=module.validate_candidate(deepcopy(initial),context)
    assert result['requirements'][3]['requirement']['status']=='unconfirmed'
