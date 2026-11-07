from uuid import UUID, uuid4

import pytest

from test_documents import create, upload
from test_screening_workflow import screening_case as screening_case


def deletion(revision=1, key=None):
    return {"expected_input_revision": revision, "client_request_id": key or str(uuid4())}


def test_delete_removes_only_selected_tender_and_replays_once(client):
    http, _, app = client
    tender, retained = create(http), create(http)
    command = deletion()
    path = f"/api/v1/tenders/{tender['id']}"
    first = http.request("DELETE", path, json=command)
    assert first.status_code == 200, first.text
    assert first.json()["id"] == tender["id"]
    assert first.json()["deleted"] is True
    assert http.request("DELETE", path, json=command).json() == first.json()
    assert [row["id"] for row in http.get("/api/v1/tenders").json()["items"]] == [retained["id"]]
    assert http.get(path).status_code == 404
    assert http.get(path + "/history").status_code == 404
    assert enqueue(http, tender, revision=2).status_code == 404

    async def inspect():
        async with app.state.pool.acquire() as c:
            assert await c.fetchval("SELECT deleted_at IS NOT NULL FROM m1_app.tenders WHERE id=$1", UUID(tender["id"]))
            assert await c.fetchval("SELECT count(*) FROM m1_app.audit_events WHERE action='delete_tender' AND details->>'id'=$1", tender["id"]) == 1
    http.portal.call(inspect)


@pytest.mark.parametrize("actor,status", [("viewer",403),("approver",200),("admin",200)])
def test_delete_uses_current_database_role(client, actors, actor, status):
    http, current, _ = client
    tender = create(http)
    current[0] = actors[actor].model_copy(update={"roles": {"member"}})
    path = f"/api/v1/tenders/{tender['id']}"
    assert http.request("DELETE", path, json=deletion()).status_code == status
    assert http.get(path).status_code == (404 if status == 200 else 200)


def test_delete_rejects_foreign_workspace_and_stale_revision(client, actors):
    http, current, _ = client
    tender = create(http)
    path = f"/api/v1/tenders/{tender['id']}"
    assert http.request("DELETE", path, json=deletion(0)).status_code == 409
    current[0] = actors["other"]
    assert http.request("DELETE", path, json=deletion()).status_code == 404
    current[0] = actors["owner"]
    assert http.get(path).status_code == 200


def test_delete_cancels_queued_screening_and_hides_retained_source(screening_case, monkeypatch):
    from app.tenders import screening_workflow

    case = screening_case
    path = f"/api/v1/tenders/{case.tender['id']}"
    detail = case.http.get(path).json()
    revision = detail["input_revision"]
    source_id = detail["documents"][0]["id"]
    response = case.http.post(path + "/screenings", json=deletion(revision))
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert case.http.request("DELETE", path, json=deletion(revision)).status_code == 200

    async def unexpected_read(*args):
        pytest.fail("A deleted tender must not start screening.")
    monkeypatch.setattr(screening_workflow, "_context", unexpected_read)
    case.http.portal.call(case.run, case.app.state.pool, case.app.state.storage, UUID(job_id))
    assert case.http.get(f"/api/v1/sources/{source_id}").status_code == 404
    assert case.http.get(f"/api/v1/jobs/{job_id}").status_code == 404

    async def inspect():
        async with case.app.state.pool.acquire() as c:
            assert await c.fetchval("SELECT status FROM m1_app.jobs WHERE id=$1", UUID(job_id)) == "cancelled"
            assert await c.fetchval("SELECT count(*) FROM m1_app.document_versions WHERE id=$1", UUID(source_id)) == 1
    case.http.portal.call(inspect)
