from uuid import UUID, uuid4
import io
import zipfile

from test_documents import create

PROFILE = {
    'content': '# CBM Pte. Ltd.\n\nCBM is a Singapore facilities management company.\nEngineering and facilities maintenance.\nCurrent staff availability needs confirmation.',
    'sources': [{'title': 'BCA company record', 'url': 'https://www.bca.gov.sg/eBACS/BCA_DIRECTORY/Company/CompanyDetails?uenNo=197100922N',
                 'publisher': 'BCA', 'checked_on': '2026-10-28'}],
}


def command(revision=0, **updates):
    return {'expected_evidence_revision': revision, 'client_request_id': str(uuid4()),
            'accept': True, 'effective_on': '2026-10-28', 'reason': 'Reviewed shared company knowledge',
            'profile': PROFILE, **updates}


def test_company_profile_admin_save_replay_history_and_assessment_source(client, actors):
    http, current, app = client
    tender = create(http)
    body = command()
    # The server's current membership wins over a forged client admin role.
    current[0] = actors['owner'].model_copy(update={'roles': {'admin'}})
    assert http.post('/api/v1/company-evidence/profile', json=body).status_code == 403
    current[0] = actors['admin']
    first = http.post('/api/v1/company-evidence/profile', json=body)
    assert first.status_code == 201, first.text
    assert first.json()['evidence_revision'] == 1
    assert http.post('/api/v1/company-evidence/profile', json=body).json() == first.json()
    view = http.get('/api/v1/company-evidence').json()
    assert view['current']['profile'] == PROFILE
    assert view['current']['created_by'] == str(actors['admin'].user_id)
    assert view['current']['created_at']
    assert view['history'][0]['id'] == first.json()['id']
    source = http.get('/api/v1/sources/' + first.json()['id']).json()
    assert any(PROFILE['content'].splitlines()[0] in anchor['text'] for anchor in source['anchors'])
    assert any(PROFILE['sources'][0]['url'] in anchor['text'] for anchor in source['anchors'])
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()['input_revision'] == 2
    assert http.post('/api/v1/company-evidence/profile', json=command()).status_code == 409
    second = http.post('/api/v1/company-evidence/profile', json=command(1, profile={**PROFILE, 'content': 'Updated by admin'}))
    assert second.status_code == 201, second.text
    view = http.get('/api/v1/company-evidence').json()
    assert len(view['history']) == 2
    historical = http.get('/api/v1/company-evidence/versions/' + first.json()['id'])
    assert historical.status_code == 200, historical.text
    assert historical.json()['profile'] == PROFILE
    assert historical.json()['evidence_revision'] == 1

    assert view['history'][1]['id'] == first.json()['id']
    current[0] = actors['viewer']
    assert http.get('/api/v1/company-evidence/versions/' + first.json()['id']).status_code == 200

    assert http.get('/api/v1/company-evidence').json()['current']['profile']['content'] == 'Updated by admin'
    assert http.post('/api/v1/company-evidence/profile', json=command(2)).status_code == 403
    current[0] = actors['other']
    assert http.get('/api/v1/company-evidence/versions/' + first.json()['id']).status_code == 404

    assert http.get('/api/v1/company-evidence').json()['current'] is None
    assert http.get('/api/v1/sources/' + first.json()['id']).status_code == 404


def test_company_profile_validates_content_links_and_deterministic_document():
    import pytest
    from pydantic import ValidationError
    from app.tenders.models import SaveCompanyProfile
    from app.tenders.assessments import profile_document, company_profile
    legacy = company_profile({'profile': {'overview': 'Original overview', 'capabilities': 'Original capabilities',
                                           'track_record': 'Original history', 'notes': 'Original notes', 'sources': PROFILE['sources']}})
    assert all(value in legacy['content'] for value in ['Original overview', 'Original capabilities', 'Original history', 'Original notes'])
    assert legacy['sources'] == PROFILE['sources']
    model = SaveCompanyProfile.model_validate(command())
    document = profile_document(model.profile)
    assert document == profile_document(model.profile)
    with zipfile.ZipFile(io.BytesIO(document)) as archive:
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
    for profile in ({**PROFILE, 'content': '   '},
                    {**PROFILE, 'sources': [{**PROFILE['sources'][0], 'url': 'javascript:alert(1)'}]}):
        with pytest.raises(ValidationError):
            SaveCompanyProfile.model_validate(command(profile=profile))
