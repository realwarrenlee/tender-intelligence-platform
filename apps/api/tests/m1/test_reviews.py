from datetime import datetime,timezone
import json
from uuid import UUID,uuid4

import pytest

from test_analysis import fixture,PACK
from test_documents import create,upload
from test_assessment_records import prepare,process,FixtureModel


@pytest.fixture
def review_case(client,actors):
    # Seed a controlled validated assessment; parser/model behavior is covered by the full cycle below.
    from app.m1.analysis import validate_candidate
    from app.m1.models import ActorContext
    http,current,app=client
    tender=create(http)
    uploaded=upload(http,tender)
    assert uploaded.status_code==201,uploaded.text
    candidate,context=fixture()
    context.update(workspace_id=str(current[0].workspace_id),tender_id=tender['id'],input_revision=2,
                   source_set_id=uploaded.json()['source_set_version_id'])
    payload=validate_candidate(candidate,context)
    reviewer=ActorContext(user_id=uuid4(),workspace_id=current[0].workspace_id,roles={'service_reviewer'})
    stranger=ActorContext(user_id=uuid4(),workspace_id=current[0].workspace_id,roles={'service_reviewer'})
    async def seed():
        async with app.state.pool.acquire() as c:
            for person in (reviewer,stranger):
                await c.execute('INSERT INTO m1_app.memberships(workspace_id,user_id,roles) VALUES($1,$2,$3)',person.workspace_id,person.user_id,list(person.roles))
            return await c.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',2,$3::jsonb,$4::jsonb,$5) RETURNING id",
                current[0].workspace_id,UUID(tender['id']),json.dumps({'evidence_revision':0,'source_set_version_id':context['source_set_id'],'previous_assessment':{'control_only':'do not recursively copy prior payloads'}}),json.dumps(payload),current[0].user_id)
    http.portal.call(seed)
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    return tender,view['assessment'],reviewer,stranger


def confirm(http,tender,assessment,assignee,**overrides):
    command={'expected_assessment_version_id':assessment['id'],'draft_ref':assessment['candidate']['review_requests'][0]['draft_ref'],
        'assignee_id':str(assignee.user_id),'client_request_id':str(uuid4()),**overrides}
    return http.post(f"/api/v1/tenders/{tender['id']}/review-tasks",json=command)


def answer(http,task,**overrides):
    return http.post(f"/api/v1/review-tasks/{task['id']}/answers",json={
        'expected_task_revision':task['revision'],'response_kind':'confirmed','text':'Fictional tender-specific confirmation.',
        'client_request_id':str(uuid4()),**overrides})


@pytest.mark.parametrize('closing,expected',[
    ('2026-11-05T10:00:00+00:00','2026-11-03T10:00:00+00:00'),
    ('2026-11-02T22:00:00+00:00','2026-11-01T22:00:00+00:00'),
    ('2026-11-01T20:00:00+00:00','2026-11-01T10:00:00+00:00'),
])
def test_default_due_uses_utc_formula(closing,expected):
    from app.m1 import reviews
    assert reviews.default_due_at(datetime.fromisoformat('2026-11-01T10:00:00+00:00'),datetime.fromisoformat(closing))==datetime.fromisoformat(expected)


@pytest.mark.parametrize('closing',[None,datetime(2026,10,1,tzinfo=timezone.utc),datetime(2026,12,1)])
def test_default_due_refuses_unknown_past_or_naive_closing(closing):
    from app.m1 import reviews
    from app.m1.policy import DomainError
    with pytest.raises(DomainError):
        reviews.default_due_at(datetime(2026,11,1,tzinfo=timezone.utc),closing)


def test_draft_needs_confirmation_and_deduplicates_open_tasks(client,review_case,actors):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    assert http.get('/api/v1/tenders/'+tender['id']).json()['review_tasks']==[]
    key=str(uuid4())
    first=confirm(http,tender,assessment,reviewer,client_request_id=key)
    assert first.status_code==201,first.text
    task=first.json()
    assert task['assignee_id']==str(reviewer.user_id)
    assert task['assessment_version_id']==assessment['id']
    assert task['manifest']['source_set_version_id']
    assert task['requirement_ids']==[assessment['requirements'][3]['id']]
    assert confirm(http,tender,assessment,reviewer,client_request_id=key).json()==task
    assert confirm(http,tender,assessment,reviewer).json()['id']==task['id']
    assert len(http.get('/api/v1/tenders/'+tender['id']).json()['review_tasks'])==1
    current[0]=actors['viewer']
    assert confirm(http,tender,assessment,reviewer).status_code==403
    current[0]=actors['other']
    assert confirm(http,tender,assessment,reviewer).status_code==404


def test_confirmation_validates_assignee_draft_currency_and_due(client,review_case,actors):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    assert confirm(http,tender,assessment,actors['viewer']).status_code==422
    assert confirm(http,tender,assessment,actors['other']).status_code==422
    assert confirm(http,tender,assessment,reviewer,draft_ref='invented').status_code==422
    assert confirm(http,tender,assessment,reviewer,expected_assessment_version_id=str(uuid4())).status_code==409
    assert confirm(http,tender,assessment,reviewer,due_at='2020-01-01T00:00:00+00:00').status_code==422
    assert confirm(http,tender,assessment,reviewer,due_at='2026-10-24T15:00:00').status_code==422
    from app.m1 import reviews
    from unittest.mock import patch
    with patch.object(reviews,'utc_now',lambda:datetime.fromisoformat('2026-10-26T10:00:00+08:00')):
        response=confirm(http,tender,assessment,reviewer,due_at='2026-10-27T09:30:00+08:00')
        assert response.status_code==201,response.text
        assert datetime.fromisoformat(response.json()['due_at'])==datetime.fromisoformat('2026-10-27T09:30:00+08:00')
    assert upload(http,tender,revision=2).status_code==201
    assert confirm(http,tender,assessment,reviewer).status_code==409


def test_assigned_answer_is_atomic_attributed_and_idempotent(client,review_case,actors):
    http,current,app=client
    tender,assessment,reviewer,stranger=review_case
    task=confirm(http,tender,assessment,reviewer).json()
    current[0]=stranger
    assert answer(http,task).status_code==403
    current[0]=actors['owner']
    assert answer(http,task).status_code==403
    current[0]=actors['other']
    assert answer(http,task).status_code==404
    current[0]=reviewer
    assert answer(http,task,text='   ').status_code==422
    assert answer(http,task,actor_id=str(stranger.user_id)).status_code==422
    key=str(uuid4())
    first=answer(http,task,client_request_id=key)
    assert first.status_code==201,first.text
    result=first.json()
    assert answer(http,task,client_request_id=key).json()==result
    assert answer(http,task).status_code==409
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['input_revision']==3
    assert view['assessment']['is_current'] is False
    saved=view['review_tasks'][0]
    assert saved['status']=='answered' and saved['revision']==2
    assert saved['answer']['actor_id']==str(reviewer.user_id)
    assert saved['answer']['response_kind']=='confirmed'
    assert saved['answer']['reassessment_status']=='queued'
    async def inspect():
        async with app.state.pool.acquire() as c:
            assert await c.fetchval('SELECT count(*) FROM m1_app.review_answers WHERE task_id=$1',UUID(task['id']))==1
            row=await c.fetchrow('SELECT * FROM m1_app.jobs WHERE id=$1',UUID(result['reassessment_job_id']))
            manifest=json.loads(row['manifest'])
            assert row['created_by']==reviewer.user_id
            assert manifest['review_answers'][0]['actor_id']==str(reviewer.user_id)
            assert manifest['review_answers'][0]['response_kind']=='confirmed'
            assert manifest['review_answers'][0]['task_id']==task['id']
            assert await c.fetchval('SELECT count(*) FROM m1_queue.pgqueuer WHERE dedupe_key=$1',result['reassessment_job_id'])==1
    http.portal.call(inspect)


def test_enqueue_failure_rolls_back_answer_revision_and_task(client,review_case,monkeypatch):
    from app.m1 import jobs
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    task=confirm(http,tender,assessment,reviewer).json()
    current[0]=reviewer
    original=jobs.queue_queries
    class Unavailable:
        async def enqueue(self,*args,**kwargs): raise ConnectionError('Controlled queue unavailable')
    monkeypatch.setattr(jobs,'queue_queries',lambda connection:Unavailable())
    response=answer(http,task)
    assert response.status_code==503,response.text
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['input_revision']==2 and view['assessment']['is_current']
    assert view['review_tasks'][0]['status']=='open'
    assert view['review_tasks'][0]['answer'] is None
    async def counts():
        async with app.state.pool.acquire() as c:
            return await c.fetchrow("SELECT (SELECT count(*) FROM m1_app.review_answers WHERE task_id=$1) answers,(SELECT count(*) FROM m1_app.artifact_versions WHERE tender_id=$2 AND kind='review_answer') evidence,(SELECT count(*) FROM m1_app.jobs WHERE tender_id=$2) jobs",UUID(task['id']),UUID(tender['id']))
    assert tuple(http.portal.call(counts))==(0,0,0)
    monkeypatch.setattr(jobs,'queue_queries',original)
    assert answer(http,task).status_code==201


def test_assigned_owner_requires_basis_and_unable_answer_stays_unknown(client,review_case,actors):
    http,current,app=client
    tender,assessment,_,_=review_case
    task=confirm(http,tender,assessment,actors['owner']).json()
    assert answer(http,task,response_kind='unable_to_confirm').status_code==422
    response=answer(http,task,response_kind='unable_to_confirm',basis='I checked the latest allocation register.')
    assert response.status_code==201,response.text
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['assessment']['candidate']['requirements'][3]['status']=='unconfirmed'
    assert not view['assessment']['is_current']
    assert view['review_tasks'][0]['answer']['response_kind']=='unable_to_confirm'


def test_real_parser_answer_endpoint_and_reassessment_cycle(client,actors):
    from app.m1.models import ActorContext
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
    response=answer(http,task,text=event['text'])
    assert response.status_code==201,response.text
    assert not http.get('/api/v1/tenders/'+tender['id']).json()['assessment']['is_current']
    process(http,app,response.json()['reassessment_job_id'],FixtureModel('answered'))
    updated=http.get('/api/v1/tenders/'+tender['id']).json()
    assert updated['assessment']['is_current']
    staffing=next(r for r in updated['assessment']['candidate']['requirements'] if r['local_ref']=='R4')
    assert staffing['status']=='met'
    assert any(c['anchor_id']==response.json()['evidence_version_id']+'-answer' for c in staffing['company_citations'])
    assert updated['review_tasks'][0]['answer']['reassessment_status']=='completed'

def test_concurrent_confirmations_and_answer_replays_have_one_effect(client,review_case):
    from concurrent.futures import ThreadPoolExecutor
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses=list(executor.map(lambda _:confirm(http,tender,assessment,reviewer),range(2)))
    assert all(r.status_code==201 for r in responses),[r.text for r in responses]
    assert len({r.json()['id'] for r in responses})==1
    task=responses[0].json()
    current[0]=reviewer
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses=list(executor.map(lambda _:answer(http,task,client_request_id=key),range(2)))
    assert all(r.status_code==201 for r in responses),[r.text for r in responses]
    assert responses[0].json()==responses[1].json()
    assert http.get('/api/v1/tenders/'+tender['id']).json()['input_revision']==3


def test_concurrent_distinct_reviewers_keep_both_answers_and_fence_old_job(client,review_case):
    from concurrent.futures import ThreadPoolExecutor
    from app.m1.reviews import answer_review_task
    from app.m1.models import AnswerReviewTask
    from test_jobs import run_job
    http,current,app=client
    tender,assessment,reviewer,stranger=review_case
    first=confirm(http,tender,assessment,reviewer).json()
    second=confirm(http,tender,assessment,stranger).json()
    def submit(pair):
        task,actor=pair
        return http.portal.call(answer_review_task,app.state.repository,actor,UUID(task['id']),
            AnswerReviewTask(expected_task_revision=1,response_kind='unable_to_confirm',text='Allocation is still being reviewed.',client_request_id=str(uuid4())))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(submit,[(first,reviewer),(second,stranger)]))
    assert sorted(r['input_revision'] for r in results)==[3,4]
    old=min(results,key=lambda r:r['input_revision'])
    newest=max(results,key=lambda r:r['input_revision'])
    run_job(http,app,old['reassessment_job_id'])
    assert http.get('/api/v1/jobs/'+old['reassessment_job_id']).json()['status']=='non_current'
    async def check():
        async with app.state.pool.acquire() as c:
            manifest=json.loads(await c.fetchval('SELECT manifest FROM m1_app.jobs WHERE id=$1',UUID(newest['reassessment_job_id'])))
            assert {a['actor_id'] for a in manifest['review_answers']}=={str(reviewer.user_id),str(stranger.user_id)}
    http.portal.call(check)


def test_answer_after_source_change_keeps_original_question_and_new_job_manifest(client,review_case):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    task=confirm(http,tender,assessment,reviewer).json()
    assert upload(http,tender,revision=2).status_code==201
    current[0]=reviewer
    response=answer(http,task,response_kind='denied',text='I cannot allocate two technicians to that original schedule.')
    assert response.status_code==201,response.text
    async def check():
        async with app.state.pool.acquire() as c:
            row=await c.fetchrow('SELECT input_revision,manifest FROM m1_app.jobs WHERE id=$1',UUID(response.json()['reassessment_job_id']))
            manifest=json.loads(row['manifest'])
            assert row['input_revision']==4
            assert len(manifest['documents'])==2
            evidence=manifest['review_answers'][0]
            assert evidence['response_kind']=='denied'
            assert evidence['source_manifest']['assessment_input_revision']==2
            assert evidence['assessment_version_id']==assessment['id']
    http.portal.call(check)


def test_task_snapshot_keeps_version_references_without_prior_payloads(client,review_case):
    http,_,_=client
    tender,assessment,reviewer,_=review_case
    response=confirm(http,tender,assessment,reviewer)
    assert response.status_code==201,response.text
    assert 'previous_assessment' not in response.json()['manifest']
    assert response.json()['manifest']['assessment_input_revision']==2


def carried_assessment(http,app,tender,assessment,resolved=False,drop_carry=False):
    from copy import deepcopy
    from app.m1.analysis import validate_candidate
    async def seed():
        async with app.state.pool.acquire() as c:
            original=await c.fetchrow('SELECT * FROM m1_app.artifact_versions WHERE id=$1',UUID(assessment['id']))
            previous=json.loads(original['payload'])
            candidate,context=fixture('amended')
            context.update(previous_assessment=previous,workspace_id=str(original['workspace_id']),tender_id=tender['id'],input_revision=2)
            payload=validate_candidate(candidate,context)
            current=payload['requirements'][3]
            if resolved:
                current['requirement'].update(status='met',missing_information=None)
                payload['candidate']['requirements'][3]=deepcopy(current['requirement'])
            if drop_carry: payload['requirements']=[r for r in payload['requirements'] if not r['carried_forward']]
            version=await c.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',2,$3::jsonb,$4::jsonb,$5) RETURNING id",original['workspace_id'],original['tender_id'],original['manifest'],json.dumps(payload),original['created_by'])
            return str(version),current['id']
    version,identity=http.portal.call(seed)
    result=http.get('/api/v1/tenders/'+tender['id']).json()['assessment']
    assert result['id']==version
    return result,identity


def test_carried_local_ref_does_not_pollute_task_scope_or_dedup(client,review_case):
    http,_,app=client
    tender,original,reviewer,_=review_case
    amended,identity=carried_assessment(http,app,tender,original)
    first=confirm(http,tender,amended,reviewer)
    assert first.status_code==201,first.text
    assert first.json()['requirement_ids']==[identity]
    reconciled,_=carried_assessment(http,app,tender,original,drop_carry=True)
    repeated=confirm(http,tender,reconciled,reviewer)
    assert repeated.status_code==201,repeated.text
    assert repeated.json()['id']==first.json()['id']


def test_carried_unknown_cannot_make_resolved_current_draft_actionable(client,review_case):
    http,_,app=client
    tender,original,reviewer,_=review_case
    amended,_=carried_assessment(http,app,tender,original,resolved=True)
    response=confirm(http,tender,amended,reviewer)
    assert response.status_code==422,response.text
    assert response.json()['code']=='DRAFT_RESOLVED'


def test_edited_question_is_validated_and_persisted(client,review_case):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    for invalid in ('   ','x'*2001):
        assert confirm(http,tender,assessment,reviewer,question=invalid).status_code==422
    edited='Can we confirm two qualified technicians for Saturday coverage?'
    response=confirm(http,tender,assessment,reviewer,question=edited)
    assert response.status_code==201,response.text
    assert response.json()['question']==edited
    saved=http.get('/api/v1/tenders/'+tender['id']).json()['review_tasks'][0]
    assert saved['question']==edited


def test_extracted_tender_title_is_used_in_detail_and_inbox(client,review_case):
    http,current,app=client
    tender,assessment,reviewer,_=review_case
    extracted=assessment['candidate']['key_facts']['title']['value']
    assert extracted and extracted!=tender['title']
    assert http.get('/api/v1/tenders/'+tender['id']).json()['title']==extracted
    item=next(row for row in http.get('/api/v1/tenders').json()['items'] if row['id']==tender['id'])
    assert item['title']==extracted


def test_unchanged_review_request_preserves_legacy_retry_identity():
    from app.m1.models import CreateReviewTask
    legacy={
        'expected_assessment_version_id':'11111111-1111-4111-8111-111111111111',
        'draft_ref':'Q1',
        'assignee_id':'22222222-2222-4222-8222-222222222222',
        'due_at':None,
        'client_request_id':'legacy-review-retry',
    }
    command=CreateReviewTask.model_validate(legacy)
    assert command.model_dump_json()==json.dumps(legacy,separators=(',',':'))
