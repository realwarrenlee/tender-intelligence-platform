import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID,uuid4

import pytest

from app.tenders.models import ActorContext
from test_opportunities import imported,approve,triage,db
from test_retrieval import seed_parsed


class Decisions:
    async def classify_excerpt(self,*args):
        return {"answers":[{"name":"kind","label":"unknown"}],"usage_receipt":{"id":"controlled"}}


class Reasoner:
    def __init__(self,include_delivery=False): self.include_delivery=include_delivery
    async def interpret(self,context,hints):
        from test_screening import finding,candidate
        cite=context["excerpts"][0]
        answer=next((a for a in context["answers"] if "registration" in a["finding_ids"]),None)
        row=finding(status="supported" if answer and answer["response_kind"]=="confirmed" else "unconfirmed",
            tender_citations=[{"anchor_id":cite["anchor_id"],"quote":"Critical registration is required before submission."}],
            company_citations=[],answer_ids=[answer["id"]] if answer else [])
        rows=[row]
        if self.include_delivery and context.get("affected_ids") is None:
            rows.append(finding("staff",statement="Minimum staffing",kind="delivery_commitment",due_stage="mobilisation",
                critical=False,critical_basis=None,status="unconfirmed",company_citations=[],answer_ids=[],
                tender_citations=[{"anchor_id":cite["anchor_id"],"quote":"Minimum staffing is due during mobilisation."}]))
        return candidate(*rows)


@pytest.fixture
def screening_case(client,actors,request):
    from app.tenders.screening_workflow import execute_screening_job
    from functools import partial
    http,current,app=client
    app.state.qualification_enabled=True
    item=imported(http,notice_id="SCREEN-"+str(uuid4()),closing_at="2099-01-01T16:00:00+08:00")
    budget=approve(http,app,actors["owner"],item["id"])
    active=triage(http,item).json()
    tender=http.get("/api/v1/tenders/"+active["tender_id"]).json()
    reviewer=ActorContext(user_id=uuid4(),workspace_id=actors["owner"].workspace_id,roles={"member"})
    db(http,app,"INSERT INTO m1_app.memberships(workspace_id,user_id,roles) VALUES($1,$2,$3) RETURNING user_id",
       reviewer.workspace_id,reviewer.user_id,["member"])
    case=SimpleNamespace(http=http,current=current,app=app,actor=actors["owner"],reviewer=reviewer,
        tender=tender,item=item,budget=budget,run=partial(execute_screening_job,enabled=True))
    http.portal.call(seed_parsed,case,[{"filename":"instructions.pdf",
        "text":"Critical registration is required before submission. Minimum staffing is due during mobilisation.",
        "status":"partial" if getattr(request,"param",False)=="partial" else "complete"}])
    response=http.post("/api/v1/tenders/"+tender["id"]+"/screenings",json={
        "expected_input_revision":1,"client_request_id":str(uuid4())})
    assert response.status_code==202,response.text
    case.job=response.json()
    http.portal.call(case.run,app.state.pool,app.state.storage,UUID(case.job["id"]),Decisions(),Reasoner(getattr(request,"param",False) is True))
    case.review=http.get("/api/v1/review-cases/"+tender["id"]).json()
    return case


def confirm(c,draft="finding:registration",assignee=None):
    return c.http.post("/api/v1/tenders/"+c.tender["id"]+"/review-tasks",json={
        "expected_assessment_version_id":c.review["screening"]["id"],"draft_ref":draft,
        "assignee_id":str((assignee or c.reviewer).user_id),"due_at":"2098-12-30T10:00:00+08:00",
        "client_request_id":str(uuid4())})


def reply(c,task,**changes):
    return c.http.post("/api/v1/review-tasks/"+task["id"]+"/answers",json={
        "expected_task_revision":task["revision"],"response_kind":"confirmed",
        "text":"The bidding entity has current registration.","basis":"Checked current entity-specific registry evidence.",
        "client_request_id":str(uuid4()),**changes})


def make_ready(c):
    task=confirm(c).json();c.current[0]=c.reviewer
    response=reply(c,task)
    assert response.status_code==201,response.text
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,UUID(response.json()["reassessment_job_id"]),Decisions(),Reasoner())
    c.current[0]=c.actor
    c.review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert next(f for f in c.review["screening"]["artifact"]["findings"] if f["id"]=="registration")["status"]=="supported"
    return response.json()


def decide(c,task,**changes):
    body={"expected_input_revision":c.review["input_revision"],"expected_evidence_revision":c.review["evidence_revision"],
        "screening_version_id":c.review["screening"]["id"],"approval_task_id":task["id"],
        "outcome":"approve_preparation","reason":"Current scoped evidence reviewed.",
        "preparation_scope":"Prepare a draft bid and costed delivery approach.",
        "preparation_budget":{"amount":"1500","currency":"SGD"},"conditions":[],
        "client_request_id":str(uuid4()),**changes}
    return c.http.post("/api/v1/tenders/"+c.tender["id"]+"/preparation-decisions",json=body)


def test_disabled_new_entry_and_enabled_legacy_entry_are_explicit(client):
    http,_,app=client
    tender=http.post("/api/v1/tenders",json={"title":"Fictional","client_request_id":str(uuid4())}).json()
    body={"expected_input_revision":1,"client_request_id":str(uuid4())}
    assert http.post("/api/v1/tenders/"+tender["id"]+"/screenings",json=body).status_code==409
    app.state.qualification_enabled=True
    response=http.post("/api/v1/tenders/"+tender["id"]+"/analyses",json=body)
    assert response.status_code==409 and response.json()["code"]=="BOUNDED_WORKFLOW_REQUIRED"


def test_drafts_do_not_assign_and_confirmed_requests_are_personal(screening_case):
    c=screening_case
    assert c.review["screening"]["artifact"]["request_drafts"]
    assert c.http.get("/api/v1/inbox-actions").json()["items"]==[]
    assert not db(c.http,c.app,"SELECT id FROM m1_app.review_tasks WHERE tender_id=$1",UUID(c.tender["id"]))
    response=confirm(c)
    assert response.status_code==201,response.text
    task=response.json()
    c.current[0]=c.reviewer
    inbox=c.http.get("/api/v1/inbox-actions").json()["items"]
    assert len(inbox)==1 and inbox[0]["task_id"]==task["id"] and inbox[0]["tab"]=="human"
    c.current[0]=c.actor
    assert c.http.get("/api/v1/inbox-actions").json()["items"]==[]


def test_overview_answer_preserves_all_findings_and_carries_its_pinned_scope(screening_case):
    c=screening_case;task=confirm(c,"overview:reference").json()
    c.current[0]=c.reviewer
    response=reply(c,task,text="Check the cover reference.",basis="Inspected the cover; a source amendment is needed.")
    assert response.status_code==201,response.text
    job=db(c.http,c.app,"SELECT * FROM m1_app.jobs WHERE id=$1",UUID(response.json()["reassessment_job_id"]))[0]
    assert json.loads(job["manifest"])["affected_ids"]==[]
    answer=db(c.http,c.app,"SELECT payload FROM m1_app.artifact_versions WHERE id=$1",UUID(response.json()["evidence_version_id"]))[0]
    assert json.loads(answer["payload"])["overview_field"]=="reference"
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,job["id"],Decisions(),Reasoner())
    c.current[0]=c.actor
    result=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()["screening"]["artifact"]
    assert result["attention"]=="SCREENING_DEPENDENCY_WIDER_REQUIRED"
    assert result["findings"]==c.review["screening"]["artifact"]["findings"]


def test_old_tender_fingerprint_is_derived_from_pinned_history_without_rewriting_it(screening_case):
    from app.tenders.screening_workflow import _context
    c=screening_case
    legacy=json.loads(json.dumps(c.review["screening"]["artifact"]))
    legacy["pins"].pop("tender_source_signature")
    saved=db(c.http,c.app,"""INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
        SELECT workspace_id,tender_id,kind,input_revision,$2::jsonb,$3::jsonb,created_by FROM m1_app.artifact_versions WHERE id=$1 RETURNING id""",
        UUID(c.review["screening"]["id"]),json.dumps(legacy["pins"]),json.dumps(legacy))[0]["id"]
    response=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())})
    assert response.status_code==202,response.text
    job=db(c.http,c.app,"SELECT * FROM m1_app.jobs WHERE id=$1",UUID(response.json()["id"]))[0]
    ctx=c.http.portal.call(_context,c.app.state.pool,c.app.state.storage,c.actor,job)
    assert ctx["previous"]["pins"]["tender_source_signature"]==ctx["pins"]["tender_source_signature"]
    stored=json.loads(db(c.http,c.app,"SELECT payload FROM m1_app.artifact_versions WHERE id=$1",saved)[0]["payload"])
    assert "tender_source_signature" not in stored["pins"]


def test_preparation_work_requires_a_human_condition_even_when_not_material_now(screening_case,actors):
    c=screening_case;make_ready(c)
    # A controlled current artifact isolates the delegated decision rule from model semantics.
    from test_screening import finding
    artifact=c.review["screening"]["artifact"]
    artifact["findings"].append(finding("pricing",statement="Prepare the pricing schedule",kind="bid_artifact",
        material_now=False,status="unconfirmed",company_citations=[],critical=True,
        preparation_role="preparation_work",preparation_basis="Submit pricing at submission."))
    artifact["preparation_condition_ids"]=["pricing"]
    db(c.http,c.app,"""INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
        SELECT workspace_id,tender_id,kind,input_revision,manifest,$2::jsonb,created_by FROM m1_app.artifact_versions WHERE id=$1 RETURNING id""",
       UUID(c.review["screening"]["id"]),json.dumps(artifact))
    c.review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    denied=decide(c,task)
    assert denied.status_code==422 and denied.json()["code"]=="PREPARATION_CONDITIONS_REQUIRED"
    response=decide(c,task,conditions=[{"finding_id":"pricing","condition":"Finance to complete and review pricing before submission."}])
    assert response.status_code==201,response.text


def test_answer_is_attributed_atomic_scoped_and_queues_only_bounded_work(screening_case,actors):
    c=screening_case;task=confirm(c).json()
    for actor in (actors["owner"],actors["viewer"],actors["other"]):
        c.current[0]=actor
        assert reply(c,task).status_code in (403,404)
    c.current[0]=c.reviewer
    key=str(uuid4());first=reply(c,task,client_request_id=key)
    assert first.status_code==201,first.text
    assert reply(c,task,client_request_id=key).json()==first.json()
    assert reply(c,task).status_code==409
    rows=db(c.http,c.app,"SELECT * FROM m1_app.jobs WHERE id=$1",UUID(first.json()["reassessment_job_id"]))
    assert rows[0]["job_kind"]=="screening"
    assert json.loads(rows[0]["manifest"])["affected_ids"]==["registration"]
    saved=db(c.http,c.app,"SELECT actor_id FROM m1_app.review_answers WHERE task_id=$1",UUID(task["id"]))
    assert len(saved)==1 and saved[0]["actor_id"]==c.reviewer.user_id
    assert c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()["state"]=="Needs reassessment"


def test_confirmed_approval_request_goes_to_human_and_admin_has_no_business_authority(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json()
    c.current[0]=actors["approver"]
    inbox=c.http.get("/api/v1/inbox-actions").json()["items"]
    assert inbox[0]["tab"]=="human" and inbox[0]["kind"]=="preparation_approval"
    action=c.http.get("/api/v1/review-cases").json()["items"][0]["next_action"]
    assert action["assignee_id"]==str(actors["approver"].user_id)
    assert action["task_id"]==task["id"] and action["section"]=="questions"
    assert datetime.fromisoformat(action["due_at"])==datetime.fromisoformat(inbox[0]["due_at"])
    c.current[0]=actors["admin"].model_copy(update={"roles":{"member"}})
    assert decide(c,task).status_code==403
    c.current[0]=actors["approver"]
    assert decide(c,task,preparation_scope=None).status_code==422
    assert decide(c,task,preparation_budget=None).status_code==422
    assert decide(c,task,conditions=None).status_code==422
    response=decide(c,task)
    assert response.status_code==201,response.text
    assert response.json()["outcome"]=="approve_preparation" and response.json()["is_current"]
    review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert review["state"]=="Completed" and review["tender_stage"]=="preparing_bid"
    assert "final_release" not in response.json()


def test_critical_unknown_cannot_be_approved_but_request_information_keeps_an_owned_action(screening_case,actors):
    c=screening_case;task=confirm(c,"preparation",actors["approver"]).json()
    c.current[0]=actors["approver"]
    assert decide(c,task).status_code==422
    assert decide(c,task,outcome="request_information",next_assignee_id=str(actors["viewer"].user_id),
        information_request="Check the bidding entity registration.").status_code==422
    result=decide(c,task,outcome="request_information",next_assignee_id=str(c.actor.user_id),
        information_request="Resolve current entity registration before preparation.",due_at="2098-12-30T10:00:00+08:00")
    assert result.status_code==201,result.text
    c.current[0]=c.actor
    actions=c.http.get("/api/v1/inbox-actions").json()["items"]
    assert len(actions)==1 and actions[0]["kind"]=="information_request"
    review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert review["state"]=="Waiting for input" and review["next_actor_id"]==str(c.actor.user_id)


def test_source_amendment_invalidates_preparation_without_resetting_budget(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    assert decide(c,task).status_code==201
    c.current[0]=c.actor
    amended=imported(c.http,notice_id=c.item["notice"]["source_identity"].split("controlled:",1)[1],
        closing_at="2099-01-01T16:00:00+08:00",notice_text="Amended source notice.")
    assert amended["budget_id"]==c.budget
    review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert review["state"]=="Needs reassessment" and not review["preparation_decision"]["is_current"]
    c.current[0]=actors["approver"]
    assert decide(c,task).status_code==409


def test_team_read_visibility_does_not_grant_actions_and_foreign_case_is_hidden(screening_case,actors):
    c=screening_case;c.current[0]=actors["viewer"]
    review=c.http.get("/api/v1/review-cases/"+c.tender["id"])
    assert review.status_code==200 and review.json()["permitted_actions"]==[]
    sources=c.http.get("/api/v1/assessments/"+c.review["screening"]["id"]+"/sources")
    assert sources.status_code==200 and sources.json()["anchors"]
    assert c.http.get("/api/v1/review-cases").json()["items"][0]["tender_id"]==c.tender["id"]
    assert confirm(c).status_code==403
    c.current[0]=actors["other"]
    assert c.http.get("/api/v1/review-cases/"+c.tender["id"]).status_code==404
    assert c.http.get("/api/v1/assessments/"+c.review["screening"]["id"]+"/sources").status_code==404
    assert c.http.get("/api/v1/review-cases").json()["items"]==[]


def test_cancellation_and_late_source_changes_cannot_publish(screening_case):
    c=screening_case
    revision=c.review["input_revision"]
    job=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":revision,"client_request_id":str(uuid4())}).json()
    class Cancel(Reasoner):
        async def interpret(self,ctx,hints):
            async with c.app.state.pool.acquire() as conn:
                await conn.execute("UPDATE m1_app.jobs SET status='cancelled' WHERE id=$1",UUID(job["id"]))
            return await super().interpret(ctx,hints)
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,UUID(job["id"]),Decisions(),Cancel())
    saved=db(c.http,c.app,"SELECT status,output_version_id FROM m1_app.jobs WHERE id=$1",UUID(job["id"]))[0]
    assert saved["status"]=="cancelled" and saved["output_version_id"] is None


def test_company_revision_blocks_a_stale_preparation_command(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json()
    db(c.http,c.app,"UPDATE m1_app.workspaces SET evidence_revision=evidence_revision+1 WHERE id=$1 RETURNING id",c.actor.workspace_id)
    c.current[0]=actors["approver"]
    assert decide(c,task).status_code==409


def test_queue_failure_rolls_back_new_answer_and_revisions(screening_case,monkeypatch):
    from app.tenders import jobs
    c=screening_case;task=confirm(c).json();c.current[0]=c.reviewer
    class Unavailable:
        async def enqueue(self,*args,**kwargs): raise ConnectionError("Controlled queue failure")
    monkeypatch.setattr(jobs,"queue_queries",lambda connection:Unavailable())
    assert reply(c,task).status_code==503
    assert not db(c.http,c.app,"SELECT id FROM m1_app.review_answers WHERE task_id=$1",UUID(task["id"]))
    assert db(c.http,c.app,"SELECT input_revision FROM m1_app.tenders WHERE id=$1",UUID(c.tender["id"]))[0]["input_revision"]==c.review["input_revision"]


def test_rollback_disables_new_confirmations_but_keeps_evidence_readable(screening_case):
    c=screening_case;c.app.state.qualification_enabled=False
    assert confirm(c).status_code==409
    assert c.http.get("/api/v1/review-cases/"+c.tender["id"]).status_code==200
    fallback=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/analyses",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())})
    assert fallback.status_code==409 and fallback.json()["code"]=="BOUNDED_WORKFLOW_REQUIRED"


def test_supersession_and_finalization_do_not_deadlock(screening_case,monkeypatch):
    c=screening_case
    job=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())}).json()
    async def exercise():
        from app.tenders import screening_workflow
        held=asyncio.Event();entered=asyncio.Event();finishing=[False]
        original=screening_workflow.snapshot
        async def synchronized(conn,*args,**kwargs):
            if finishing[0]:
                entered.set()
                await asyncio.sleep(0)
            return await original(conn,*args,**kwargs)
        monkeypatch.setattr(screening_workflow,"snapshot",synchronized)
        async def supersede():
            async with c.app.state.pool.acquire() as conn,conn.transaction():
                await conn.fetchrow("SELECT id FROM m1_app.tenders WHERE id=$1 FOR UPDATE",UUID(c.tender["id"]))
                held.set()
                await entered.wait()
                await conn.execute("UPDATE m1_app.jobs SET status='cancelled' WHERE id=$1",UUID(job["id"]))
        class Concurrent(Reasoner):
            async def interpret(self,ctx,hints):
                self.other=asyncio.create_task(supersede())
                await held.wait()
                finishing[0]=True
                return await super().interpret(ctx,hints)
        reasoner=Concurrent()
        try:
            await c.run(c.app.state.pool,c.app.state.storage,UUID(job["id"]),Decisions(),reasoner)
        finally:
            entered.set()
            await reasoner.other
    c.http.portal.call(exercise)
    row=db(c.http,c.app,"SELECT status,output_version_id FROM m1_app.jobs WHERE id=$1",UUID(job["id"]))[0]
    assert row["status"]=="cancelled" and row["output_version_id"] is None


@pytest.mark.parametrize("screening_case",[True],indirect=True)
def test_team_review_and_human_actions_page_without_duplicates(screening_case,actors):
    c=screening_case
    ids={c.tender["id"]}
    for n in range(2):
        ids.add(c.http.post("/api/v1/tenders",json={"title":"Another fictional case "+str(n),
            "client_request_id":str(uuid4())}).json()["id"])
    one=c.http.get("/api/v1/review-cases?limit=2").json()
    two=c.http.get("/api/v1/review-cases",params={"limit":2,"after":one["next_cursor"]}).json()
    assert {x["tender_id"] for x in one["items"]+two["items"]}==ids and two["next_cursor"] is None
    assert not set(x["tender_id"] for x in one["items"])&set(x["tender_id"] for x in two["items"])
    assert all(x["screening"] is None for x in one["items"]+two["items"])
    first_task=confirm(c).json();second_task=confirm(c,"finding:staff").json()
    denied=confirm(c,"preparation",actors["viewer"])
    assert denied.status_code==422 and denied.json()["code"]=="INVALID_ASSIGNEE"
    assert confirm(c,"preparation",c.actor).status_code==201
    c.current[0]=c.reviewer
    first=c.http.get("/api/v1/inbox-actions?limit=1").json()
    second=c.http.get("/api/v1/inbox-actions",params={"limit":1,"after":first["next_cursor"]}).json()
    assert {x["task_id"] for x in first["items"]+second["items"]}=={first_task["id"],second_task["id"]}
    assert second["next_cursor"] is None


@pytest.mark.parametrize("screening_case",[True],indirect=True)
def test_material_future_duty_can_have_explicit_preparation_conditions(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    assert decide(c,task).status_code==422
    response=decide(c,task,conditions=[{"finding_id":"staff","condition":"Obtain an accepted mobilisation staffing plan before committing delivery resources."}])
    assert response.status_code==201,response.text
    assert response.json()["outcome"]=="approve_preparation"


def test_preparation_replay_does_not_resurrect_a_superseded_decision(screening_case,actors):
    c=screening_case
    first_task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    key=str(uuid4())
    changes={"outcome":"request_information","next_assignee_id":str(c.actor.user_id),
        "information_request":"Provide entity-specific confirmation.","client_request_id":key}
    first=decide(c,first_task,**changes)
    assert first.status_code==201,first.text
    c.current[0]=c.actor
    second_task=confirm(c,"preparation",actors["approver"]).json()
    c.current[0]=actors["approver"]
    assert decide(c,second_task).status_code==422
    assert decide(c,second_task,outcome="decline").status_code==201
    pending=db(c.http,c.app,"SELECT id,status,revision FROM m1_app.review_tasks WHERE tender_id=$1 AND purpose='information_request'",UUID(c.tender["id"]))[0]
    assert pending["status"]=="cancelled"
    c.current[0]=c.actor
    assert not c.http.get("/api/v1/inbox-actions").json()["items"]
    assert reply(c,{"id":str(pending["id"]),"revision":1}).status_code==409
    c.current[0]=actors["approver"]
    replay=decide(c,first_task,**changes)
    assert replay.status_code==201 and not replay.json()["is_current"]


def test_late_source_change_fences_a_screening_result(screening_case):
    c=screening_case
    job=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())}).json()
    class Changed(Reasoner):
        async def interpret(self,ctx,hints):
            async with c.app.state.pool.acquire() as conn:
                await conn.execute("UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1",UUID(c.tender["id"]))
            return await super().interpret(ctx,hints)
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,UUID(job["id"]),Decisions(),Changed())
    row=db(c.http,c.app,"SELECT status,output_version_id FROM m1_app.jobs WHERE id=$1",UUID(job["id"]))[0]
    assert row["status"]=="non_current" and row["output_version_id"] is None


def test_starting_a_new_investigation_invalidates_preparation_immediately(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    assert decide(c,task).status_code==201
    c.current[0]=c.actor
    response=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())})
    assert response.status_code==202
    review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert review["state"]=="Needs reassessment"
    assert not review["screening_is_current"] and not review["preparation_decision"]["is_current"]
    assert db(c.http,c.app,"SELECT id FROM m1_app.stage_budgets WHERE tender_id=$1",UUID(c.tender["id"]))[0]["id"]==UUID(c.budget)


@pytest.mark.parametrize("screening_case",["partial"],indirect=True)
def test_partial_coverage_needs_a_confirmed_scoped_materiality_review(screening_case,actors):
    c=screening_case
    registration=confirm(c).json();coverage=confirm(c,"coverage_review").json()
    assert c.review["screening"]["artifact"]["coverage"]["source_complete"] is False
    c.current[0]=c.reviewer
    first=reply(c,registration)
    assert first.status_code==201
    second=reply(c,coverage,text="The specified unread paragraph region is only a decorative image.",
        basis="Inspected the exact source region named in this request; it adds no material condition.")
    assert second.status_code==201,second.text
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,UUID(second.json()["reassessment_job_id"]),Decisions(),Reasoner())
    c.current[0]=c.actor
    c.review=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert c.review["screening"]["artifact"]["coverage"]["source_complete"] is False
    assert c.review["screening"]["artifact"]["coverage"]["complete"]
    assert c.review["state"]=="Ready for decision"
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    assert decide(c,task).status_code==201

@pytest.mark.parametrize("mode",["success","uncertain","stale"])
def test_reasoning_provider_uses_shared_reservations_and_source_attempt_fences(screening_case,mode):
    from app.tenders.screening_workflow import ScreeningReasoner,_context
    from app.tenders.usage_budget import ModelPrice
    from app.tenders.policy import DomainError
    from test_stage_budget import usage
    c=screening_case
    queued=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"client_request_id":str(uuid4())}).json()
    row=db(c.http,c.app,"""UPDATE m1_app.jobs SET status='running',attempt=1,
        deadline_at=clock_timestamp()+interval '60 seconds' WHERE id=$1 RETURNING *""",UUID(queued["id"]))[0]
    async def exercise():
        context=await _context(c.app.state.pool,c.app.state.storage,c.actor,row)
        calls=[]
        async def count(**kwargs):
            if mode=="stale":
                async with c.app.state.pool.acquire() as conn:
                    await conn.execute("UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1",UUID(c.tender["id"]))
            return SimpleNamespace(input_tokens=1000)
        async def create(**kwargs):
            calls.append(kwargs)
            if mode=="uncertain": raise TimeoutError("private provider detail")
            raw=await Reasoner().interpret(context,[])
            return SimpleNamespace(status="completed",output_text=json.dumps(raw),id="controlled-provider-response",model="controlled-model",
                usage=SimpleNamespace(model_dump=lambda:usage(1000,100)))
        client=SimpleNamespace(responses=SimpleNamespace(input_tokens=SimpleNamespace(count=count),create=create))
        price=ModelPrice(input_per_million="1",cached_input_per_million="0.1",output_per_million="2")
        reasoner=ScreeningReasoner(c.app.state.pool,c.actor,row,{"controlled-model":price},"controlled-model",client)
        if mode=="success":
            result=await reasoner.interpret(context,[])
            assert result["findings"] and len(calls)==1 and "tools" not in calls[0]
        else:
            with pytest.raises(DomainError) as error: await reasoner.interpret(context,[])
            assert error.value.code==("STALE_SOURCE_INDEX" if mode=="stale" else "SCREENING_PROVIDER_UNAVAILABLE")
            assert "private provider" not in str(error.value)
        return calls
    calls=c.http.portal.call(exercise)
    receipts=db(c.http,c.app,"SELECT state,maximum_cost,actual_cost FROM m1_app.usage_reservations WHERE budget_id=$1",UUID(c.budget))
    if mode=="stale": assert not calls and not receipts
    else:
        assert len(receipts)==1
        assert receipts[0]["state"]==("settled" if mode=="success" else "unknown")
        if mode=="uncertain": assert receipts[0]["actual_cost"] is None and receipts[0]["maximum_cost"]>0


def test_native_upload_and_company_expiry_use_the_bounded_path(client,actors):
    from docx import Document
    from io import BytesIO
    from test_documents import upload
    from test_company_profile import command as company_command
    from test_screening import finding,candidate
    from app.tenders.screening_workflow import execute_screening_job
    http,current,app=client;app.state.qualification_enabled=True
    item=imported(http,notice_id="NATIVE-"+str(uuid4()),closing_at="2099-01-01T16:00:00+08:00")
    approve(http,app,actors["owner"],item["id"])
    active=triage(http,item).json()
    current[0]=actors["admin"]
    company=http.post("/api/v1/company-evidence/profile",json=company_command(
        effective_on="2020-01-01",expires_on="2027-01-01",
        profile={"content":"# Fictional Ltd\n\nFictional Ltd registration is current.","sources":[]}))
    assert company.status_code==201,company.text
    current[0]=actors["owner"]
    doc=Document();doc.add_paragraph("Critical registration is required before submission.")
    stream=BytesIO();doc.save(stream)
    result=upload(http,{"id":active["tender_id"]},files=[("instructions.docx",stream.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")],revision=2)
    assert result.status_code==201,result.text
    job=http.post("/api/v1/tenders/"+active["tender_id"]+"/screenings",json={
        "expected_input_revision":3,"client_request_id":str(uuid4())})
    assert job.status_code==202,job.text
    class ClaimsCompanySupport:
        async def interpret(self,ctx,hints):
            cite=ctx["excerpts"][0];company=ctx["company_excerpts"][0]
            return candidate(finding(status="supported",company_citations=[{"anchor_id":company["anchor_id"],"quote":company["quote"]}],
                tender_citations=[{"anchor_id":cite["anchor_id"],"quote":"Critical registration is required before submission."}]))
    from functools import partial
    http.portal.call(partial(execute_screening_job,enabled=True),app.state.pool,app.state.storage,
                     UUID(job.json()["id"]),Decisions(),ClaimsCompanySupport())
    review=http.get("/api/v1/review-cases/"+active["tender_id"]).json()
    assert review["screening"]["artifact"]["findings"][0]["status"]=="unconfirmed"
    assert "EVIDENCE_EXPIRED" in review["screening"]["artifact"]["company_evidence"]["gaps"]
    assert db(http,app,"SELECT id FROM m1_app.artifact_versions WHERE tender_id=$1 AND kind='parsed_sources'",UUID(active["tender_id"]))


def test_new_preparation_delegation_invalidates_old_approval(screening_case,actors):
    c=screening_case;make_ready(c)
    task=confirm(c,"preparation",actors["approver"]).json();c.current[0]=actors["approver"]
    key=str(uuid4())
    assert decide(c,task,client_request_id=key).status_code==201
    second=ActorContext(user_id=uuid4(),workspace_id=c.actor.workspace_id,roles={"member"})
    db(c.http,c.app,"INSERT INTO m1_app.memberships(workspace_id,user_id,roles) VALUES($1,$2,ARRAY['member']) RETURNING user_id",
       second.workspace_id,second.user_id)
    c.current[0]=c.actor
    newer=confirm(c,"preparation",second)
    assert newer.status_code==201,newer.text
    view=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()
    assert view["state"]=="Needs reassessment" and not view["preparation_decision"]["is_current"]
    c.current[0]=actors["approver"]
    assert not decide(c,task,client_request_id=key).json()["is_current"]
    c.current[0]=second
    assert decide(c,newer.json()).status_code==201
    c.current[0]=c.actor
    old_request=confirm(c,"preparation",actors["approver"]).json()
    current_request=confirm(c,"preparation",second).json()
    assert db(c.http,c.app,"SELECT status FROM m1_app.review_tasks WHERE id=$1",UUID(old_request["id"]))[0]["status"]=="cancelled"
    c.current[0]=actors["approver"]
    assert decide(c,old_request).status_code==403
    c.current[0]=second
    assert decide(c,current_request).status_code==201


def test_empty_bounded_search_retains_validated_same_source_work(screening_case):
    c=screening_case
    job=c.http.post("/api/v1/tenders/"+c.tender["id"]+"/screenings",json={
        "expected_input_revision":c.review["input_revision"],"investigation_queries":["no-such-evidence-xyz"],
        "client_request_id":str(uuid4())}).json()
    class NoCalls:
        async def classify_excerpt(self,*args): pytest.fail("Empty retrieval cannot dispatch classification.")
        async def interpret(self,*args): pytest.fail("Empty retrieval cannot dispatch reasoning.")
    c.http.portal.call(c.run,c.app.state.pool,c.app.state.storage,UUID(job["id"]),NoCalls(),NoCalls())
    current=c.http.get("/api/v1/review-cases/"+c.tender["id"]).json()["screening"]["artifact"]
    assert current["findings"]==c.review["screening"]["artifact"]["findings"]
    assert current["classifications"] and current["attention"]=="TENDER_EVIDENCE_REQUIRED"


def test_source_pane_resolves_summary_and_closing_separately_from_findings(client,actors):
    from app.tenders.screening_workflow import execute_screening_job
    from test_screening import finding,candidate
    from test_screening_summary import summary,summary_context
    http,current,app=client
    app.state.qualification_enabled=True
    item=imported(http,notice_id="FACT-SOURCE-"+str(uuid4()),closing_at="2099-01-01T16:00:00+08:00")
    approve(http,app,actors["owner"],item["id"])
    tender_id=triage(http,item).json()["tender_id"]
    case=SimpleNamespace(http=http,app=app,actor=actors["owner"],tender={"id":tender_id})
    gate="Critical registration is required before submission."
    closing="Closing submission deadline: 2099-01-01T16:00:00+08:00."
    overview="Overview: "+summary_context()["excerpts"][-1]["quote"]
    term_note="Overview note: Contract period: 60 months for store services."
    http.portal.call(seed_parsed,case,[{"filename":"gate.pdf","text":gate},
        {"filename":"deadline.pdf","text":closing},{"filename":"overview.pdf","text":overview},
        {"filename":"misc.pdf","text":term_note}])
    class FactReasoner:
        async def interpret(self,context,hints):
            cite=next(e for e in context["excerpts"] if gate in e["quote"])
            deadline=next(e for e in context["excerpts"] if closing in e["quote"])
            overview_cite=next(e for e in context["excerpts"] if overview in e["quote"])
            extracts=summary()
            for fact in extracts.values(): fact["citations"][0]["anchor_id"]=overview_cite["anchor_id"]
            term_cite=next(e for e in context["excerpts"] if term_note in e["quote"])
            term_support=extracts["contract_period"]["citations"][0]
            extracts["contract_period"]={"value":None,"citations":[]}
            return {**candidate(finding(status="unconfirmed",company_citations=[],tender_citations=[{"anchor_id":cite["anchor_id"],"quote":gate}])),
                "summary":extracts,"overview_issues":[{"field":"contract_period","kind":"conflicting",
                    "question":"Confirm which period applies to the store services.","citations":[term_support,
                        {"anchor_id":term_cite["anchor_id"],"quote":term_note}]}],
                "closing_at":"2099-01-01T16:00:00+08:00",
                "closing_citations":[{"anchor_id":deadline["anchor_id"],"quote":closing}]}
    response=http.post("/api/v1/tenders/"+tender_id+"/screenings",json={
        "expected_input_revision":1,"investigation_queries":["registration","closing","overview"],
        "client_request_id":str(uuid4())})
    assert response.status_code==202,response.text
    http.portal.call(execute_screening_job,app.state.pool,app.state.storage,UUID(response.json()["id"]),
        Decisions(),FactReasoner(),True)
    review=http.get("/api/v1/review-cases/"+tender_id).json()
    version=review["screening"]["id"]
    assert review["screening"]["artifact"]["attention"] is None
    assert review["screening"]["artifact"]["summary"]["scope"]["value"]==summary()["scope"]["value"]
    sources=http.get("/api/v1/assessments/"+version+"/sources")
    assert sources.status_code==200,sources.text
    assert {a["text"] for a in sources.json()["anchors"]}=={gate,closing,overview,term_note}
    current[0]=actors["other"]
    assert http.get("/api/v1/assessments/"+version+"/sources").status_code==404
    current[0]=actors["owner"]

    class InvalidSummary(FactReasoner):
        async def interpret(self,context,hints):
            result=await super().interpret(context,hints)
            result["summary"]["scope"]["citations"][0]["quote"]="Invented scope."
            return result
    job=http.post("/api/v1/tenders/"+tender_id+"/screenings",json={
        "expected_input_revision":1,"investigation_queries":["registration","closing","overview"],
        "client_request_id":str(uuid4())}).json()
    http.portal.call(execute_screening_job,app.state.pool,app.state.storage,UUID(job["id"]),
        Decisions(),InvalidSummary(),True)
    latest=http.get("/api/v1/review-cases/"+tender_id).json()["screening"]
    assert latest["id"]!=version
    assert latest["artifact"]["attention"]=="SCREENING_INVALID"
    assert latest["artifact"]["summary"] is None
    assert latest["artifact"]["findings"]==review["screening"]["artifact"]["findings"]
    assert {a["text"] for a in http.get("/api/v1/assessments/"+version+"/sources").json()["anchors"]}=={gate,closing,overview,term_note}
    assert any(i["kind"]=="conflicting" and i["field"]=="contract_period" for i in latest["artifact"]["overview_issues"])
    assert {a["text"] for a in http.get("/api/v1/assessments/"+latest["id"]+"/sources").json()["anchors"]}=={gate,closing,overview,term_note}


def test_browser_cutover_follows_server_and_retains_bounded_history(screening_case):
    c=screening_case
    assert c.http.get('/api/v1/me').json()['qualification_workflow_enabled'] is True
    c.app.state.qualification_enabled=False
    assert c.http.get('/api/v1/me').json()['qualification_workflow_enabled'] is False
    assert c.http.get('/api/v1/tenders/'+c.tender['id']).json()['workflow']=='screening'
