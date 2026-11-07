import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter

from test_opportunities import db
from test_preparation_tracking import command, create, preparation
from test_screening_workflow import confirm, decide, make_ready, screening_case


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def package_body(view, approver):
    return {
        "client_request_id": str(uuid4()),
        "expected_snapshot": view["snapshot"],
        "previous_package_id": view["packages"][0]["id"] if view["packages"] else None,
        "approver_id": str(approver.user_id),
    }


def accept_deliverables(c, actors, **acceptance):
    workbook = io.BytesIO()
    with ZipFile(workbook, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    for kind, file in [
        ("technical_response", ("response.pdf", pdf_bytes(), "application/pdf")),
        ("pricing_workbook", ("pricing.xlsx", workbook.getvalue(),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
    ]:
        c.current[0] = c.actor
        created = c.http.post(c.url, json=create(c, actors["approver"], kind))
        assert created.status_code == 201, created.text
        path = c.url + "/" + created.json()["id"]
        c.current[0] = actors["approver"]
        uploaded = c.http.post(path + "/files", data={"metadata": json.dumps(
            command(c.approval, expected_revision=1))}, files={"file": file})
        assert uploaded.status_code == 201, uploaded.text
        asked = c.http.post(path + "/actions", json=command(
            c.approval, expected_revision=2, action="request_review", note="Check complete submission scope."))
        assert asked.status_code == 201, asked.text
        c.current[0] = c.reviewer
        reviewed = c.http.post(path + "/actions", json=command(
            c.approval, expected_revision=3, action="accept", note="Reviewed the file.", **acceptance))
        assert reviewed.status_code == 201, reviewed.text
    c.current[0] = c.actor


def test_release_and_receipt_require_distinct_authority_and_keep_history(preparation, actors, monkeypatch):
    c = preparation
    path = c.url.replace("/preparation", "/submission")
    initial = c.http.get(path)
    assert initial.status_code == 200, initial.text
    assert not initial.json()["can_seal"] and not initial.json()["packages"]
    accept_deliverables(c, actors)
    view = c.http.get(path).json()
    assert view["can_seal"] and len(view["candidate_files"]) == 2
    body = package_body(view, c.reviewer)
    sealed = c.http.post(path + "/packages", json=body)
    assert sealed.status_code == 201, sealed.text
    assert c.http.post(path + "/packages", json=body).json() == sealed.json()
    assert c.http.post(path + "/packages", json={**body, "client_request_id": str(uuid4())}).status_code == 409
    package_id = sealed.json()["id"]
    package_path = path + "/packages/" + package_id
    def record(metadata, evidence):
        return c.http.post(package_path + "/receipt", data={"metadata": json.dumps(metadata)},
                           files={"file": ("portal-receipt.pdf", evidence, "application/pdf")})

    receipt = {"client_request_id": str(uuid4()), "portal_reference": "CONTROLLED-123",
               "submitted_at": datetime.now(timezone.utc).isoformat()}
    evidence = pdf_bytes()
    assert record(receipt, evidence).status_code == 409
    release = {"client_request_id": str(uuid4()), "outcome": "approved",
               "note": "Checked the technical and commercial offer.", "checks_confirmed": True}
    for actor in (c.actor, actors["admin"], actors["viewer"]):
        c.current[0] = actor
        assert c.http.post(package_path + "/decision", json=release).status_code == 403
    c.current[0] = c.reviewer
    assert c.http.post(package_path + "/decision", json={**release, "checks_confirmed": False}).status_code == 422
    approved = c.http.post(package_path + "/decision", json=release)
    assert approved.status_code == 201, approved.text
    assert c.http.post(package_path + "/decision", json=release).json() == approved.json()
    package = c.http.get(path).json()["packages"][0]
    assert package["state"] == "approved" and package["receipt"] is None
    assert {f["kind"] for f in package["files"]} == {"technical_response", "pricing_workbook"}
    assert all(len(f["sha256"]) == 64 and f["review_id"] for f in package["files"])
    c.current[0] = c.actor
    receipt["submitted_at"] = package["decision"]["decided_at"]
    monkeypatch.setattr("app.tenders.submission.utc_now", lambda: datetime(2100, 1, 1, tzinfo=timezone.utc))
    after_close = c.http.get(path).json()["packages"][0]
    assert after_close["state"] == "closed" and after_close["can_record_receipt"]
    assert record({**receipt, "submitted_at": "2020-01-01T10:00:00+08:00"}, evidence).status_code == 422
    assert record({**receipt, "submitted_at": "2099-01-03T10:00:00+08:00"}, evidence).status_code == 422
    recorded = record(receipt, evidence)
    assert recorded.status_code == 201, recorded.text
    assert record(receipt, evidence).json() == recorded.json()
    assert c.http.get(path).json()["packages"][0]["state"] == "submitted"
    assert c.http.get(package_path + "/receipt").content == evidence
    c.current[0] = actors["other"]
    assert c.http.get(path).status_code == 404
    assert c.http.get(package_path + "/receipt").status_code == 404
    c.current[0] = actors["viewer"]
    db(c.http, c.app, "UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1 RETURNING id",
       UUID(c.tender["id"]))
    package = c.http.get(path).json()["packages"][0]
    assert package["state"] == "non_current" and package["receipt"]["portal_reference"] == "CONTROLLED-123"
    assert c.http.get(package_path + "/receipt").content == evidence


def test_replacing_an_accepted_file_invalidates_release(preparation, actors):
    c = preparation
    path = c.url.replace("/preparation", "/submission")
    accept_deliverables(c, actors)
    view = c.http.get(path).json()
    sealed = c.http.post(path + "/packages", json=package_body(view, c.reviewer))
    assert sealed.status_code == 201, sealed.text
    package_path = path + "/packages/" + sealed.json()["id"]
    c.current[0] = c.reviewer
    release = {"client_request_id": str(uuid4()), "outcome": "approved",
               "note": "Checked both versions.", "checks_confirmed": True}
    assert c.http.post(package_path + "/decision", json=release).status_code == 201
    c.current[0] = actors["approver"]
    item = next(item for item in c.http.get(c.url).json()["items"] if item["kind"] == "technical_response")
    replaced = c.http.post(c.url + "/" + item["id"] + "/files",
        data={"metadata": json.dumps(command(c.approval, expected_revision=item["revision"]))},
        files={"file": ("updated.pdf", pdf_bytes(), "application/pdf")})
    assert replaced.status_code == 201, replaced.text
    c.current[0] = c.actor
    current = c.http.get(path).json()
    assert not current["can_seal"] and current["packages"][0]["state"] == "non_current"
    assert not current["packages"][0]["can_record_receipt"]
    response = c.http.post(package_path + "/receipt", data={"metadata": json.dumps({
        "client_request_id": str(uuid4()), "portal_reference": "OLD-PACKAGE",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })}, files={"file": ("portal-receipt.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 409


@pytest.mark.parametrize("requirements_checked", [None, True])
def test_linked_submission_condition_requires_explicit_review(screening_case, actors, requirements_checked):
    c = screening_case
    make_ready(c)
    c.url = f"/api/v1/tenders/{c.tender['id']}/preparation"
    path = c.url.replace("/preparation", "/submission")
    artifact = c.review["screening"]["artifact"]
    artifact["findings"][0].update(status="unconfirmed", material_now=False, kind="bid_artifact",
        due_stage="submission", preparation_role="preparation_work", preparation_basis="before submission")
    artifact["preparation_condition_ids"] = ["registration"]
    db(c.http, c.app, """INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
       SELECT workspace_id,tender_id,kind,input_revision,manifest,$2::jsonb,created_by FROM m1_app.artifact_versions
       WHERE id=$1 RETURNING id""",
       UUID(c.review["screening"]["id"]), json.dumps(artifact))
    c.review = c.http.get("/api/v1/review-cases/" + c.tender["id"]).json()
    task = confirm(c, "preparation", actors["approver"]).json()
    c.current[0] = actors["approver"]
    approved = decide(c, task, conditions=[{"finding_id": "registration", "condition": "Check the final submission file."}])
    assert approved.status_code == 201, approved.text
    c.approval = approved.json()["id"]
    accept_deliverables(c, actors, **({"requirements_checked": True} if requirements_checked else {}))
    view = c.http.get(path).json()
    assert len(view["candidate_files"]) == 2
    assert view["can_seal"] is bool(requirements_checked)
