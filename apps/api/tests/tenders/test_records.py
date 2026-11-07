import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4

import pytest

from conftest import implemented


def payload(**changes):
    return {"title":"Fictional maintenance tender", "source_label":"manual_upload",
            "client_request_id":str(uuid4()), **changes}


def test_application_exists():
    implemented()


def test_create_replay_conflict_and_unready_screening(client):
    http, _, _ = client
    body = payload()
    created = http.post("/api/v1/tenders",json=body)
    assert created.status_code == 201, created.text
    tender = created.json()
    assert tender["input_revision"] == 1
    assert http.post("/api/v1/tenders",json=body).json()["id"] == tender["id"]
    assert http.post("/api/v1/tenders",json={**body,"title":"Changed"}).status_code == 409
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()["assessment"] is None
    assert http.post(f"/api/v1/tenders/{tender['id']}/screenings",json={"expected_input_revision":1,"client_request_id":str(uuid4())}).status_code == 422


def test_concurrent_duplicate_creates_one_tender(client):
    http, _, _ = client
    body = payload()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _:http.post("/api/v1/tenders",json=body),range(2)))
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1


def test_source_versions_increment_once_and_reject_stale_revision(client):
    from app.tenders.models import RegisterSources,SourceInput
    from app.tenders.repository import Repository

    http, current, app = client
    tender = http.post("/api/v1/tenders",json=payload()).json()
    command = RegisterSources(tender_id=tender["id"],expected_input_revision=1,
        client_request_id=str(uuid4()),sources=[SourceInput(filename="fictional.pdf",sha256="a"*64,storage_key="test-only/file-v1",role="tender")])
    async def register():
        import asyncpg,os
        pool=await asyncpg.create_pool(os.environ["DATABASE_URL"],min_size=1,max_size=2)
        try:
            repo=Repository(pool)
            first=await repo.register_sources(current[0],command)
            replay=await repo.register_sources(current[0],command)
            assert first==replay
            assert first["input_revision"]==2
            from uuid import UUID
            async with pool.acquire() as connection:
                stored=await connection.fetchval("SELECT manifest FROM m1_app.artifact_versions WHERE id=$1",UUID(first["source_set_version_id"]))
                assert json.loads(stored)["document_version_ids"]==first["document_version_ids"]
            stale=command.model_copy(update={"client_request_id":str(uuid4())})
            with pytest.raises(Exception) as error:
                await repo.register_sources(current[0],stale)
            assert error.value.status_code==409
        finally:
            await pool.close()
    asyncio.run(register())
    view=http.get(f"/api/v1/tenders/{tender['id']}").json()
    assert view["input_revision"]==2
    assert len(view["documents"])==1


def test_persistence_across_app_restart(schema,actors):
    from fastapi.testclient import TestClient
    from app.auth import get_actor
    body=payload()
    apps=[schema(),schema()]
    for app in apps:
        app.dependency_overrides[get_actor]=lambda:actors["owner"]
    with TestClient(apps[0]) as first:
        tender=first.post("/api/v1/tenders",json=body).json()
    with TestClient(apps[1]) as second:
        assert second.get(f"/api/v1/tenders/{tender['id']}").status_code==200
        assert second.post("/api/v1/tenders",json=body).json()["id"]==tender["id"]


def test_private_schema_denies_browser_roles_and_versions_are_immutable(client):
    import asyncpg,os
    from app.tenders.models import RegisterSources,SourceInput
    from app.tenders.repository import Repository

    http,current,_=client
    tender=http.post("/api/v1/tenders",json=payload()).json()
    async def check():
        pool=await asyncpg.create_pool(os.environ["DATABASE_URL"],min_size=1,max_size=1)
        try:
            command=RegisterSources(tender_id=tender["id"],expected_input_revision=1,client_request_id=str(uuid4()),
                sources=[SourceInput(filename="fictional.pdf",sha256="a"*64,storage_key="test-only/file",role="tender")])
            result=await Repository(pool).register_sources(current[0],command)
            from uuid import UUID
            async with pool.acquire() as connection:
                assert not await connection.fetchval("SELECT has_schema_privilege('anon','m1_app','USAGE')")
                assert not await connection.fetchval("SELECT has_schema_privilege('authenticated','m1_app','USAGE')")
                assert await connection.fetchval("SELECT bool_and(rowsecurity) FROM pg_tables WHERE schemaname='m1_app'")
                with pytest.raises(asyncpg.RaiseError):
                    await connection.execute("UPDATE m1_app.document_versions SET filename='changed' WHERE id=$1",UUID(result["document_version_ids"][0]))
        finally:
            await pool.close()
    asyncio.run(check())


def test_unchanged_migration_accepts_windows_line_endings(schema,tmp_path,monkeypatch):
    from app import db

    source=next((db.ROOT/"supabase/migrations").glob("*_m1_foundation.sql"))
    destination=tmp_path/"supabase/migrations"/source.name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(source.read_text(encoding="utf-8").replace("\n","\r\n").encode())
    monkeypatch.setattr(db,"ROOT",tmp_path)
    asyncio.run(db.migrate())


def test_tender_revision_and_documents_use_one_snapshot(client):
    import asyncpg,os
    from app.tenders.models import RegisterSources,SourceInput
    from app.tenders.repository import Repository
    from uuid import UUID

    http,current,_=client
    tender=http.post("/api/v1/tenders",json=payload()).json()
    async def check():
        pool=await asyncpg.create_pool(os.environ["DATABASE_URL"],min_size=1,max_size=2)
        try:
            repo=Repository(pool)
            original=repo._tender
            async def pause_after_read(connection,actor,tender_id,lock=False):
                row=await original(connection,actor,tender_id,lock)
                if not lock:
                    await repo.register_sources(actor,RegisterSources(tender_id=tender_id,expected_input_revision=1,
                        client_request_id=str(uuid4()),sources=[SourceInput(filename="new.pdf",sha256="b"*64,storage_key="test-only/new",role="tender")]))
                return row
            repo._tender=pause_after_read
            view=await repo.get_tender(current[0],UUID(tender["id"]))
            assert view["input_revision"]==1
            assert view["documents"]==[]
            repo._tender=original
            latest=await repo.get_tender(current[0],UUID(tender["id"]))
            assert latest["input_revision"]==2 and len(latest["documents"])==1
        finally:
            await pool.close()
    asyncio.run(check())
