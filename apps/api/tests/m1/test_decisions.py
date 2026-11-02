from datetime import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID,uuid4

import pytest

from test_reviews import review_case as review_case,confirm,answer
from test_analysis import fixture,PACK
from test_assessment_records import prepare,process,FixtureModel
from test_documents import upload


@pytest.fixture
def decision_case(client,review_case):
    from app.m1.analysis import validate_candidate
    http,current,app=client
    tender,initial,reviewer,_=review_case
    candidate,context=fixture('answered')
    context.update(workspace_id=str(current[0].workspace_id),tender_id=tender['id'],input_revision=2)
    payload=validate_candidate(candidate,context)
    async def seed():
        async with app.state.pool.acquire() as c:
            manifest=await c.fetchval('SELECT manifest FROM m1_app.artifact_versions WHERE id=$1',UUID(initial['id']))
            return await c.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',2,$3::jsonb,$4::jsonb,$5) RETURNING id",current[0].workspace_id,UUID(tender['id']),manifest,json.dumps(payload),current[0].user_id)
    version=http.portal.call(seed)
    return tender,{**initial,'id':str(version)},payload


def decide(http,tender,assessment,**changes):
    return http.post(f"/api/v1/tenders/{tender['id']}/decisions",json={
        'expected_input_revision':assessment['input_revision'],'assessment_version_id':assessment['id'],
        'decision':'pursue','reason':'I reviewed the critical facts and qualification evidence.',
        'review_complete':True,'client_request_id':str(uuid4()),**changes})


def test_human_decision_replays_and_invalidates_after_source_change(client,decision_case,actors):
    http,current,app=client
    tender,assessment,_=decision_case
    assert decide(http,tender,assessment).status_code==403
    current[0]=actors['approver']
    key=str(uuid4())
    first=decide(http,tender,assessment,client_request_id=key)
    assert first.status_code==201,first.text
    result=first.json()
    assert result['actor_id']==str(actors['approver'].user_id) and result['is_current']
    assert decide(http,tender,assessment,client_request_id=key).json()==result
    current[0]=actors['owner']
    assert upload(http,tender,revision=2).status_code==201
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['decision']['id']==result['id'] and not view['decision']['is_current']
    current[0]=actors['approver']
    replay=decide(http,tender,assessment,client_request_id=key).json()
    assert replay['id']==result['id'] and not replay['is_current']
    assert decide(http,tender,assessment).status_code==409


def test_pursue_requires_attestation_live_blockers_and_nonblank_reason(client,decision_case,actors,monkeypatch):
    from app.m1 import decisions
    http,current,app=client
    tender,assessment,_=decision_case
    current[0]=actors['approver']
    assert decide(http,tender,assessment,review_complete=False).status_code==422
    assert decide(http,tender,assessment,reason='   ').status_code==422
    monkeypatch.setattr(decisions,'utc_now',lambda:datetime.fromisoformat('2026-11-21T00:00:00+08:00'))
    assert decide(http,tender,assessment).status_code==422
    assert decide(http,tender,assessment,decision='hold',review_complete=False).status_code==201


def test_missing_or_foreign_assessment_and_tender_do_not_authorize_decisions(client,decision_case,actors):
    http,current,_=client
    tender,assessment,_=decision_case
    current[0]=actors['approver']
    assert decide(http,tender,assessment,assessment_version_id=str(uuid4())).status_code==409
    current[0]=actors['other']
    assert http.get(f"/api/v1/tenders/{tender['id']}/qualification-brief",params={'assessment_version_id':assessment['id']}).status_code==404
    assert decide(http,tender,assessment).status_code==403


def test_expired_company_evidence_blocks_a_current_pursue(client,decision_case,actors):
    http,current,app=client
    tender,assessment,payload=decision_case
    payload['context']['evidence_dates']['profile-v1']['expires_on']='2026-11-01'
    async def seed():
        async with app.state.pool.acquire() as c:
            row=await c.fetchrow('SELECT * FROM m1_app.artifact_versions WHERE id=$1',UUID(assessment['id']))
            return await c.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',2,$3::jsonb,$4::jsonb,$5) RETURNING id",row['workspace_id'],row['tender_id'],row['manifest'],json.dumps(payload),row['created_by'])
    assessment['id']=str(http.portal.call(seed))
    current[0]=actors['approver']
    response=decide(http,tender,assessment)
    assert response.status_code==422
    assert response.json()['code']=='QUALIFICATION_BLOCKED'


def test_export_labels_exact_snapshot_decision_and_non_current_history(client,decision_case,actors):
    http,current,_=client
    tender,assessment,_=decision_case
    url=f"/api/v1/tenders/{tender['id']}/qualification-brief"
    draft=http.get(url,params={'assessment_version_id':assessment['id']})
    assert draft.status_code==200,draft.text
    assert 'DRAFT' in draft.text and assessment['id'] in draft.text
    assert 'company' in draft.text.lower() and 'profile-v1-p1' in draft.text
    current[0]=actors['approver']
    decision=decide(http,tender,assessment).json()
    current_export=http.get(url,params={'assessment_version_id':assessment['id']})
    assert 'CURRENT HUMAN DECISION' in current_export.text
    assert decision['id'] in current_export.text and str(actors['approver'].user_id) in current_export.text
    assert 'review_complete' in current_export.text
    current[0]=actors['owner']
    assert upload(http,tender,revision=2).status_code==201
    historical=http.get(url,params={'assessment_version_id':assessment['id']})
    assert 'NON-CURRENT' in historical.text and decision['id'] in historical.text
    assert historical.headers['cache-control']=='private, no-store'
    assert 'attachment' in historical.headers['content-disposition']


def test_new_assessment_same_inputs_invalidates_older_snapshot_and_decision(client,decision_case,actors):
    http,current,app=client
    tender,assessment,payload=decision_case
    current[0]=actors['approver']
    assert decide(http,tender,assessment).status_code==201
    async def seed():
        async with app.state.pool.acquire() as c:
            row=await c.fetchrow('SELECT * FROM m1_app.artifact_versions WHERE id=$1',UUID(assessment['id']))
            await c.execute("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',2,$3::jsonb,$4::jsonb,$5)",row['workspace_id'],row['tender_id'],row['manifest'],json.dumps(payload),row['created_by'])
    http.portal.call(seed)
    assert not http.get('/api/v1/assessments/'+assessment['id']).json()['is_current']
    assert not http.get('/api/v1/tenders/'+tender['id']).json()['decision']['is_current']
    assert decide(http,tender,assessment).status_code==409


def test_amendment_waiting_on_decision_cannot_leave_current_approval(client,decision_case,actors,monkeypatch):
    from app.m1.models import RegisterSources,SourceInput
    http,current,app=client
    tender,assessment,_=decision_case
    current[0]=actors['approver']
    locked,release,writer_started=threading.Event(),threading.Event(),threading.Event()
    original=app.state.repository._tender
    async def pause(connection,actor,tender_id,lock=False):
        if actor.user_id==actors['owner'].user_id: writer_started.set()
        row=await original(connection,actor,tender_id,lock)
        if lock and actor.user_id==actors['approver'].user_id:
            locked.set()
            import asyncio
            await asyncio.to_thread(release.wait,10)
        return row
    monkeypatch.setattr(app.state.repository,'_tender',pause)
    command=RegisterSources(tender_id=tender['id'],expected_input_revision=2,client_request_id=str(uuid4()),
        sources=[SourceInput(filename='race.pdf',sha256='b'*64,storage_key=f"{actors['owner'].workspace_id}/controlled-race.pdf",role='tender')])
    with ThreadPoolExecutor(max_workers=2) as executor:
        human=executor.submit(decide,http,tender,assessment)
        assert locked.wait(10)
        writer=executor.submit(http.portal.call,app.state.repository.register_sources,actors['owner'],command)
        try: assert writer_started.wait(10)
        finally: release.set()
        assert human.result().status_code==201
        assert writer.result()['input_revision']==3
    assert not http.get('/api/v1/tenders/'+tender['id']).json()['decision']['is_current']


def test_real_parser_answer_decision_and_addendum_sequence(client,actors):
    from app.m1.models import ActorContext
    from test_jobs import enqueue
    http,current,app=client
    tender,view=prepare(client,actors)
    reviewer=ActorContext(user_id=uuid4(),workspace_id=current[0].workspace_id,roles={'service_reviewer'})
    async def member():
        async with app.state.pool.acquire() as c:
            await c.execute('INSERT INTO m1_app.memberships(workspace_id,user_id,roles) VALUES($1,$2,$3)',reviewer.workspace_id,reviewer.user_id,list(reviewer.roles))
    http.portal.call(member)
    task=confirm(http,tender,view['assessment'],reviewer).json()
    current[0]=reviewer
    event=json.loads((PACK/'events/engineering-answer.json').read_text())
    accepted=answer(http,task,text=event['text']).json()
    process(http,app,accepted['reassessment_job_id'],FixtureModel('answered'))
    ready=http.get('/api/v1/tenders/'+tender['id']).json()['assessment']
    current[0]=actors['approver']
    assert decide(http,tender,ready).status_code==201
    current[0]=actors['owner']
    original=http.get('/api/v1/tenders/'+tender['id']).json()['documents'][0]['id']
    response=http.post(f"/api/v1/tenders/{tender['id']}/documents",data={'metadata':json.dumps({
        'expected_input_revision':ready['input_revision'],'client_request_id':str(uuid4()),
        'files':[{'role':'addendum','amends_version_id':original}]})},
        files={'files':('addendum.pdf',(PACK/'inputs/updates/addendum.pdf').read_bytes(),'application/pdf')})
    assert response.status_code==201,response.text
    assert not http.get('/api/v1/tenders/'+tender['id']).json()['decision']['is_current']
    job=enqueue(http,tender,revision=response.json()['input_revision']).json()
    process(http,app,job['id'],FixtureModel('amended'))
    amended=http.get('/api/v1/tenders/'+tender['id']).json()
    assert amended['assessment']['candidate']['key_facts']['closing_at']['value']=='2026-11-27T16:00:00+08:00'
    assert amended['assessment']['candidate']['requirements'][3]['status']=='unconfirmed'
    assert amended['assessment']['candidate']['recommendation']['decision']=='hold'
    assert not amended['decision']['is_current']


def test_replaying_pursue_after_new_human_decline_is_non_current(client,decision_case,actors):
    http,current,_=client
    tender,assessment,_=decision_case
    current[0]=actors['approver']
    key=str(uuid4())
    first=decide(http,tender,assessment,client_request_id=key).json()
    declined=decide(http,tender,assessment,decision='decline',reason='Human declines after reviewing the same snapshot.').json()
    assert declined['is_current'] and declined['id']!=first['id']
    replay=decide(http,tender,assessment,client_request_id=key).json()
    assert not replay['is_current'], 'A later human decision supersedes the earlier pursuit even on unchanged inputs.'
    assert replay['currency_reason']=='DECISION_SUPERSEDED'
    assert http.get('/api/v1/tenders/'+tender['id']).json()['decision']['id']==declined['id']



def test_browser_decision_currency_still_checks_live_closing(client,decision_case,actors,monkeypatch):
    from app.m1 import decisions,repository,workspace_views

    http,current,_=client
    tender,assessment,_=decision_case
    current[0]=actors['approver']
    assert decide(http,tender,assessment).status_code==201
    urls=['/api/v1/tenders/'+tender['id'],'/api/v1/tenders','/api/v1/tenders/'+tender['id']+'/history']
    def views():
        detail,inbox,history=[http.get(url).json() for url in urls]
        return [detail['decision'],inbox['items'][0]['decision'],history['decisions'][0]]
    assert all(view['is_current'] for view in views())
    for module in (decisions,repository,workspace_views):
        monkeypatch.setattr(module,'utc_now',lambda:datetime.fromisoformat('2026-11-21T00:00:00+08:00'))
    for view in views():
        assert not view['is_current']
        assert view['currency_reason']=='QUALIFICATION_OR_TIME_CHANGED'
