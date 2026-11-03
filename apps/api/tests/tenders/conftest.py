import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv
import pytest

ROOT = Path(__file__).resolve().parents[4]
load_dotenv(ROOT / ".env", override=False)


def implemented():
    assert (ROOT / "apps/api/app/main.py").exists(), "T1 application is not implemented"
    from app.main import create_app
    return create_app


@pytest.fixture(scope="session")
def schema():
    create_app = implemented()
    from app.db import migrate
    asyncio.run(migrate())
    from app.tenders.storage import setup
    asyncio.run(setup())
    return create_app


@pytest.fixture
def actors(schema):
    from app.tenders.models import ActorContext

    first, other = uuid4(), uuid4()
    result = {}
    async def seed():
        connection = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            await connection.executemany("INSERT INTO m1_app.workspaces(id,name) VALUES($1,$2)",
                                         [(first,"Fictional test workspace"),(other,"Other fictional workspace")])
            for name, roles, workspace in [
                ("owner",["member"],first),("viewer",["viewer"],first),
                ("admin",["admin"],first),("approver",["member"],first),
                ("other",["member"],other),
            ]:
                user = uuid4()
                await connection.execute("INSERT INTO m1_app.memberships(workspace_id,user_id,roles) VALUES($1,$2,$3)", workspace,user,roles)
                result[name] = ActorContext(user_id=user,workspace_id=workspace,roles=set(roles))
        finally:
            await connection.close()
    asyncio.run(seed())
    yield result
    async def clean():
        connection = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            keys = await connection.fetch("SELECT storage_key FROM m1_app.document_versions WHERE workspace_id=ANY($1::uuid[]) UNION SELECT storage_key FROM m1_app.preparation_files WHERE workspace_id=ANY($1::uuid[]) UNION SELECT storage_key FROM m1_app.submission_receipts WHERE workspace_id=ANY($1::uuid[]) UNION SELECT payload->'document'->>'storage_key' FROM m1_app.artifact_versions WHERE workspace_id=ANY($1::uuid[]) AND kind='company_evidence'",[first,other])
            owned = [row['storage_key'] for row in keys if row['storage_key'].startswith((str(first)+'/',str(other)+'/'))]
            if owned:
                import httpx
                from app.tenders.storage import SourceStorage,BUCKET
                async with httpx.AsyncClient(timeout=60) as http:
                    response = await SourceStorage(http).request('DELETE',f'/object/{BUCKET}',json={'prefixes':owned})
                    assert response.status_code == 200, 'Could not delete this test workspace source objects'
            await connection.execute('DELETE FROM m1_queue.pgqueuer WHERE dedupe_key IN (SELECT id::text FROM m1_app.jobs WHERE workspace_id=ANY($1::uuid[]))',[first,other])
            await connection.execute('DELETE FROM m1_app.assistant_runs WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute('DELETE FROM m1_app.decisions WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute('DELETE FROM m1_app.preparation_items WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute('DELETE FROM m1_app.submission_packages WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute('DELETE FROM m1_app.preparation_decisions WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute('DELETE FROM m1_app.review_tasks WHERE workspace_id=ANY($1::uuid[])',[first,other])
            await connection.execute("DELETE FROM m1_app.workspaces WHERE id=ANY($1::uuid[])",[first,other])
        finally:
            await connection.close()
    asyncio.run(clean())


@pytest.fixture
def client(schema, actors):
    from fastapi.testclient import TestClient
    from app.auth import get_actor

    app = schema()
    current = [actors["owner"]]
    app.dependency_overrides[get_actor] = lambda: current[0]
    with TestClient(app) as http:
        yield http, current, app
