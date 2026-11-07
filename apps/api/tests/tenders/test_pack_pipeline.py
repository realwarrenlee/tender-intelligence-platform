from test_documents import create,upload,PDF


def test_mixed_pack_capacity_and_pending_inventory_are_visible(client):
    http,_,_=client
    tender=create(http)
    response=upload(http,tender,files=[(f'source{i}.pdf',PDF.read_bytes(),'application/pdf') for i in range(11)])
    assert response.status_code==201,response.text
    coverage=http.get(f"/api/v1/tenders/{tender['id']}").json()['source_coverage']
    assert coverage['total_files']==11 and coverage['pending_files']==11
    assert not coverage['complete']
