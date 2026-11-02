"""Default screening must deliver decision facets despite keyword-heavy material."""
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from test_documents import create
from test_opportunities import db
from test_retrieval import seed_parsed


@pytest.fixture
def retrieval_case(client, actors):
    http, _, app = client
    app.state.qualification_enabled = True
    case = SimpleNamespace(http=http, app=app, actor=actors["owner"], tender=create(http))
    db(http, app, """INSERT INTO m1_app.workspace_spending_policies
        (workspace_id,daily_limit_usd,approved_by) VALUES($1,5,$2) RETURNING workspace_id""",
        case.actor.workspace_id, case.actor.user_id)
    db(http, app, """INSERT INTO m1_app.stage_budgets
        (workspace_id,tender_id,stage,scope_key,limit_usd,max_requests,max_responses_requests,
         max_input_tokens,approved_by) VALUES($1,$2,'screening',$3,0.5,8,2,200000,$4) RETURNING id""",
        case.actor.workspace_id, UUID(case.tender["id"]), "tender:" + case.tender["id"], case.actor.user_id)
    return case


def context(case, documents, queries=None):
    from app.m1.screening_workflow import _context
    case.http.portal.call(seed_parsed, case, documents)
    response = case.http.post("/api/v1/tenders/" + case.tender["id"] + "/screenings", json={
        "expected_input_revision": 1, "client_request_id": str(uuid4()),
        **({"investigation_queries": queries} if queries else {}),
    })
    assert response.status_code == 202, response.text
    job = db(case.http, case.app, "SELECT * FROM m1_app.jobs WHERE id=$1",
             UUID(response.json()["id"]))[0]
    return case.http.portal.call(_context, case.app.state.pool, case.app.state.storage,
                                 case.actor, job), job


def test_default_context_finds_gate_score_finance_and_date_amid_keyword_noise(retrieval_case):
    case = retrieval_case
    texts = {
        "quantities.xlsx": "registration guarantee submission evaluation mobilisation " * 220,
        "rates-annex.xlsx": "Critical evaluation criteria: the X-17 operating permit is required at submission.",
        "attributes.docx": "A quality score below 65 points excludes the offer.",
        "accounts.pdf": "Positive net worth is required for award.",
        "letter.pdf": "The closing deadline is 28 November 2099 at 16:00 Singapore time.",
    }
    ctx, job = context(case, [{"filename": name, "text": text} for name, text in texts.items()])
    selected = {e["filename"]: e["quote"] for e in ctx["excerpts"]}
    for name in ("rates-annex.xlsx", "attributes.docx", "accounts.pdf", "letter.pdf"):
        assert name in selected and texts[name] in selected[name]
    assert len(ctx["excerpts"]) <= 6
    assert len(json.loads(job["manifest"])["queries"]) <= 3
    # Native completeness must not clear the unread/partially selected noise.
    assert ctx["coverage"]["requires_wider_review"]


def test_one_focus_cannot_consume_every_excerpt_before_later_facets(retrieval_case):
    case = retrieval_case
    docs = [{"filename": f"permit-{i}.pdf", "text": f"Operating permit rule {i}. "} for i in range(8)]
    docs += [
        {"filename": "quality.pdf", "text": "A quality score below 65 points excludes the offer."},
        {"filename": "deadline.pdf", "text": "The closing deadline is 28 November 2099 at 16:00."},
    ]
    ctx, _ = context(case, docs, ["operating permit", "quality score", "closing deadline"])
    names = [e["filename"] for e in ctx["excerpts"]]
    assert "quality.pdf" in names and "deadline.pdf" in names
    assert len(names) == len(set(names)) == 6
    assert ctx["coverage"]["requires_wider_review"]
