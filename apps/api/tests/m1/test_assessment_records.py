import json
from uuid import UUID,uuid4

import pytest

from test_analysis import implemented,fixture,PACK
from test_documents import create,upload
from test_jobs import enqueue


def accept(http,revision=0,key=None):
    return http.post('/api/v1/company-evidence',data={'metadata':json.dumps({
        'expected_evidence_revision':revision,'client_request_id':key or str(uuid4()),'accept':True,
        'effective_on':'2026-01-01','expires_on':'2027-12-31','reason':'Fictional admin-reviewed company profile'})},
        files={'file':('company-profile.pdf',(PACK/'inputs/initial/company-profile.pdf').read_bytes(),'application/pdf')})


class FixtureModel:
    def __init__(self,stage='initial'):
        self.stage=stage
        self.calls=0

    async def generate(self,context,*args):
        self.calls+=1
        candidate,_=fixture(self.stage)
        aliases={}
        roles={'tender-v1':'tender','profile-v1':'company_evidence','addendum-v1':'addendum'}
        for alias,role in roles.items():
            for anchor in context['source_anchors'].values():
                if anchor['source_role']==role: aliases[f"{alias}-p{anchor['page']}"]=anchor['anchor_id']
        for anchor in context['source_anchors'].values():
            if anchor['source_role']=='review_answer': aliases['engineering-answer-v1-note']=anchor['anchor_id']
        def remap(value):
            if isinstance(value,dict): return {k:(aliases[v] if k=='anchor_id' else remap(v)) for k,v in value.items()}
            if isinstance(value,list): return [remap(v) for v in value]
            return value
        return {'candidate':remap(candidate),'model':'controlled-fixture','usage':{'total_tokens':100},'response_id':str(self.calls)}


def process(http,app,job_id,model):
    from app.m1.jobs import run_analysis_job
    return http.portal.call(run_analysis_job,app.state.pool,app.state.storage,UUID(job_id),model)


def prepare(client,actors):
    http,current,app=client
    current[0]=actors['admin']
    response=accept(http)
    assert response.status_code==201,response.text
    current[0]=actors['owner']
    tender=create(http)
    assert upload(http,tender).status_code==201
    job=enqueue(http,tender).json()
    process(http,app,job['id'],FixtureModel())
    view=http.get(f"/api/v1/tenders/{tender['id']}").json()
    return tender,view


def test_company_evidence_is_admin_only_versioned_and_invalidates_tenders(client,actors):
    implemented()
    http,current,app=client
    tender=create(http)
    assert accept(http).status_code==403
    current[0]=actors['admin']
    key=str(uuid4())
    first=accept(http,key=key)
    assert first.status_code==201,first.text
    assert accept(http,key=key).json()==first.json()
    assert first.json()['evidence_revision']==1
    current[0]=actors['owner']
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()['input_revision']==2
    assert http.get('/api/v1/company-evidence').json()['current']['id']==first.json()['id']
    assert http.get('/api/v1/sources/'+first.json()['id']).content.startswith(b'%PDF-')
    current[0]=actors['other']
    assert http.get('/api/v1/sources/'+first.json()['id']).status_code==404


def test_valid_assessment_persists_and_replay_spends_no_more_model_calls(client,actors):
    implemented()
    http,current,app=client
    tender,view=prepare(client,actors)
    assessment=view['assessment']
    assert assessment['candidate']['recommendation']['decision']=='hold'
    assert assessment['is_current']
    assert len(assessment['requirements'])==6
    assert assessment['blockers']
    async def inspect():
        async with app.state.pool.acquire() as connection:
            row=await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE tender_id=$1',UUID(tender['id']))
            manifest=json.loads(row['manifest'])
            assert len(manifest['company_evidence_version_ids'])==1
            assert await connection.fetchval('SELECT count(*) FROM m1_app.analysis_model_calls WHERE job_id=$1',row['id'])==1
            return str(row['id'])
    job_id=http.portal.call(inspect)
    model=FixtureModel()
    process(http,app,job_id,model)
    assert model.calls==0
    assert http.get('/api/v1/jobs/'+job_id).json()['status']=='completed'


def test_correction_is_immutable_attributed_and_survives_rerun(client,actors):
    implemented()
    http,current,app=client
    tender,view=prepare(client,actors)
    assessment=view['assessment']
    requirement=assessment['requirements'][3]
    correction={'expected_assessment_version_id':assessment['id'],'client_request_id':str(uuid4()),
        'reason':'Human checked the available rota',
        'edits':{'requirements':[{'requirement_id':requirement['id'],'status':'unconfirmed',
            'company_citations':requirement['requirement']['company_citations'],
            'explanation':'Human review: rota is still unavailable.','missing_information':'Provide the approved Saturday rota.'}]}}
    response=http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json=correction)
    assert response.status_code==200,response.text
    corrected=response.json()
    assert corrected['id']!=assessment['id']
    assert corrected['created_by']==str(current[0].user_id)
    historical=http.get('/api/v1/assessments/'+assessment['id'])
    assert historical.status_code==200,historical.text
    assert not historical.json()['is_current']
    assert historical.json()['candidate']==assessment['candidate']
    assert http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json=correction).json()==corrected
    assert http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json={**correction,'client_request_id':str(uuid4())}).status_code==409
    job=enqueue(http,tender,revision=corrected['input_revision']).json()
    process(http,app,job['id'],FixtureModel())
    latest=http.get(f"/api/v1/tenders/{tender['id']}").json()['assessment']
    record=next(r for r in latest['requirements'] if r['id']==requirement['id'])
    assert record['requirement']['explanation']=='Human review: rota is still unavailable.'
    assert any(b['code']=='RECONCILIATION_REQUIRED' for b in latest['blockers'])
    assert http.get('/api/v1/jobs/'+job['id']).json()['status']=='needs_input'
    current[0]=actors['other']
    assert http.get('/api/v1/assessments/'+assessment['id']).status_code==404


def test_model_call_reservation_prevents_unknown_outcome_replay(client,actors):
    module=implemented()
    from app.m1.analysis_runtime import ModelLedger
    http,current,app=client
    tender=create(http)
    assert upload(http,tender).status_code==201
    job=enqueue(http,tender).json()
    async def check():
        ledger=ModelLedger(app.state.pool,UUID(job['id']),current[0].workspace_id)
        await ledger.reserve('initial')
        candidate,context=fixture()
        model=FixtureModel()
        with pytest.raises(module.CandidateError): await module.analyse(context,model,ledger)
        assert model.calls==0
    http.portal.call(check)

def test_safe_downgrade_clear_fact_and_late_result_preserve_correction(client,actors):
    from copy import deepcopy
    http,current,app=client
    tender,view=prepare(client,actors)
    original=view['assessment']
    async def publish_positive():
        async with app.state.pool.acquire() as connection:
            row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE id=$1",UUID(original['id']))
            payload=json.loads(row['payload'])
            for req in payload['candidate']['requirements']:
                if req['kind'] in ('eligibility','delivery'): req.update(status='met',missing_information=None)
            payload['candidate']['recommendation']['decision']='pursue'
            for record in payload['requirements']:
                record['requirement']=deepcopy(next(r for r in payload['candidate']['requirements'] if r['local_ref']==record['requirement']['local_ref']))
            payload['blockers']=[]
            return dict(row),payload,await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",row['workspace_id'],row['tender_id'],row['input_revision'],row['manifest'],json.dumps(payload),row['created_by'])
    row,payload,positive=http.portal.call(publish_positive)
    req=payload['requirements'][3]
    response=http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json={
        'expected_assessment_version_id':str(positive),'client_request_id':str(uuid4()),'reason':'Rota evidence is missing',
        'edits':{'requirements':[{'requirement_id':req['id'],'status':'unconfirmed','company_citations':[],
            'explanation':'Rota is missing','missing_information':'Provide rota'}],
            'key_facts':{'buyer':{'value':None,'citations':[]}}}})
    assert response.status_code==200,response.text
    corrected=response.json()
    assert corrected['candidate']['recommendation']['decision']=='hold'
    assert corrected['candidate']['key_facts']['buyer']=={'value':None,'citations':[]}
    async def late():
        async with app.state.pool.acquire() as connection:
            return await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",row['workspace_id'],row['tender_id'],row['input_revision'],row['manifest'],json.dumps(payload),row['created_by'])
    late_id=http.portal.call(late)
    assert http.get('/api/v1/assessments/'+str(late_id)).json()['is_current'] is False
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()['assessment']['id']==corrected['id']
    job=enqueue(http,tender,revision=corrected['input_revision']).json()
    async def pinned():
        async with app.state.pool.acquire() as connection:
            return json.loads(await connection.fetchval('SELECT manifest FROM m1_app.jobs WHERE id=$1',UUID(job['id'])))
    assert http.portal.call(pinned)['previous_assessment_version_id']==corrected['id']


def test_duplicate_inflight_and_stale_attempt_model_reservations_are_refused(client,actors):
    from app.m1.analysis_runtime import ModelLedger
    from app.m1.policy import DomainError
    http,current,app=client
    tender=create(http)
    assert upload(http,tender).status_code==201
    job=enqueue(http,tender).json()
    async def check():
        ledger=ModelLedger(app.state.pool,UUID(job['id']),current[0].workspace_id)
        await ledger.reserve('initial')
        with pytest.raises(DomainError): await ledger.reserve('initial')
        async with app.state.pool.acquire() as connection:
            await connection.execute("UPDATE m1_app.analysis_model_calls SET state='transient_failure' WHERE job_id=$1",UUID(job['id']))
            await connection.execute("UPDATE m1_app.jobs SET attempt=2 WHERE id=$1",UUID(job['id']))
        stale=ModelLedger(app.state.pool,UUID(job['id']),current[0].workspace_id,expected_attempt=1)
        with pytest.raises(DomainError): await stale.reserve('initial')
    http.portal.call(check)


def test_unrelated_reconciliation_mapping_cannot_remove_an_obligation(client,actors):
    http,current,app=client
    tender,view=prepare(client,actors)
    assessment=view['assessment']
    old,target=assessment['requirements'][3],assessment['requirements'][0]
    async def carry():
        async with app.state.pool.acquire() as connection:
            payload=json.loads(await connection.fetchval('SELECT payload FROM m1_app.artifact_versions WHERE id=$1',UUID(assessment['id'])))
            payload['candidate']['requirements']=[r for r in payload['candidate']['requirements'] if r['local_ref']!=old['requirement']['local_ref']]
            payload['candidate']['review_requests']=[]
            payload['candidate']['recommendation']['condition_refs']=[]
            payload['reconciliation']=[{'kind':'missing_or_changed','requirement_id':old['id'],'resolved':False,'previous_requirement':old['requirement']}]
            # Seed immutable fixture history through a new row, never update a version.
            row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE id=$1",UUID(assessment['id']))
            return await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",row['workspace_id'],row['tender_id'],row['input_revision'],row['manifest'],json.dumps(payload),row['created_by'])
    version=http.portal.call(carry)
    response=http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json={
        'expected_assessment_version_id':str(version),'client_request_id':str(uuid4()),'reason':'Fictional unrelated replacement',
        'edits':{'reconciliations':[{'previous_requirement_id':old['id'],'replacement_requirement_ids':[target['id']],
            'citations':old['requirement']['tender_citations']+target['requirement']['tender_citations']}]}})
    assert response.status_code==422,response.text
    assert response.json()['code']=='INVALID_RECONCILIATION'

def test_explicit_same_clause_resolution_persists_across_analysis(client,actors):
    from copy import deepcopy
    from app.m1.analysis import validate_candidate
    http,current,app=client
    tender,view=prepare(client,actors)
    assessment=view['assessment']
    async def changed():
        async with app.state.pool.acquire() as connection:
            row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE id=$1",UUID(assessment['id']))
            payload=json.loads(row['payload'])
            candidate=deepcopy(payload['candidate'])
            candidate['requirements'][3]['text']+=' Clarified wording.'
            context={**payload['context'],'previous_assessment':payload}
            result=validate_candidate(candidate,context)
            return result,await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",row['workspace_id'],row['tender_id'],row['input_revision'],row['manifest'],json.dumps(result),row['created_by'])
    payload,version=http.portal.call(changed)
    req=payload['requirements'][3]
    response=http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json={
        'expected_assessment_version_id':str(version),'client_request_id':str(uuid4()),'reason':'Same source clause; wording reviewed.',
        'edits':{'reconciliations':[{'previous_requirement_id':req['id'],'replacement_requirement_ids':[req['id']],
            'citations':req['requirement']['tender_citations']}]}})
    assert response.status_code==200,response.text
    assert not any(b['code']=='RECONCILIATION_REQUIRED' for b in response.json()['blockers'])
    async def reread():
        async with app.state.pool.acquire() as connection:
            return json.loads(await connection.fetchval('SELECT payload FROM m1_app.artifact_versions WHERE id=$1',UUID(response.json()['id'])))
    resolved=http.portal.call(reread)
    result=validate_candidate(deepcopy(resolved['candidate']),{**resolved['context'],'previous_assessment':resolved})
    assert not any(b['code']=='RECONCILIATION_REQUIRED' for b in result['blockers'])
    assert result['reconciliation'][0]['resolved']


def test_amendment_mapping_accepts_both_original_and_replacement_clauses(client,actors):
    http,_,app=client
    tender,view=prepare(client,actors)
    old=view['assessment']['requirements'][3]
    response=http.post(f"/api/v1/tenders/{tender['id']}/documents",
        data={'metadata':json.dumps({'expected_input_revision':2,'client_request_id':str(uuid4()),
          'files':[{'role':'addendum','amends_version_id':view['documents'][0]['id']}]})},
        files=[('files',('addendum.pdf',(PACK/'inputs/updates/addendum.pdf').read_bytes(),'application/pdf'))])
    assert response.status_code==201,response.text
    job=enqueue(http,tender,revision=3).json()
    class AmendmentModel(FixtureModel):
        async def generate(self,context,*args):
            result=await super().generate(context,*args)
            changed=fixture('amended')[0]['requirements'][3]
            result['candidate']['requirements'][3]={**changed,'company_citations':[],
                'tender_citations':[{'anchor_id':next(a['anchor_id'] for a in context['source_anchors'].values() if a['source_role']=='addendum'),
                                    'quote':changed['tender_citations'][0]['quote']}]}
            return result
    process(http,app,job['id'],AmendmentModel())
    assessment=http.get(f"/api/v1/tenders/{tender['id']}").json()['assessment']
    target=next(r for r in assessment['requirements'] if 'three' in r['requirement']['text'].lower() and not r['carried_forward'])
    citations=old['requirement']['tender_citations']+target['requirement']['tender_citations']
    command={'expected_assessment_version_id':assessment['id'],'client_request_id':str(uuid4()),
        'reason':'Original staffing clause explicitly replaced by the uploaded addendum.',
        'edits':{'reconciliations':[{'previous_requirement_id':old['id'],'replacement_requirement_ids':[target['id']],'citations':citations}]}}
    result=http.patch(f"/api/v1/tenders/{tender['id']}/assessment",json=command)
    assert result.status_code==200,result.text
    assert any(r['resolved'] and r['requirement_id']==old['id'] for r in result.json()['reconciliation'])
    assert target['requirement']['status']=='unconfirmed'
