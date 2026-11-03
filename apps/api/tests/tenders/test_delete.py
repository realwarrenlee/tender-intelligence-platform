from uuid import UUID, uuid4

import pytest

from test_documents import create, upload
from test_jobs import enqueue, run_job


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


def test_delete_cancels_queued_analysis_and_hides_retained_source(client, monkeypatch):
    http, _, app = client
    tender = create(http)
    uploaded = upload(http, tender).json()
    job_id = enqueue(http, tender).json()["id"]
    source_id = uploaded["document_version_ids"][0]
    assert http.request("DELETE", f"/api/v1/tenders/{tender['id']}", json=deletion(2)).status_code == 200

    async def unexpected_read(*args):
        pytest.fail("A deleted tender must not start parsing.")
    monkeypatch.setattr(app.state.storage, "get", unexpected_read)
    run_job(http, app, job_id)
    assert http.get(f"/api/v1/sources/{source_id}").status_code == 404
    assert http.get(f"/api/v1/jobs/{job_id}").status_code == 404

    async def inspect():
        async with app.state.pool.acquire() as c:
            assert await c.fetchval("SELECT status FROM m1_app.jobs WHERE id=$1", UUID(job_id)) == "cancelled"
            assert await c.fetchval("SELECT count(*) FROM m1_app.document_versions WHERE id=$1", UUID(source_id)) == 1
            assert await c.fetchval("SELECT count(*) FROM m1_app.artifact_versions WHERE tender_id=$1 AND kind='parsed_sources'", UUID(tender["id"])) == 0
    http.portal.call(inspect)


def test_delete_fences_an_analysis_already_running(client, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from app.tenders import jobs

    http, _, app = client
    tender = create(http)
    assert upload(http, tender).status_code == 201
    job_id = enqueue(http, tender).json()["id"]
    entered, release = threading.Event(), threading.Event()

    async def controlled(source, *args):
        entered.set()
        await asyncio.to_thread(release.wait, 20)
        return {"document_version_id": source["id"], "source_role": "tender", "sha256": source["sha256"],
                "status": "complete", "error_code": None, "locations": [{"page": 1, "status": "complete"}],
                "anchors": [{"page": 1, "text": "Fictional parser result"}]}
    monkeypatch.setattr(jobs, "parse_isolated", controlled)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_job, http, app, job_id)
        try:
            assert entered.wait(10)
            assert http.request("DELETE", f"/api/v1/tenders/{tender['id']}", json=deletion(2)).status_code == 200
        finally:
            release.set()
        future.result(timeout=20)

    async def inspect():
        async with app.state.pool.acquire() as c:
            row = await c.fetchrow("SELECT status,output_version_id FROM m1_app.jobs WHERE id=$1", UUID(job_id))
            assert row["status"] == "cancelled"
            assert row["output_version_id"] is None
            assert await c.fetchval("SELECT count(*) FROM m1_app.artifact_versions WHERE tender_id=$1 AND kind='parsed_sources'", UUID(tender["id"])) == 0
    http.portal.call(inspect)
