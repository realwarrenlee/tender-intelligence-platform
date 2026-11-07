from uuid import uuid4

from test_screening_workflow import screening_case as screening_case


def test_member_directory_is_scoped_and_has_no_secret_profile_data(client,actors):
    http,current,_=client
    response=http.get('/api/v1/members')
    assert response.status_code==200,response.text
    members=response.json()['items']
    assert {str(actors[x].user_id) for x in ('owner','viewer','admin','approver')}=={m['user_id'] for m in members}
    assert all(set(m)=={'user_id','display_name','roles'} for m in members)
    current[0]=actors['other']
    assert str(actors['owner'].user_id) not in {m['user_id'] for m in http.get('/api/v1/members').json()['items']}


def test_old_screening_without_overview_remains_readable_and_source_scoped(screening_case,actors):
    from uuid import UUID
    from test_opportunities import db
    c=screening_case
    version=str(db(c.http,c.app,"""INSERT INTO m1_app.artifact_versions
        (workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
        SELECT workspace_id,tender_id,kind,input_revision,manifest,payload-'summary',created_by
        FROM m1_app.artifact_versions WHERE id=$1 RETURNING id""",UUID(c.review['screening']['id']))[0]['id'])
    c.current[0]=actors['viewer']
    response=c.http.get('/api/v1/review-cases/'+c.tender['id'])
    assert response.status_code==200,response.text
    assert response.json()['screening']['artifact']['summary'] is None
    url='/api/v1/assessments/'+version+'/sources'
    sources=c.http.get(url)
    assert sources.status_code==200 and sources.json()['anchors']
    assert all('storage_key' not in anchor for anchor in sources.json()['anchors'])
    c.current[0]=actors['other']
    assert c.http.get(url).status_code==404

def test_new_tender_history_is_available_before_analysis(client):
    http,_,_=client
    tender=http.post('/api/v1/tenders',json={'title':'New unassessed tender','client_request_id':str(uuid4())}).json()
    response=http.get('/api/v1/tenders/'+tender['id']+'/history')
    assert response.status_code==200,response.text
    assert response.json()['assessments']==[] and response.json()['decisions']==[]
