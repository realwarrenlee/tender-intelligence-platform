
from test_analysis import implemented,fixture


def test_expired_company_evidence_blocks_pursue_at_closing_date():
    module=implemented()
    candidate,context=fixture('answered')
    candidate['recommendation']['decision']='hold'
    context['evidence_dates']['profile-v1']['expires_on']='2026-11-01'
    result=module.validate_candidate(candidate,context)
    assert any(b['code']=='EVIDENCE_EXPIRED' for b in result['blockers'])


def test_unknown_or_closed_deadline_blocks_pursue():
    module=implemented()
    candidate,context=fixture('answered')
    candidate['recommendation']['decision']='hold'
    context['as_of']='2026-12-01T00:00:00+08:00'
    result=module.validate_candidate(candidate,context)
    assert any(b['code']=='CLOSING_PASSED' for b in result['blockers'])
    candidate['key_facts']['closing_at']={'value':None,'citations':[]}
    result=module.validate_candidate(candidate,context)
    assert any(b['code']=='CLOSING_UNKNOWN' for b in result['blockers'])


def test_submission_artifacts_do_not_block_qualification():
    module=implemented()
    candidate,context=fixture('answered')
    result=module.validate_candidate(candidate,context)
    assert not result['blockers']
    assert len([r for r in result['requirements'] if r['requirement']['status']=='not_assessed'])==2


def test_evidence_effective_today_uses_workspace_calendar_date():
    module=implemented()
    candidate,context=fixture('answered')
    context['as_of']='2026-10-23T18:00:00+00:00'
    context['evidence_dates']['profile-v1']['effective_on']='2026-10-24'
    result=module.validate_candidate(candidate,context)
    assert not result['blockers']


def test_evidence_expiry_uses_workspace_date_for_a_utc_closing_value():
    module=implemented()
    candidate,context=fixture('answered')
    candidate['recommendation']['decision']='hold'
    candidate['key_facts']['closing_at']['value']='2026-11-19T22:00:00+00:00'
    context['evidence_dates']['profile-v1']['expires_on']='2026-11-19'
    result=module.validate_candidate(candidate,context)
    assert any(b['code']=='EVIDENCE_EXPIRED' for b in result['blockers']), 'Closing is 20 November in Singapore; evidence expiring on the 19th is insufficient.'
