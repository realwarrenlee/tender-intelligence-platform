from uuid import uuid4

from fastapi.testclient import TestClient
import asyncpg
import pytest

def test_without_a_verified_session_access_is_denied(schema):
    with TestClient(schema()) as http:
        assert http.get("/api/v1/tenders").status_code==401


def test_viewer_cannot_create_and_foreign_tender_id_is_hidden(client,actors):
    http,current,_=client
    body={"title":"Fictional", "client_request_id":str(uuid4())}
    tender=http.post("/api/v1/tenders",json=body).json()
    current[0]=actors["viewer"]
    assert http.post("/api/v1/tenders",json={**body,"client_request_id":str(uuid4())}).status_code==403
    current[0]=actors["other"]
    assert http.get(f"/api/v1/tenders/{tender['id']}").status_code==404
    assert http.get("/api/v1/tenders").json()["items"]==[]


def test_admin_without_approver_role_cannot_record_decision(client,actors):
    http,current,_=client
    tender=http.post("/api/v1/tenders",json={"title":"Fictional", "client_request_id":str(uuid4())}).json()
    decision={"expected_input_revision":1,"assessment_version_id":str(uuid4()),
        "decision":"pursue","reason":"Test only","review_complete":True,"client_request_id":str(uuid4())}
    current[0]=actors["admin"]
    assert http.post(f"/api/v1/tenders/{tender['id']}/decisions",json=decision).status_code==403
    current[0]=actors["approver"]
    assert http.post(f"/api/v1/tenders/{tender['id']}/decisions",json=decision).status_code==422
    assert http.post(f"/api/v1/tenders/{tender['id']}/decisions",json={**decision,"expected_input_revision":0}).status_code==409


def test_client_cannot_supply_roles_or_workspace(client):
    http,_,_=client
    response=http.post("/api/v1/tenders",json={"title":"Fictional", "client_request_id":str(uuid4()),"roles":["admin"],"workspace_id":str(uuid4())})
    assert response.status_code==422


def test_forged_context_roles_do_not_override_database_membership(client,actors):
    http,current,_=client
    current[0]=actors["viewer"].model_copy(update={"roles":{"bid_owner"}})
    assert http.post("/api/v1/tenders",json={"title":"Fictional","client_request_id":str(uuid4())}).status_code==403


def test_verified_identity_uses_database_roles_not_user_metadata(schema,actors,monkeypatch):
    import httpx
    from unittest.mock import AsyncMock

    response=httpx.Response(200,json={"id":str(actors["viewer"].user_id),"user_metadata":{"roles":["bid_owner","approver"]}})
    monkeypatch.setattr(httpx.AsyncClient,"get",AsyncMock(return_value=response))
    with TestClient(schema()) as http:
        headers={"Authorization":"Bearer fictional-test-token"}
        assert http.get("/api/v1/me",headers=headers).json()["roles"]==["viewer"]
        assert http.post("/api/v1/tenders",headers=headers,json={"title":"Fictional","client_request_id":str(uuid4())}).status_code==403


def test_malformed_upstream_session_is_unauthenticated(schema,monkeypatch):
    import httpx
    from unittest.mock import AsyncMock

    monkeypatch.setattr(httpx.AsyncClient,"get",AsyncMock(return_value=httpx.Response(400,json={"error":"invalid token"})))
    with TestClient(schema()) as http:
        assert http.get("/api/v1/me",headers={"Authorization":"Bearer fictional-invalid-token"}).status_code==401


def test_bid_owner_cannot_register_company_evidence(client):
    from app.m1.models import RegisterSources,SourceInput
    from app.m1.repository import Repository
    import asyncio,asyncpg,os,pytest

    http,current,_=client
    tender=http.post("/api/v1/tenders",json={"title":"Fictional","client_request_id":str(uuid4())}).json()
    command=RegisterSources(tender_id=tender["id"],expected_input_revision=1,client_request_id=str(uuid4()),
        sources=[SourceInput(filename="company.pdf",sha256="a"*64,storage_key="test-only/company",role="company_evidence")])
    async def check():
        pool=await asyncpg.create_pool(os.environ["DATABASE_URL"],min_size=1,max_size=1)
        try:
            with pytest.raises(Exception) as error:
                await Repository(pool).register_sources(current[0],command)
            assert error.value.status_code==403
        finally:
            await pool.close()
    asyncio.run(check())


@pytest.mark.parametrize("error",[ConnectionError("private connection detail"),TimeoutError("private timeout detail"),asyncpg.ConnectionDoesNotExistError("private driver detail")])
def test_database_availability_errors_are_sanitised_retryable_json(client,monkeypatch,error):
    from unittest.mock import AsyncMock

    http,_,app=client
    monkeypatch.setattr(app.state.repository,"list_tenders",AsyncMock(side_effect=error))
    response=http.get("/api/v1/tenders")
    assert response.status_code==503
    assert response.json()=={"code":"DATABASE_UNAVAILABLE","message":"The database is temporarily unavailable; retry this request.","retryable":True}
    assert "private" not in response.text


def test_integrity_errors_are_not_misreported_as_an_outage(client,monkeypatch):
    from unittest.mock import AsyncMock

    http,_,app=client
    monkeypatch.setattr(app.state.repository,"list_tenders",AsyncMock(side_effect=asyncpg.UniqueViolationError("test integrity error")))
    with pytest.raises(asyncpg.UniqueViolationError):
        http.get("/api/v1/tenders")
