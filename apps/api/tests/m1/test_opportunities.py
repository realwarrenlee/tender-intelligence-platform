import asyncio
import json
from uuid import UUID,uuid4

import httpx
import pytest

from app.m1.policy import DomainError


def command(**changes):
    return {"notice_id":"FICT-001","title":"Fictional integrated facilities management",
        "buyer":"Fictional Agency","reference":"FICT-001","category":"Facilities Management",
        "closing_at":"2026-12-01T16:00:00+08:00","notice_text":"Fictional notice for IFM services. Attachments require access.",
        "client_request_id":str(uuid4()),**changes}


def imported(http,**changes):
    response=http.post("/api/v1/opportunity-suggestions/import",json=command(**changes))
    assert response.status_code==201,response.text
    return response.json()


def db(http,app,sql,*args):
    async def execute():
        async with app.state.pool.acquire() as c:
            return await c.fetch(sql,*args)
    return http.portal.call(execute)


def approve(http,app,actor,suggestion_id):
    async def seed():
        async with app.state.pool.acquire() as c,c.transaction():
            await c.execute("""INSERT INTO m1_app.workspace_spending_policies(workspace_id,daily_limit_usd,approved_by)
                VALUES($1,5,$2) ON CONFLICT DO NOTHING""",actor.workspace_id,actor.user_id)
            return str(await c.fetchval("""INSERT INTO m1_app.stage_budgets
                (workspace_id,stage,scope_key,limit_usd,max_requests,max_responses_requests,max_input_tokens,approved_by)
                VALUES($1,'screening',$2,0.50,8,2,200000,$3) RETURNING id""",
                actor.workspace_id,"opportunity:"+suggestion_id,actor.user_id))
    return http.portal.call(seed)


def triage(http,item,action="start_assessment",**changes):
    body={"expected_revision":item["revision"],"action":action,"client_request_id":str(uuid4()),**changes}
    return http.post("/api/v1/opportunity-suggestions/"+item["id"]+"/triage",json=body)


def test_import_is_labelled_deduplicated_versioned_and_source_evidence_is_immutable(client):
    http,_,app=client
    body=command()
    first=http.post("/api/v1/opportunity-suggestions/import",json=body)
    assert first.status_code==201,first.text
    item=first.json()
    assert item["notice"]["origin"]=="controlled_import"
    assert item["notice"]["coverage"]=="notice_only" and not item["tender_id"]
    assert item["budget_status"]=="not_approved" and item["match"]["relevant"]
    assert http.post("/api/v1/opportunity-suggestions/import",json=body).json()==item
    same=imported(http)
    assert same["id"]==item["id"] and same["notice_version_id"]==item["notice_version_id"]
    amended=imported(http,closing_at="2026-12-03T16:00:00+08:00")
    assert amended["id"]==item["id"] and amended["revision"]==item["revision"]+1
    assert amended["notice_version_id"]!=item["notice_version_id"]
    rows=db(http,app,"SELECT payload FROM m1_app.notice_versions WHERE suggestion_id=$1 ORDER BY version",UUID(item["id"]))
    assert len(rows)==2 and json.loads(rows[0]["payload"])["closing_at"]==body["closing_at"]
    conflict=http.post("/api/v1/opportunity-suggestions/import",json={**body,"title":"Changed"})
    assert conflict.status_code==409


def test_defer_dismiss_replay_and_stale_commands_preserve_history(client):
    http,_,app=client
    item=imported(http)
    request_id=str(uuid4())
    later=triage(http,item,"defer",client_request_id=request_id)
    assert later.status_code==200,later.text
    assert later.json()["state"]=="deferred"
    assert triage(http,item,"defer",client_request_id=request_id).json()==later.json()
    assert triage(http,item,"dismiss").status_code==409
    dismissed=triage(http,later.json(),"dismiss")
    assert dismissed.status_code==200 and dismissed.json()["state"]=="dismissed"
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    assert http.get("/api/v1/opportunity-suggestions?state=dismissed").json()["items"][0]["id"]==item["id"]
    assert len(db(http,app,"SELECT * FROM m1_app.opportunity_triage_events WHERE suggestion_id=$1",UUID(item["id"])))==2


def test_business_roles_workspace_and_intake_owner_are_enforced(client,actors):
    http,current,app=client
    item=imported(http)
    for name in ("admin","viewer","approver"):
        current[0]=actors[name].model_copy(update={"roles":{"bid_owner"}})
        assert http.post("/api/v1/opportunity-suggestions/import",json=command()).status_code==403
        assert triage(http,item,"defer").status_code==403
        assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    current[0]=actors["other"]
    assert triage(http,item,"defer").status_code==404
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    current[0]=actors["owner"]
    for extra in ({"origin":"public_notice"},{"intake_owner_user_id":str(uuid4())},{"budget_usd":1},{"source_url":"https://evil.example"},{"workspace_id":str(uuid4())}):
        assert http.post("/api/v1/opportunity-suggestions/import",json=command(**extra)).status_code==422


def test_activation_requires_existing_authority_and_concurrent_starts_share_case_and_budget(client,actors):
    from app.m1.models import TriageSuggestion
    from app.m1.opportunities import Opportunities
    http,_,app=client
    actor=actors["owner"]
    item=imported(http)
    denied=triage(http,item)
    assert denied.status_code==422 and denied.json()["code"]=="ASSESSMENT_BUDGET_REQUIRED"
    assert db(http,app,"SELECT id FROM m1_app.tenders WHERE workspace_id=$1",actor.workspace_id)==[]
    budget_id=approve(http,app,actor,item["id"])
    async def start():
        service=Opportunities(app.state.pool)
        return await asyncio.gather(*(service.triage_suggestion(actor,UUID(item["id"]),TriageSuggestion(
            expected_revision=item["revision"],action="start_assessment",client_request_id=str(uuid4()))) for _ in range(2)))
    results=http.portal.call(start)
    assert results[0]["tender_id"]==results[1]["tender_id"]
    assert results[0]["budget_id"]==results[1]["budget_id"]==budget_id
    assert len(db(http,app,"SELECT id FROM m1_app.tenders WHERE workspace_id=$1",actor.workspace_id))==1
    assert len(db(http,app,"SELECT id FROM m1_app.stage_budgets WHERE workspace_id=$1",actor.workspace_id))==1
    assert db(http,app,"SELECT id FROM m1_app.jobs WHERE workspace_id=$1",actor.workspace_id)==[]
    repeated=triage(http,item)
    assert repeated.status_code==200 and repeated.json()["tender_id"]==results[0]["tender_id"]
    assert triage(http,repeated.json(),"dismiss").status_code==409
    detail=http.get("/api/v1/tenders/"+repeated.json()["tender_id"]).json()
    assert detail["opportunity"]["notice_version_id"]==item["notice_version_id"]
    assert detail["opportunity"]["notice"]["origin"]=="controlled_import"


def test_paused_authority_cannot_activate_or_reset_a_budget(client,actors):
    http,_,app=client
    item=imported(http)
    budget=approve(http,app,actors["owner"],item["id"])
    db(http,app,"UPDATE m1_app.workspace_spending_policies SET paused=true WHERE workspace_id=$1 RETURNING workspace_id",actors["owner"].workspace_id)
    assert triage(http,item).status_code==422
    assert len(db(http,app,"SELECT id FROM m1_app.stage_budgets WHERE id=$1",UUID(budget)))==1


def test_amendment_invalidates_inputs_without_replacing_case_budget_or_prior_spend(client,actors):
    http,_,app=client
    actor=actors["owner"]
    item=imported(http)
    budget=approve(http,app,actor,item["id"])
    db(http,app,"""INSERT INTO m1_app.usage_reservations(workspace_id,budget_id,actor_id,idempotency_key,request_hash,
       model,api,max_input_tokens,max_output_tokens,maximum_cost,price,state,outcome)
       VALUES($1,$2,$3,'prior-attempt','test','fictional','decisions',100,1,0.1,'{}','unknown','unknown') RETURNING id""",
       actor.workspace_id,UUID(budget),actor.user_id)
    activated=triage(http,item).json()
    amended=imported(http,notice_text="Fictional amended notice; attachment remains unavailable.")
    assert amended["state"]=="activated" and amended["tender_id"]==activated["tender_id"] and amended["budget_id"]==budget
    tender=http.get("/api/v1/tenders/"+activated["tender_id"]).json()
    assert tender["input_revision"]==2 and tender["opportunity"]["notice_version_id"]==amended["notice_version_id"]
    assert len(db(http,app,"SELECT id FROM m1_app.usage_reservations WHERE budget_id=$1",UUID(budget)))==1
    assert len(db(http,app,"SELECT id FROM m1_app.stage_budgets WHERE workspace_id=$1",actor.workspace_id))==1
    assert len(db(http,app,"SELECT id FROM m1_app.notice_versions WHERE suggestion_id=$1",UUID(item["id"])))==2


def test_bounded_personal_listing_has_stable_pagination_and_matching_reasons(client):
    http,_,_=client
    ids=[imported(http,notice_id="PAGE-"+str(n))["id"] for n in range(3)]
    outside=imported(http,notice_id="OTHER",title="Fictional stationery",category="Office supplies",notice_text="Paper only")
    assert not outside["match"]["relevant"]
    first=http.get("/api/v1/opportunity-suggestions?limit=2").json()
    second=http.get("/api/v1/opportunity-suggestions",params={"limit":2,"after":first["next_cursor"]}).json()
    assert {x["id"] for x in first["items"]+second["items"]}==set(ids)
    assert not set(x["id"] for x in first["items"])&set(x["id"] for x in second["items"])
    assert second["next_cursor"] is None
    assert http.get("/api/v1/opportunity-suggestions?limit=51").status_code==422


def test_configured_collector_records_failure_without_replacing_last_source(client,actors):
    from app.m1.jobs import run_notice_collection
    from app.m1.notice_sources import NoticeJob
    from test_notice_sources import URL,page
    http,_,app=client
    actor=actors["owner"]
    config=NoticeJob(key="fictional",workspace_id=actor.workspace_id,intake_owner_user_id=actor.user_id,
                    source_url=URL,enabled=True)
    async def run(handler):
        return await run_notice_collection(app.state.pool,"fictional",[config],transport=httpx.MockTransport(handler))
    first=http.portal.call(run,lambda request:httpx.Response(200,text=page(),headers={"content-type":"text/html"}))
    assert first["status"]=="collected" and first["suggestion"]["notice"]["origin"]=="public_notice"
    failed=http.portal.call(run,lambda request:httpx.Response(403))
    assert failed["status"]=="failed" and failed["error_code"]=="NOTICE_FETCH_FAILED"
    assert failed.get("unchanged") is None
    listed=http.get("/api/v1/opportunity-suggestions").json()["items"]
    assert len(listed)==1 and listed[0]["notice_version_id"]==first["suggestion"]["notice_version_id"]
    assert len(db(http,app,"SELECT id FROM m1_app.audit_events WHERE workspace_id=$1 AND action='notice_collection_failed'",actor.workspace_id))==1
    with pytest.raises(DomainError):
        http.portal.call(run_notice_collection,app.state.pool,"unknown-job",[config])


def test_revoked_intake_owner_cannot_persist_after_fetch(client,actors):
    from app.m1.jobs import run_notice_collection
    from app.m1.notice_sources import NoticeJob
    from test_notice_sources import URL,page
    http,_,app=client
    actor=actors["owner"]
    config=NoticeJob(key="revocation",workspace_id=actor.workspace_id,intake_owner_user_id=actor.user_id,
                    source_url=URL,enabled=True)
    async def handler(request):
        async with app.state.pool.acquire() as c:
            await c.execute("UPDATE m1_app.memberships SET roles=ARRAY['viewer'] WHERE workspace_id=$1 AND user_id=$2",
                            actor.workspace_id,actor.user_id)
        return httpx.Response(200,text=page(),headers={"content-type":"text/html"})
    with pytest.raises(DomainError) as error:
        http.portal.call(run_notice_collection,app.state.pool,"revocation",[config],httpx.MockTransport(handler))
    assert error.value.code=="FORBIDDEN"
    assert db(http,app,"SELECT id FROM m1_app.opportunity_suggestions WHERE workspace_id=$1",actor.workspace_id)==[]


def test_notice_facts_follow_the_activated_tender_listing(client,actors):
    http,_,app=client
    item=imported(http)
    approve(http,app,actors["owner"],item["id"])
    active=triage(http,item).json()
    row=next(x for x in http.get("/api/v1/tenders").json()["items"] if x["id"]==active["tender_id"])
    assert row["buyer"]=="Fictional Agency"
    assert row["closing_at"]=="2026-12-01T16:00:00+08:00"
    assert row["source_label"]=="controlled_import"


def test_same_workspace_bid_owner_cannot_triage_another_intake_owners_suggestion(client,actors):
    http,current,app=client
    item=imported(http)
    second=actors["viewer"]
    db(http,app,"UPDATE m1_app.memberships SET roles=ARRAY['bid_owner'] WHERE workspace_id=$1 AND user_id=$2 RETURNING user_id",
       second.workspace_id,second.user_id)
    current[0]=second
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    assert triage(http,item,"defer").status_code==404
    assert http.post("/api/v1/opportunity-suggestions/import",json=command()).status_code==403
