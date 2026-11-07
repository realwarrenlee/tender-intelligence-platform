import json
from uuid import uuid4

from test_analysis import implemented,PACK
from test_documents import create


def accept(http,revision=0,key=None):
    return http.post('/api/v1/company-evidence',data={'metadata':json.dumps({
        'expected_evidence_revision':revision,'client_request_id':key or str(uuid4()),'accept':True,
        'effective_on':'2026-01-01','expires_on':'2027-12-31','reason':'Fictional admin-reviewed company profile'})},
        files={'file':('company-profile.pdf',(PACK/'inputs/initial/company-profile.pdf').read_bytes(),'application/pdf')})


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
