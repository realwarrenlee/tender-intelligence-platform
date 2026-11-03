import asyncio
import json
from uuid import UUID,uuid4

import httpx
import pytest

from app.tenders.policy import DomainError


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


def test_dismiss_replay_and_stale_commands_preserve_history(client):
    http,_,app=client
    item=imported(http)
    request_id=str(uuid4())
    assert triage(http,item,"defer").status_code==422
    dismissed=triage(http,item,"dismiss",client_request_id=request_id)
    assert dismissed.status_code==200 and dismissed.json()["state"]=="dismissed"
    assert triage(http,item,"dismiss",client_request_id=request_id).json()==dismissed.json()
    assert triage(http,item,"dismiss").status_code==409
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    assert http.get("/api/v1/opportunity-suggestions?state=dismissed").json()["items"][0]["id"]==item["id"]
    assert len(db(http,app,"SELECT * FROM m1_app.opportunity_triage_events WHERE suggestion_id=$1",UUID(item["id"])))==1


def test_business_roles_workspace_and_intake_owner_are_enforced(client,actors):
    http,current,app=client
    item=imported(http)
    for name,status,import_error in (("admin",404,"INTAKE_OWNER_REQUIRED"),
        ("viewer",403,"FORBIDDEN"),("approver",404,"INTAKE_OWNER_REQUIRED")):
        current[0]=actors[name]
        response=http.post("/api/v1/opportunity-suggestions/import",json=command())
        assert response.status_code==403 and response.json()["code"]==import_error
        assert triage(http,item,"dismiss").status_code==status
        assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    current[0]=actors["other"]
    assert triage(http,item,"dismiss").status_code==404
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    current[0]=actors["owner"]
    for extra in ({"origin":"public_notice"},{"intake_owner_user_id":str(uuid4())},{"budget_usd":1},{"source_url":"https://evil.example"},{"workspace_id":str(uuid4())}):
        assert http.post("/api/v1/opportunity-suggestions/import",json=command(**extra)).status_code==422


def test_forwarded_notice_and_reply_are_visible_only_to_participants(client,actors):
    http,current,app=client
    item=imported(http)
    base='/api/v1/opportunity-feedback'
    recipient=actors['approver']
    sent=http.post(f"/api/v1/opportunity-suggestions/{item['id']}/feedback",json={
        'expected_revision':item['revision'],'recipient_id':str(recipient.user_id),
        'question':'Do we have the right experience?','client_request_id':str(uuid4()),
    })
    assert sent.status_code==201
    feedback_id=sent.json()['id']
    assert sent.json()['notice']['title']==item['notice']['title']
    assert sent.json()['answer'] is None
    assert len(http.get(base).json()['items'])==1
    assert db(http,app,'SELECT id FROM m1_app.tenders WHERE workspace_id=$1',recipient.workspace_id)==[]
    reply={'answer':'Yes, check the FM references.','client_request_id':str(uuid4())}
    current[0]=actors['admin']
    assert http.get(base).json()['items']==[]
    assert http.post(f'{base}/{feedback_id}/answer',json=reply).status_code==404
    current[0]=recipient
    assert http.get(base).json()['items'][0]['id']==feedback_id
    result=http.post(f'{base}/{feedback_id}/answer',json=reply)
    assert result.status_code==200 and result.json()['answer']==reply['answer']
    current[0]=actors['owner']
    assert http.get(base).json()['items'][0]['answer']==reply['answer']


def test_activation_without_budget_creates_case_without_starting_screening(client,actors,monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'qualification_workflow_enabled',True)
    http,_,app=client
    item=imported(http)
    response=triage(http,item)
    assert response.status_code==200
    tender_id=response.json()['tender_id']
    assert tender_id and response.json()['budget_status']=='not_approved'
    assert db(http,app,'SELECT id FROM m1_app.jobs WHERE workspace_id=$1',actors['owner'].workspace_id)==[]
    screening=http.post(f'/api/v1/tenders/{tender_id}/screenings',json={
        'expected_input_revision':1,'client_request_id':str(uuid4())})
    assert screening.status_code==422 and screening.json()['code']=='USAGE_BUDGET_REQUIRED'


def test_schedule_switch_is_workspace_scoped_and_controls_collection(client,actors,monkeypatch):
    from app.config import get_settings
    from app.tenders.jobs import run_notice_collection
    from app.tenders.notice_sources import LISTING_URL,NoticeJob
    http,current,app=client
    owner=actors['owner']
    job=NoticeJob(key='test-scan',workspace_id=owner.workspace_id,intake_owner_user_id=owner.user_id,
                  source_url=LISTING_URL,enabled=True)
    monkeypatch.setattr(get_settings(),'notice_source_jobs',[job])
    monkeypatch.setattr(get_settings(),'qualification_workflow_enabled',True)
    path='/api/v1/opportunity-discovery'
    assert http.get(path).json()=={'configured':True,'enabled':True,'can_edit':True}
    current[0]=actors['viewer']
    assert http.put(path,json={'enabled':False}).status_code==403
    current[0]=owner
    assert http.put(path,json={'enabled':False}).json()['enabled'] is False
    result=http.portal.call(run_notice_collection,app.state.pool,job.key,[job],
                            httpx.MockTransport(lambda _: pytest.fail('A disabled scan fetched GeBIZ')))
    assert result=={'status':'disabled'}
    assert http.put(path,json={'enabled':True}).json()['enabled'] is True
    current[0]=actors['other']
    assert http.get(path).json()['configured'] is False


def test_daily_collection_places_a_matching_notice_in_the_owners_inbox_once(client,actors):
    from app.tenders.jobs import run_notice_collection
    from app.tenders.notice_sources import LISTING_URL,NoticeJob
    from test_notice_sources import page

    http,current,app=client
    owner=actors['owner']
    job=NoticeJob(key='test-scan',workspace_id=owner.workspace_id,intake_owner_user_id=owner.user_id,
                  source_url=LISTING_URL,enabled=True)
    def response(request):
        if str(request.url)==LISTING_URL:
            return httpx.Response(200,text='''<input name="javax.faces.ViewState" value="state">
                <a href="/ptn/opportunity/directlink.xhtml?docCode=PAS000ETT26000081">Tender</a>''')
        return httpx.Response(200,text=page(closing='27 Nov 2099<br>04:00PM'),
                              headers={'content-type':'text/html'})
    transport=httpx.MockTransport(response)
    for _ in range(2):
        result=http.portal.call(run_notice_collection,app.state.pool,job.key,[job],transport)
        assert result=={'status':'collected','matched':1,'failed':0}
    path='/api/v1/opportunity-suggestions'
    items=http.get(path).json()['items']
    assert [(item['notice']['reference'],item['notice_version']) for item in items]==[('PAS000ETT26000081',1)]
    current[0]=actors['approver']
    assert http.get(path).json()['items']==[]


def test_concurrent_starts_share_case_and_budget(client,actors):
    from app.tenders.models import TriageSuggestion
    from app.tenders.opportunities import Opportunities
    http,_,app=client
    actor=actors["owner"]
    item=imported(http)
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


def test_paused_authority_remains_blocked_after_activation(client,actors):
    http,_,app=client
    item=imported(http)
    budget=approve(http,app,actors["owner"],item["id"])
    db(http,app,"UPDATE m1_app.workspace_spending_policies SET paused=true WHERE workspace_id=$1 RETURNING workspace_id",actors["owner"].workspace_id)
    response=triage(http,item)
    assert response.status_code==200 and response.json()['budget_status']=='blocked'
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
    from app.tenders.jobs import run_notice_collection
    from app.tenders.notice_sources import NoticeJob
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
    from app.tenders.jobs import run_notice_collection
    from app.tenders.notice_sources import NoticeJob
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


def test_same_workspace_member_cannot_triage_another_intake_owners_suggestion(client,actors):
    http,current,_=client
    item=imported(http)
    current[0]=actors["approver"]
    assert http.get("/api/v1/opportunity-suggestions").json()["items"]==[]
    assert triage(http,item,"dismiss").status_code==404
    response=http.post("/api/v1/opportunity-suggestions/import",json=command())
    assert response.status_code==403 and response.json()["code"]=="INTAKE_OWNER_REQUIRED"
    own=imported(http,notice_id="FICT-002")
    assert own["intake_owner_user_id"]==str(actors["approver"].user_id)
