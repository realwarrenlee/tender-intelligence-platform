from uuid import uuid4

from test_reviews import review_case as review_case


def test_member_directory_is_scoped_and_has_no_secret_profile_data(client,actors):
    http,current,_=client
    response=http.get('/api/v1/members')
    assert response.status_code==200,response.text
    members=response.json()['items']
    assert {str(actors[x].user_id) for x in ('owner','viewer','admin','approver')}=={m['user_id'] for m in members}
    assert all(set(m)=={'user_id','display_name','roles'} for m in members)
    current[0]=actors['other']
    assert str(actors['owner'].user_id) not in {m['user_id'] for m in http.get('/api/v1/members').json()['items']}


def test_pinned_source_navigation_and_history_are_tenant_scoped(client,review_case,actors):
    http,current,_=client
    tender,assessment,_,_=review_case
    url='/api/v1/assessments/'+assessment['id']+'/sources'
    response=http.get(url)
    assert response.status_code==200,response.text
    anchors=response.json()['anchors']
    assert anchors and any(a['source_role']=='tender' and a['page']==1 for a in anchors)
    assert all('storage_key' not in a for a in anchors)
    history=http.get('/api/v1/tenders/'+tender['id']+'/history')
    assert history.status_code==200,history.text
    assert history.json()['assessments'][0]['id']==assessment['id']
    view=http.get('/api/v1/tenders/'+tender['id']).json()
    assert view['jobs']==[]
    current[0]=actors['other']
    assert http.get(url).status_code==404
    assert http.get('/api/v1/tenders/'+tender['id']+'/history').status_code==404


def test_history_preserves_superseded_human_decision_currency(client,review_case,actors):
    http,current,_=client
    tender,assessment,_,_=review_case
    current[0]=actors['approver']
    for decision in ('hold','decline'):
        response=http.post('/api/v1/tenders/'+tender['id']+'/decisions',json={
            'expected_input_revision':2,'assessment_version_id':assessment['id'],'decision':decision,
            'reason':'Fictional historical human decision.','review_complete':True,'client_request_id':str(uuid4())})
        assert response.status_code==201,response.text
    response=http.get('/api/v1/tenders/'+tender['id']+'/history')
    assert response.status_code==200,response.text
    decisions=response.json()['decisions']
    assert [d['decision'] for d in decisions]==['decline','hold']
    assert decisions[0]['is_current'] and not decisions[1]['is_current']
    assert decisions[1]['currency_reason']=='DECISION_SUPERSEDED'


def test_new_tender_history_is_available_before_analysis(client):
    http,_,_=client
    tender=http.post('/api/v1/tenders',json={'title':'New unassessed tender','client_request_id':str(uuid4())}).json()
    response=http.get('/api/v1/tenders/'+tender['id']+'/history')
    assert response.status_code==200,response.text
    assert response.json()['assessments']==[] and response.json()['decisions']==[]



def test_browser_reads_do_not_transfer_private_snapshot_bodies(client,review_case):
    from contextlib import asynccontextmanager
    from uuid import UUID

    http,current,app=client
    tender,assessment,_,_=review_case

    async def seed():
        async with app.state.pool.acquire() as c:
            version=await c.fetchval("""
                INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
                SELECT workspace_id,tender_id,kind,input_revision,
                    manifest || jsonb_build_object('previous_assessment',repeat('x',2000000)),
                    jsonb_set(payload,'{context,previous_assessment}',to_jsonb(repeat('x',2000000))),created_by
                FROM m1_app.artifact_versions WHERE id=$1 RETURNING id
            """,UUID(assessment['id']))
            job=await c.fetchval("""
                INSERT INTO m1_app.jobs(workspace_id,tender_id,input_revision,manifest,status,created_by)
                VALUES($1,$2,2,jsonb_build_object('previous_assessment',repeat('x',2000000)),'completed',$3)
                RETURNING id
            """,current[0].workspace_id,UUID(tender['id']),current[0].user_id)
            return version,job
    version,job=http.portal.call(seed)
    transferred=[]

    class RecordingConnection:
        def __init__(self,connection):
            self.connection=connection

        def __getattr__(self,name):
            method=getattr(self.connection,name)
            if name not in ('fetch','fetchrow','fetchval'): return method
            async def read(*args,**kwargs):
                result=await method(*args,**kwargs)
                transferred.append(len(str(result).encode()))
                return result
            return read

    class RecordingPool:
        @asynccontextmanager
        async def acquire(self):
            async with app.state.pool.acquire() as c:
                yield RecordingConnection(c)

    app.state.repository.pool=RecordingPool()
    detail=http.get('/api/v1/tenders/'+tender['id'])
    history=http.get('/api/v1/tenders/'+tender['id']+'/history')
    inbox=http.get('/api/v1/tenders')
    historical=http.get('/api/v1/assessments/'+str(version))
    for response in (detail,history,inbox,historical):
        assert response.status_code==200,response.text
    assert detail.json()['assessment']['candidate']==assessment['candidate']
    assert detail.json()['jobs'][0]['id']==str(job)
    assert history.json()['assessments'][0]['id']==str(version)
    assert historical.json()['is_current']
    assert inbox.json()['items'][0]['assessment_status']=='current'
    assert sum(transferred)<250000, f'Browser reads transferred {sum(transferred)} database bytes'
