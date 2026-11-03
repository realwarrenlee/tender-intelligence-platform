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
    from app.tenders.screening_workflow import _context
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


def test_overview_adds_labelled_facts_and_competing_terms_without_evicting_gates(retrieval_case):
    from app.tenders.retrieval import SourceIndex
    case=retrieval_case
    docs=[{"filename":f"gate-{i}.pdf","text":f"Critical evaluation criteria {i}: mandatory operating permit at submission."} for i in range(6)]
    docs += [{"filename":"noise.pdf","text":"Maintenance contract period servicing sites "*700},
        {"filename":"a.pdf","text":"Fictional Agency\nTENDER REF: FM-2026\nPROVISION OF INTEGRATED FACILITIES SERVICES"},
        {"filename":"b.pdf","text":"CONTRACT PERIOD\nThe contract is for 72 months, commencing October 2027 subject to the buyer."},
        {"filename":"c.pdf","text":"CONTRACT PERIOD\nStore services are for 60 months plus an optional 36 months."},
        {"filename":"d.pdf","text":"Sites and installations\nNorth Campus, South Campus and Central Waterworks. South may decommission; Central commencement may be delayed."}]
    ctx,_=context(case,docs)
    assert len(ctx["excerpts"])==6
    assert all(e["filename"].startswith("gate-") for e in ctx["excerpts"])
    overview=ctx["overview_excerpts"]
    assert len(json.dumps(overview,ensure_ascii=False).encode())<=5000
    assert {e["filename"] for e in overview}>={"a.pdf","b.pdf","c.pdf","d.pdf"}
    joined=" ".join(e["quote"] for e in overview)
    assert all(s in joined for s in ("FM-2026","72 months","60 months","optional 36","Central Waterworks","delayed"))
    for excerpt in overview:
        assert excerpt["source_role"]=="tender" and excerpt["source_index_version"]==ctx["pins"]["source_index_version"]
        case.http.portal.call(SourceIndex(case.app.state.pool).validate_excerpt,case.actor,excerpt)
    assert ctx["coverage"]["requires_wider_review"]


def test_overview_windows_share_an_anchor_without_joining_text_or_crossing_workspace(retrieval_case,actors):
    from app.tenders.retrieval import SourceIndex
    from app.tenders.policy import DomainError
    case=retrieval_case
    text="Fictional Agency\nTender reference: FM-2026. Critical registration is required before submission.\n"
    text+="Unrelated maintenance description. "*75+"\nCONTRACT PERIOD\n72 months.\n"
    text+="Unrelated maintenance description. "*50+"\nSites and installations\nNorth Campus and South Campus. South commencement may be delayed."
    ctx,_=context(case,[{"filename":"single.pdf","text":text}])
    windows=ctx["overview_excerpts"]
    assert len(windows)>=3 and len({e["anchor_id"] for e in windows})==1
    assert len({e["quote"] for e in windows})==len(windows)
    assert all(e["quote"] in text for e in windows)
    assert len(json.dumps(windows,ensure_ascii=False).encode())<=5000
    with pytest.raises(DomainError) as denied:
        case.http.portal.call(SourceIndex(case.app.state.pool).retrieve_overview,ctx["pins"]["source_index_version"],actors["other"])
    assert denied.value.status_code==404


def test_competing_periods_on_one_native_anchor_get_separate_exact_windows(retrieval_case):
    text="CONTRACT PERIOD\n72 months.\n"+"Other scope description. "*95
    text+="\nCONTRACT PERIOD\nStore services: 60 months plus optional 36 months."
    ctx,_=context(retrieval_case,[{"filename":"terms.pdf","text":text}])
    windows=ctx["overview_excerpts"]
    assert len(windows)==2 and len({e["anchor_id"] for e in windows})==1
    assert any("72 months" in e["quote"] for e in windows)
    assert any("60 months plus optional 36 months" in e["quote"] for e in windows)
    assert all(e["quote"] in text for e in windows)
