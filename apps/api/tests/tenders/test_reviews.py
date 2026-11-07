from datetime import datetime,timezone
import json

import pytest


@pytest.mark.parametrize('closing,expected',[
    ('2026-11-05T10:00:00+00:00','2026-11-03T10:00:00+00:00'),
    ('2026-11-02T22:00:00+00:00','2026-11-01T22:00:00+00:00'),
    ('2026-11-01T20:00:00+00:00','2026-11-01T10:00:00+00:00'),
])
def test_default_due_uses_utc_formula(closing,expected):
    from app.tenders import reviews
    assert reviews.default_due_at(datetime.fromisoformat('2026-11-01T10:00:00+00:00'),datetime.fromisoformat(closing))==datetime.fromisoformat(expected)


@pytest.mark.parametrize('closing',[None,datetime(2026,10,1,tzinfo=timezone.utc),datetime(2026,12,1)])
def test_default_due_refuses_unknown_past_or_naive_closing(closing):
    from app.tenders import reviews
    from app.tenders.policy import DomainError
    with pytest.raises(DomainError):
        reviews.default_due_at(datetime(2026,11,1,tzinfo=timezone.utc),closing)


def test_unchanged_review_request_preserves_legacy_retry_identity():
    from app.tenders.models import CreateReviewTask
    legacy={
        'expected_assessment_version_id':'11111111-1111-4111-8111-111111111111',
        'draft_ref':'Q1',
        'assignee_id':'22222222-2222-4222-8222-222222222222',
        'due_at':None,
        'client_request_id':'legacy-review-retry',
    }
    command=CreateReviewTask.model_validate(legacy)
    assert command.model_dump_json()==json.dumps(legacy,separators=(',',':'))
