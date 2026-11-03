from uuid import UUID, uuid4

import pytest

from test_screening_workflow import Decisions, Reasoner, confirm, decide, make_ready, screening_case
from test_opportunities import db


def command(approval_id, **fields):
    return dict(client_request_id=str(uuid4()), approval_id=approval_id, **fields)


@pytest.fixture
def preparation(screening_case, actors):
    case = screening_case
    make_ready(case)
    task = confirm(case, "preparation", actors["approver"]).json()
    case.current[0] = actors["approver"]
    result = decide(case, task)
    assert result.status_code == 201, result.text
    case.current[0] = case.actor
    case.approval = result.json()["id"]
    case.app.state.preparation_enabled = True
    case.url = f"/api/v1/tenders/{case.tender['id']}/preparation"
    return case


def create(case, owner, kind="technical_response", **overrides):
    return command(case.approval, **{
        "kind": kind, "owner_id": str(owner.user_id), "reviewer_id": str(case.reviewer.user_id),
        "due_at": "2098-12-29T09:00:00+08:00", "finding_ids": ["registration"], **overrides,
    })


def test_deliverables_require_current_approval_and_named_members(preparation, actors):
    c = preparation
    body = create(c, actors["owner"])
    assert c.http.get(c.url).json()["items"] == []
    assert c.http.post(c.url, json={**body, "approval_id": str(uuid4())}).status_code == 409
    assert c.http.post(c.url, json={**body, "finding_ids": ["other-tender"]}).status_code == 422
    assert c.http.post(c.url, json={**body, "due_at": "2099-01-02T09:00:00+08:00"}).status_code == 422
    assert c.http.post(c.url, json={**body, "reviewer_id": str(actors["viewer"].user_id)}).status_code == 422
    for actor in (actors["admin"], actors["viewer"], actors["other"]):
        c.current[0] = actor
        assert c.http.post(c.url, json=body).status_code in (403, 404)
    assert c.http.get(c.url).status_code == 404
    c.current[0] = c.actor
    c.app.state.preparation_enabled = False
    assert c.http.post(c.url, json=body).status_code == 409
    c.app.state.preparation_enabled = True
    response = c.http.post(c.url, json=body)
    assert response.status_code == 201, response.text
    assert c.http.post(c.url, json=body).json() == response.json()
    assert c.http.post(c.url, json={**body, "due_at": "2098-12-29T10:00:00+08:00"}).status_code == 409
    assert c.http.post(c.url, json=create(c, actors["approver"], "pricing_workbook")).status_code == 201
    items = c.http.get(c.url).json()["items"]
    assert len(items) == 2 and {item["status"] for item in items} == {"draft"}
    assert items[0]["findings"][0]["citations"]
    assert any(action["kind"] == "preparation_deliverable" for action in
               c.http.get("/api/v1/inbox-actions").json()["items"])
    team = c.http.get("/api/v1/review-cases").json()["items"][0]
    assert team["state"] == "Completed" and team["tender_stage"] == "preparing_bid"
    assert team["preparation"] == {"total": 2, "accepted": 0, "pending_reviews": 0, "non_current": 0}


def test_reviews_pin_working_versions_and_survive_amendment(preparation, actors):
    import io
    import json
    from pypdf import PdfWriter

    c = preparation
    created = c.http.post(c.url, json=create(c, actors["approver"]))
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    item_url = c.url + "/" + item_id
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    writer.write(output)
    pdf = output.getvalue()

    def upload(revision, data=pdf, metadata=None):
        return c.http.post(item_url + "/files", data={"metadata": json.dumps(
            metadata or command(c.approval, expected_revision=revision))},
            files={"file": ("response.pdf", data, "application/pdf")})

    def act(action, revision, **fields):
        return c.http.post(item_url + "/actions", json=command(
            c.approval, action=action, expected_revision=revision, **fields))

    assert upload(1).status_code == 403
    c.current[0] = actors["approver"]
    meta = command(c.approval, expected_revision=1)
    first = upload(1, metadata=meta)
    assert first.status_code == 201, first.text
    assert upload(1, metadata=meta).json() == first.json()
    assert upload(1).status_code == 409
    version = first.json()["id"]
    assert act("request_review", 2, note="Check coverage of the technical obligations.").status_code == 201
    assert act("accept", 3, note="Self approval").status_code == 403
    c.current[0] = c.reviewer
    actions = c.http.get("/api/v1/inbox-actions").json()["items"]
    assert any(action["kind"] == "preparation_review" and action["task_id"] == item_id for action in actions)
    next_action = c.http.get("/api/v1/review-cases").json()["items"][0]["next_action"]
    assert next_action["task_id"] == item_id and next_action["section"] == "preparation"
    assert next_action["assignee_id"] == str(c.reviewer.user_id)
    assert c.http.get("/api/v1/review-cases/" + c.tender["id"]).json()["preparation"]["pending_reviews"] == 1
    assert act("accept", 2, note="Old screen").status_code == 409
    assert act("accept", 3, note="Verified the technical response against the requirements.").status_code == 201
    assert c.http.get(c.url).json()["items"][0]["status"] == "accepted"
    assert c.http.get("/api/v1/review-cases/" + c.tender["id"]).json()["preparation"]["accepted"] == 1
    c.current[0] = actors["approver"]
    assert upload(4, pdf + b"\n").status_code == 201
    assert c.http.get(c.url).json()["items"][0]["status"] == "draft"
    assert act("request_review", 5, note="Check the revised technical response.").status_code == 201
    db(c.http, c.app, "UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1 RETURNING id", UUID(c.tender["id"]))
    c.current[0] = c.reviewer
    assert act("accept", 6, note="Stale approval").status_code == 409
    c.app.state.preparation_enabled = False
    c.current[0] = actors["viewer"]
    item = c.http.get(c.url).json()["items"][0]
    assert item["status"] == "non_current" and not item["permitted_actions"]
    assert len(item["files"]) == len(item["reviews"]) == 2
    assert not any(review["is_current"] for review in item["reviews"])
    file_url = item_url + "/files/" + version
    assert c.http.get(file_url).content == pdf
    c.current[0] = actors["other"]
    assert c.http.get(file_url).status_code == 404
    assert c.http.get("/api/v1/tenders/" + c.tender["id"]).status_code == 404

    # A new approval restores the bid owner's ability to reconfirm, not the old review's currency.
    c.app.state.preparation_enabled = True
    c.current[0] = c.actor
    start = c.http.post("/api/v1/tenders/" + c.tender["id"] + "/screenings", json={
        "expected_input_revision": c.review["input_revision"] + 1, "client_request_id": str(uuid4())})
    assert start.status_code == 202, start.text
    c.http.portal.call(c.run, c.app.state.pool, c.app.state.storage, UUID(start.json()["id"]), Decisions(), Reasoner())
    c.review = c.http.get("/api/v1/review-cases/" + c.tender["id"]).json()
    task = confirm(c, "preparation", actors["approver"]).json()
    c.current[0] = actors["approver"]
    approved = decide(c, task)
    assert approved.status_code == 201, approved.text
    c.approval = approved.json()["id"]
    assert act("request_review", 6, note="The item is still pinned to the old approval.").status_code == 409
    c.current[0] = c.actor
    assert any(action["kind"] == "preparation_reconfirm" and action["can_act"] for action in
               c.http.get("/api/v1/inbox-actions").json()["items"])
    assert act("reconfirm", 6, due_at="2098-12-28T09:00:00+08:00", finding_ids=[],
               owner_id=str(actors["approver"].user_id), reviewer_id=str(c.reviewer.user_id)).status_code == 201
    result = c.http.get(c.url).json()["items"][0]
    assert result["status"] == "draft" and len(result["files"]) == len(result["reviews"]) == 2
    assert not any(review["is_current"] for review in result["reviews"])
    assert result["findings"] == []
    assert result["previous_plans"][0]["findings"][0]["id"] == "registration"
    assert result["previous_plans"][0]["screening_version_id"] != result["screening_version_id"]
    assert [row["filename"] for row in db(c.http, c.app,
        "SELECT filename FROM m1_app.document_versions WHERE tender_id=$1", UUID(c.tender["id"]))] == ["instructions.pdf"]


def test_bid_owner_can_reassign_work_without_inheriting_review(preparation, actors):
    c = preparation
    created = c.http.post(c.url, json=create(c, actors["approver"])).json()
    db(c.http, c.app, "UPDATE m1_app.memberships SET roles=ARRAY['viewer'] WHERE user_id=$1 RETURNING user_id",
       c.reviewer.user_id)
    body = command(c.approval, action="update_plan", expected_revision=1, due_at="2098-12-28T10:00:00+08:00",
                   owner_id=str(actors["approver"].user_id), reviewer_id=str(actors["admin"].user_id),
                   finding_ids=["registration"])
    result = c.http.post(c.url + "/" + created["id"] + "/actions", json=body)
    assert result.status_code == 201, result.text
    item = c.http.get(c.url).json()["items"][0]
    assert item["reviewer_id"] == str(actors["admin"].user_id)
    assert item["previous_plans"][0]["reviewer_id"] == str(c.reviewer.user_id)
