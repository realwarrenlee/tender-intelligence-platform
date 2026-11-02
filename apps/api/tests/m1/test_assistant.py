import asyncio
from copy import deepcopy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID,uuid4

import pytest

from test_analysis import fixture
from test_reviews import review_case as review_case


def context():
    from app.m1.analysis import validate_candidate
    candidate,ctx=fixture()
    payload=validate_candidate(candidate,ctx)
    return {'assessment_version_id':str(uuid4()),'is_current':True,'assessment':{
        key:payload[key] for key in ('candidate','requirements','blockers','reconciliation')},
        'anchors':ctx['source_anchors'],'routing_roles':ctx['routing_roles'],'tasks':[]}


def final(quote='The contractor must provide two FM-T2 qualified technicians on site every Saturday from 09:00 to 13:00 throughout the contract.'):
    return {'answer':'Saturday staffing availability is unconfirmed; a qualified person must supply the missing evidence.',
        'citations':[{'anchor_id':'tender-v1-p1','quote':quote}],'out_of_scope':False}


def call(name,arguments=None,id=None):
    return {'id':id or str(uuid4()),'name':name,'arguments':arguments or {}}


class Scripted:
    def __init__(self,responses): self.responses,self.calls=responses,0
    async def generate(self,messages,tools,schema,prompt):
        index=min(self.calls,len(self.responses)-1)
        self.calls+=1
        response=deepcopy(self.responses[index])
        return {'model':'controlled-assistant','response_id':str(self.calls),'usage':{'total_tokens':100},
            'calls':[],'answer':None,'output':[],**response}


def run(model,ctx=None):
    from app.m1.assistant import run_assistant
    return asyncio.run(run_assistant(ctx or context(),model))


def test_three_tools_scope_draft_cache_and_grounded_answer():
    from app.m1.assistant import tool_definitions
    assert {t['name'] for t in tool_definitions()}=={'get_assessment','search_evidence','prepare_review_request'}
    draft={'requirement_refs':['R4'],'suggested_role':'engineering_lead','question':'Can you confirm the Saturday allocation?','rationale':'The profile leaves staffing unconfirmed.'}
    model=Scripted([{'calls':[call('get_assessment'),call('search_evidence',{'query':'Saturday','source_kind':'tender','limit':1})]},
        {'calls':[call('prepare_review_request',draft),call('prepare_review_request',draft)]},{'answer':final()}])
    result=run(model)
    assert len(result['review_request_drafts'])==1
    assert result['review_request_drafts'][0]['requirement_refs']==['R4']
    assert result['run']['calls']==3 and result['run']['tool_calls']==4
    assert result['run']['total_tokens']==300


@pytest.mark.parametrize('calls',[
    [call('send_email',{'to':'external@example.invalid'})],
    [call('record_decision',{'decision':'pursue'})],
    [call('get_assessment',{'workspace_id':str(uuid4())})],
    [call('prepare_review_request',{'requirement_refs':['invented'],'suggested_role':'engineering_lead','question':'Q','rationale':'R'})],
])
def test_unallowlisted_tools_and_injected_scope_are_rejected(calls):
    from app.m1.policy import DomainError
    with pytest.raises(DomainError) as error: run(Scripted([{'calls':calls}]))
    assert error.value.code=='ASSISTANT_INVALID'
    assert error.value.run['calls']==2


def test_search_is_pinned_and_role_limited():
    from app.m1.assistant import search_evidence
    ctx=context()
    tender=search_evidence(ctx,{'query':'Saturday','source_kind':'tender','limit':1})
    assert len(tender)==1 and tender[0]['source_role']=='tender'
    company=search_evidence(ctx,{'query':'Saturday','source_kind':'company','limit':10})
    assert company and all(a['source_role']=='company_evidence' for a in company)
    assert search_evidence(ctx,{'query':'foreign workspace confidential phrase','source_kind':'all','limit':5})==[]


def test_tool_and_model_call_budgets_are_enforced():
    from app.m1.policy import DomainError
    with pytest.raises(DomainError) as error: run(Scripted([{'calls':[call('get_assessment') for _ in range(7)]}]))
    assert error.value.code=='ASSISTANT_TOOL_LIMIT'
    with pytest.raises(DomainError) as error: run(Scripted([{'calls':[call('get_assessment')]}]))
    assert error.value.code=='ASSISTANT_BUDGET_EXHAUSTED'
    assert error.value.run['calls']==3


def test_fabricated_quote_repairs_once_and_refusal_is_terminal():
    from app.m1.policy import DomainError
    result=run(Scripted([{'answer':final('Invented quote')},{'answer':final()}]))
    assert result['run']['calls']==2 and result['run']['total_tokens']==200
    with pytest.raises(DomainError) as error: run(Scripted([{'answer':final('Invented quote')}]))
    assert error.value.code=='ASSISTANT_INVALID'
    with pytest.raises(DomainError) as error: run(Scripted([{'failure_code':'MODEL_REFUSED'}]))
    assert error.value.code=='MODEL_REFUSED' and error.value.run['calls']==1


def test_out_of_scope_response_cannot_claim_external_action_or_make_drafts():
    result=run(Scripted([{'answer':{'answer':'I emailed the client and approved the bid.','citations':[],'out_of_scope':True}}]))
    assert result['out_of_scope']
    assert 'I emailed' not in result['answer']
    assert result['review_request_drafts']==[]


def ask(http,tender,assessment,**changes):
    return http.post(f"/api/v1/tenders/{tender['id']}/assistant-messages",json={
        'assessment_version_id':assessment['id'],'text':'What is stopping this bid?',
        'client_request_id':str(uuid4()),**changes})


def test_assistant_http_persists_usage_replays_and_drafts_need_human_confirmation(client,review_case,actors):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    draft={'requirement_refs':['R4'],'suggested_role':'engineering_lead','question':'Can you confirm Saturday availability?','rationale':'Missing staffing allocation.'}
    model=Scripted([{'calls':[call('prepare_review_request',draft)]},{'answer':final()}])
    app.state.assistant_model=model
    key=str(uuid4())
    response=ask(http,tender,assessment,client_request_id=key)
    assert response.status_code==200,response.text
    result=response.json()
    assert ask(http,tender,assessment,client_request_id=key).json()==result
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['review_tasks']==[] and view['decision'] is None
    prepared=result['review_request_drafts'][0]
    task=http.post(f"/api/v1/tenders/{tender['id']}/review-tasks",json={
        'expected_assessment_version_id':assessment['id'],'draft_ref':prepared['draft_ref'],
        'assignee_id':str(reviewer.user_id),'client_request_id':str(uuid4())})
    assert task.status_code==201,task.text
    async def stored():
        async with app.state.pool.acquire() as c:
            row=await c.fetchrow('SELECT * FROM m1_app.assistant_runs WHERE id=$1',UUID(result['run_id']))
            assert row['status']=='completed'
            assert len(json.loads(row['calls']))==2
    http.portal.call(stored)
    current[0]=actors['other']
    assert ask(http,tender,assessment).status_code==404


def test_inflight_replay_is_bounded_and_upload_does_not_wait_for_model(client,review_case):
    from test_documents import upload
    http,current,app=client
    tender,assessment,_,_=review_case
    started,release=threading.Event(),threading.Event()
    class Slow(Scripted):
        async def generate(self,*args):
            started.set()
            await asyncio.to_thread(release.wait,10)
            return await super().generate(*args)
    app.state.assistant_model=Slow([{'answer':final()}])
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending=executor.submit(ask,http,tender,assessment,client_request_id=key)
        assert started.wait(10)
        try:
            duplicate=ask(http,tender,assessment,client_request_id=key)
            assert duplicate.status_code==409,duplicate.text
            assert upload(http,tender,revision=2).status_code==201
        finally: release.set()
        result=pending.result()
    assert result.status_code==200,result.text
    assert result.json()['is_current'] is False
    assert result.json()['answer'].startswith('This snapshot is no longer current.')
    replay=ask(http,tender,assessment,client_request_id=key)
    assert not replay.json()['is_current']


def test_invalid_tool_batch_is_acknowledged_before_schema_repair():
    class ChecksProtocol(Scripted):
        async def generate(self,messages,*args):
            if self.calls:
                requested={m['call_id'] for m in messages if m.get('type')=='function_call'}
                answered={m['call_id'] for m in messages if m.get('type')=='function_call_output'}
                assert requested==answered, 'Every requested tool needs an output before the next model request.'
            return await super().generate(messages,*args)
    result=run(ChecksProtocol([{'calls':[call('send_email'),call('get_assessment')]},{'answer':final()}]))
    assert result['run']['calls']==2


def test_concurrent_same_identity_reservation_has_one_paid_turn(client,review_case,monkeypatch):
    http,current,app=client
    tender,assessment,_,_=review_case
    claimed,release,second_started=threading.Event(),threading.Event(),threading.Event()
    original=app.state.repository._claim
    entries=0
    async def pause(c,actor,operation,command):
        nonlocal entries
        entries+=1
        entry=entries
        if entry==2: second_started.set()
        replay=await original(c,actor,operation,command)
        if entry==1:
            claimed.set()
            await asyncio.to_thread(release.wait,10)
        return replay
    monkeypatch.setattr(app.state.repository,'_claim',pause)
    app.state.assistant_model=Scripted([{'answer':final()}])
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(ask,http,tender,assessment,client_request_id=key)
        assert claimed.wait(10)
        second=executor.submit(ask,http,tender,assessment,client_request_id=key)
        try: assert second_started.wait(10)
        finally: release.set()
        results=[first.result(),second.result()]
    assert all(r.status_code in (200,409) for r in results)
    assert app.state.assistant_model.calls==1


def test_review_answer_retrieval_preserves_original_question_and_scope():
    from app.m1.assistant import search_evidence
    ctx=context()
    source={'anchor_id':'older-answer','document_version_id':'evidence-answer','source_role':'review_answer',
        'text':'Confirmed.','answer_id':str(uuid4()),'actor_id':str(uuid4()),'response_kind':'confirmed',
        'requirement_ids':['older-two-technician-obligation'],'question':'Can two technicians cover Saturday?',
        'assessment_version_id':str(uuid4()),'source_manifest':{'assessment_input_revision':2,'documents':[{'id':'older-tender'}]},
        'basis':'Reviewed the approved two-person rota.'}
    ctx['anchors']['older-answer']=source
    result=search_evidence(ctx,{'query':'Confirmed','source_kind':'review_answer','limit':1})[0]
    for field in ('question','assessment_version_id','source_manifest','basis'):
        assert result[field]==source[field], 'A short confirmation must retain the obligation it confirms.'


def test_openai_tool_items_use_wire_names_and_omit_null_fields(monkeypatch):
    import openai
    from openai.types.responses import Response,ResponseFunctionToolCall
    from app.m1.assistant import OpenAIAssistant
    item=ResponseFunctionToolCall.model_construct(id='fc_test',type='function_call',call_id='call_test',
        name='get_assessment',arguments='{}',status='completed',async_=None,caller=None,namespace=None)
    response=Response.model_construct(id='resp_test',model='controlled',status='completed',output=[item],usage=None)
    class Client:
        def __init__(self,**kwargs): self.responses=self
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def create(self,**kwargs): return response
    monkeypatch.setattr(openai,'AsyncOpenAI',Client)
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import config
    monkeypatch.setattr(config,'get_settings',lambda: SimpleNamespace(
        openai_api_key=SecretStr('controlled-test-key'),openai_model='controlled',openai_prices={}))
    class ControlledCall:
        async def create_response(self,client,request,prices): return await client.responses.create(**request)
    result=asyncio.run(OpenAIAssistant().generate([],[],{},'Controlled adapter test',paid_call=ControlledCall()))
    wire=result['output'][0]
    assert 'async_' not in wire, 'Python reserved-word aliases are not valid Responses API input keys.'
    assert 'namespace' not in wire, 'A null namespace is not a string input.'
    assert wire['call_id']=='call_test'
