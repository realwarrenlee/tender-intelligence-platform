from datetime import date
from io import BytesIO
import json
from uuid import UUID, uuid4

from docx import Document

from app.tenders.proposal import reusable_wording
from test_opportunities import db
from test_preparation_tracking import command, create, preparation
from test_screening_workflow import confirm, decide, make_ready, screening_case


def accepted_payload(expires_on="2099-12-31"):
    return {
        "effective_on": "2020-01-01", "expires_on": expires_on,
        "document": {"filename": "company.docx", "storage_key": "controlled-test-fixture", "sha256": "a" * 64},
        "parsed": {"anchors": [{
            "anchor_id": "approved-2", "location_label": "Paragraph 2",
            "text": "Unauthorised generic claim.\n"
                    "Proposal reuse | Fictional FM Pte Ltd | Fictional FM Pte Ltd holds the required registration.\n"
                    "Proposal reuse | Other FM Pte Ltd | Other FM Pte Ltd holds the required registration.\n"
                    "Proposal reuse | Fictional FM Pte Ltd | Fictional FM Pte Ltd will roster qualified HVAC technicians before mobilisation.",
        }]},
    }


def test_only_current_effective_company_wording_is_offered():
    company = {"id": uuid4(), "payload": json.dumps(accepted_payload("2027-01-01"))}
    today, deadline = date(2026, 11, 3), date(2027, 2, 1)
    assert reusable_wording(company, str(uuid4()), today, today) == []
    assert reusable_wording(company, str(company["id"]), today, deadline) == []
    options = reusable_wording(company, str(company["id"]), today, today)
    assert len(options) == 3
    assert all("Unauthorised" not in item.text for item in options)


def test_gaps_create_scoped_requests_and_block_draft_review(preparation, actors):
    c = preparation
    created = c.http.post(c.url, json=create(c, c.actor, proposal_entity="Fictional FM Pte Ltd"))
    assert created.status_code == 201, created.text
    path = c.url + "/" + created.json()["id"]
    view = c.http.get(path + "/proposal").json()
    assert view["requirements"][0]["citations"] and not view["wording"]
    assert view["can_request_input"]
    request = confirm(c, "proposal:registration")
    assert request.status_code == 201, request.text
    assert request.json()["requirement_ids"] == ["registration"]
    assert confirm(c, "proposal:unlinked").status_code == 422
    saved = c.http.post(path + "/proposal", json=command(c.approval, expected_revision=1,
        action="draft_proposal", company_version_id=None, selections={}))
    assert saved.status_code == 201, saved.text
    file = c.http.get(path + "/files/" + saved.json()["id"])
    doc = Document(BytesIO(file.content))
    paragraphs = [p.text for p in doc.paragraphs]
    assert any(p.startswith("Input needed.") for p in paragraphs)
    doc.add_paragraph("An edited copy with the same evidence gap.")
    edited = BytesIO()
    doc.save(edited)
    upload = c.http.post(path + "/files",
        data={"metadata": json.dumps(command(c.approval, expected_revision=2))},
        files={"file": ("edited.docx", edited.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert upload.status_code == 422 and upload.json()["code"] == "GENERATED_PROPOSAL_REQUIRED"
    denied = c.http.post(path + "/actions", json=command(c.approval, expected_revision=2,
        action="request_review", note="Review this incomplete draft."))
    assert denied.status_code == 409 and denied.json()["code"] == "PROPOSAL_REVIEW_BLOCKED"
    c.current[0] = actors["viewer"]
    assert not c.http.get(path + "/proposal").json()["can_request_input"]
    c.current[0] = actors["other"]
    assert c.http.get(path + "/proposal").status_code == 404


def test_proposal_pins_entity_source_and_plan_and_replays_safely(screening_case, actors):
    c = screening_case
    make_ready(c)
    workspace = c.actor.workspace_id
    company = db(c.http,c.app,"""INSERT INTO m1_app.artifact_versions(workspace_id,kind,manifest,payload,created_by)
        VALUES($1,'company_evidence','{}',$2::jsonb,$3) RETURNING id""",
        workspace,json.dumps(accepted_payload()),actors["admin"].user_id)[0]["id"]
    artifact = c.review["screening"]["artifact"]
    registration = artifact["findings"][0]
    artifact["findings"].append({
        **registration, "id": "staff", "statement": "Minimum HVAC staffing",
        "kind": "delivery_commitment", "due_stage": "mobilisation", "critical": False,
        "critical_basis": None, "material_now": False, "answer_ids": [],
        "tender_citations": [{**registration["tender_citations"][0],
            "quote": "Minimum staffing is due during mobilisation."}],
    })
    db(c.http,c.app,"""INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
        SELECT workspace_id,tender_id,kind,input_revision,manifest || $2::jsonb,$3::jsonb,created_by
        FROM m1_app.artifact_versions WHERE id=$1 RETURNING id""", UUID(c.review["screening"]["id"]),
        json.dumps({"company_version_id": str(company)}), json.dumps(artifact))
    c.review = c.http.get("/api/v1/review-cases/" + c.tender["id"]).json()
    task = confirm(c, "preparation", actors["approver"]).json()
    c.current[0] = actors["approver"]
    approved = decide(c, task)
    assert approved.status_code == 201, approved.text
    c.approval = approved.json()["id"]
    c.current[0] = c.actor
    c.url = f"/api/v1/tenders/{c.tender['id']}/preparation"
    created = c.http.post(c.url, json=create(c, actors["approver"], proposal_entity="Fictional FM Pte Ltd",
                                            finding_ids=["registration", "staff"]))
    assert created.status_code == 201, created.text
    path = c.url + "/" + created.json()["id"]
    view = c.http.get(path + "/proposal").json()
    selected, delivery = view["wording"]
    assert all(entry["entity"] == "Fictional FM Pte Ltd" for entry in view["wording"])
    body = command(c.approval, expected_revision=1, action="draft_proposal",
                   company_version_id=str(company), selections={"registration": selected["id"], "staff": delivery["id"]})
    assert c.http.post(path + "/proposal", json=body).status_code == 403
    c.current[0] = actors["approver"]
    other = reusable_wording({"id": company, "payload": json.dumps(accepted_payload())},
                            str(company), date(2026, 11, 3), date(2099, 1, 1), entity="Other FM Pte Ltd")[0]
    assert c.http.post(path + "/proposal", json={**body, "selections": {"registration": other.id}}).status_code == 422
    assert c.http.post(path + "/proposal", json={**body, "company_version_id": str(uuid4())}).status_code == 409
    saved = c.http.post(path + "/proposal", json=body)
    assert saved.status_code == 201, saved.text
    assert c.http.post(path + "/proposal", json=body).json() == saved.json()
    draft = c.http.get(path + "/files/" + saved.json()["id"])
    paragraphs = "\n".join(p.text for p in Document(BytesIO(draft.content)).paragraphs)
    assert selected["text"] in paragraphs and delivery["text"] in paragraphs and str(company) in paragraphs
    assert "Delivery approach" in paragraphs and "Qualifications and supporting evidence" in paragraphs
    assert "Other FM Pte Ltd" not in paragraphs and "Unauthorised generic claim" not in paragraphs
    asked = c.http.post(path + "/actions", json=command(c.approval, expected_revision=2,
        action="request_review", note="Review exact requirement coverage."))
    assert asked.status_code == 201, asked.text
    c.current[0] = c.reviewer
    denied = c.http.post(path + "/actions", json=command(c.approval, expected_revision=3,
        action="accept", note="Reviewed draft."))
    assert denied.status_code == 422 and denied.json()["code"] == "PROPOSAL_COVERAGE_REQUIRED"
    accepted = c.http.post(path + "/actions", json=command(c.approval, expected_revision=3,
        action="accept", note="Checked the wording against the requirement.", requirements_checked=True))
    assert accepted.status_code == 201, accepted.text
    c.current[0] = c.actor
    updated = c.http.post(path + "/actions", json=command(c.approval, expected_revision=4,
        action="update_plan", owner_id=str(actors["approver"].user_id), reviewer_id=str(c.reviewer.user_id),
        finding_ids=["registration"], due_at="2098-12-30T09:00:00+08:00"))
    assert updated.status_code == 201, updated.text
    c.current[0] = actors["approver"]
    assert c.http.post(path + "/actions", json=command(c.approval, expected_revision=5,
        action="request_review", note="Review outdated plan.")).json()["code"] == "PROPOSAL_REVIEW_BLOCKED"
    db(c.http, c.app, "UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1 RETURNING id",
       UUID(c.tender["id"]))
    amended = c.http.get(c.url).json()["items"][0]
    assert amended["status"] == "non_current" and not any(review["is_current"] for review in amended["reviews"])
    assert c.http.get(path + "/files/" + saved.json()["id"]).content == draft.content
