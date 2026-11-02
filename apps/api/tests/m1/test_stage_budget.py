"""Spending invariants against the real development DB; all model transport is controlled."""
import asyncio
from decimal import Decimal
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.m1.policy import DomainError


def budget_module():
    from app.m1 import usage_budget
    return usage_budget


@pytest.fixture
def budget_case(client, actors):
    module = budget_module()
    http, _, app = client
    from test_documents import create
    tender = create(http)
    actor = actors["owner"]

    async def seed():
        async with app.state.pool.acquire() as c:
            await c.execute("""
                INSERT INTO m1_app.workspace_spending_policies(workspace_id,daily_limit_usd,approved_by)
                VALUES($1,5,$2)
            """, actor.workspace_id, actors["approver"].user_id)
            return await c.fetchval("""
                INSERT INTO m1_app.stage_budgets(
                    workspace_id,tender_id,stage,scope_key,limit_usd,max_requests,max_responses_requests,
                    max_input_tokens,approved_by)
                VALUES($1,$2,'screening',$3,0.50,8,8,200000,$4) RETURNING id
            """, actor.workspace_id, UUID(tender["id"]), tender["id"], actors["approver"].user_id)

    budget_id = http.portal.call(seed)
    prices = {"controlled-model": module.ModelPrice(input_per_million="1",cached_input_per_million="0.1",output_per_million="2")}
    ledger = module.UsageBudget(app.state.pool, prices)
    return SimpleNamespace(http=http,app=app,actor=actor,tender=tender,budget_id=budget_id,ledger=ledger,prices=prices)


def limits(input_tokens=100000, output_tokens=100000, **changes):
    return budget_module().RequestLimits(model="controlled-model",input_tokens=input_tokens,output_tokens=output_tokens,**changes)


def reserve(case, key, maximum="0.30", request=None, actor=None, ledger=None):
    return case.http.portal.call(
        (ledger or case.ledger).reserve_call,case.budget_id,actor or case.actor,key,Decimal(maximum),request or limits())


def usage(input_tokens=100000, output_tokens=50000, cached=0):
    return {"input_tokens":input_tokens,"output_tokens":output_tokens,
            "input_tokens_details":{"cached_tokens":cached},"output_tokens_details":{"reasoning_tokens":0},
            "total_tokens":input_tokens+output_tokens}


def test_retry_and_new_answer_share_the_same_budget(budget_case):
    c = budget_case
    first = reserve(c,"job-1:initial")
    receipt = c.http.portal.call(c.ledger.settle_call,first,usage(),"completed")
    assert receipt["actual_cost"] == Decimal("0.20")
    # A restart/new job uses persisted spend, not an in-memory counter.
    restarted = budget_module().UsageBudget(c.app.state.pool,c.prices)
    second = reserve(c,"job-2:answer",ledger=restarted)
    c.http.portal.call(restarted.settle_call,second,usage(),"completed")
    with pytest.raises(DomainError) as error:
        reserve(c,"job-3:source-revision",ledger=restarted)
    assert error.value.code == "STAGE_BUDGET_EXHAUSTED"


def test_concurrent_reservations_cannot_overspend(budget_case):
    c = budget_case

    async def run():
        return await asyncio.gather(
            c.ledger.reserve_call(c.budget_id,c.actor,"concurrent-1",Decimal("0.30"),limits()),
            c.ledger.reserve_call(c.budget_id,c.actor,"concurrent-2",Decimal("0.30"),limits()),
            return_exceptions=True)

    results = c.http.portal.call(run)
    assert sum(isinstance(r,dict) for r in results) == 1
    assert [r.code for r in results if isinstance(r,DomainError)] == ["STAGE_BUDGET_EXHAUSTED"]


def test_unknown_outcome_holds_reservation(budget_case):
    c = budget_case
    first = reserve(c,"timeout")
    held = c.http.portal.call(c.ledger.settle_call,first,None,"unknown")
    assert held["state"] == "unknown" and held["actual_cost"] is None
    duplicate = reserve(c,"timeout")
    assert duplicate["id"] == first["id"] and not duplicate["dispatch"]
    with pytest.raises(DomainError) as error:
        reserve(c,"retry-after-timeout")
    assert error.value.code == "STAGE_BUDGET_EXHAUSTED"
    # A later usage receipt can resolve the hold, exactly once.
    receipt = c.http.portal.call(c.ledger.settle_call,first,usage(1000,1000),"completed")
    replay = c.http.portal.call(c.ledger.settle_call,first,usage(1000,1000),"completed")
    assert receipt["actual_cost"] == replay["actual_cost"] == Decimal("0.003")
    assert reserve(c,"after-reconciliation")["dispatch"]


def test_duplicate_reservation_is_not_new_dispatch_authority(budget_case):
    c = budget_case
    first = reserve(c,"double-click")
    duplicate = reserve(c,"double-click")
    assert first["dispatch"] and not duplicate["dispatch"]
    assert first["id"] == duplicate["id"]
    with pytest.raises(DomainError) as error:
        reserve(c,"double-click","0.31")
    assert error.value.code == "DUPLICATE_CONFLICT"


def test_foreign_workspace_budget_is_denied(budget_case,actors):
    with pytest.raises(DomainError) as error:
        reserve(budget_case,"foreign",actor=actors["other"])
    assert error.value.code == "NOT_FOUND"


def test_revoked_membership_cannot_reserve(budget_case):
    c = budget_case

    async def revoke():
        async with c.app.state.pool.acquire() as db:
            await db.execute("DELETE FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2",c.actor.workspace_id,c.actor.user_id)

    c.http.portal.call(revoke)
    with pytest.raises(DomainError) as error:
        reserve(c,"revoked")
    assert error.value.code == "FORBIDDEN"


def test_missing_prices_prevent_reservation(budget_case):
    c = budget_case
    unpriced = budget_module().UsageBudget(c.app.state.pool,{})
    with pytest.raises(DomainError) as error:
        reserve(c,"missing-price",ledger=unpriced)
    assert error.value.code == "MODEL_PRICING_MISSING"


def test_reservation_cannot_understate_worst_case_cost(budget_case):
    with pytest.raises(DomainError) as error:
        reserve(budget_case,"understated","0.01")
    assert error.value.code == "INVALID_COST_RESERVATION"


def test_cached_input_is_not_charged_twice_and_prices_are_pinned(budget_case):
    c = budget_case
    first = reserve(c,"cached")
    c.ledger.prices = {}
    receipt = c.http.portal.call(c.ledger.settle_call,first,usage(100000,50000,80000),"completed")
    # 20k regular input at $1/M + 80k cached at $0.10/M + 50k output at $2/M.
    assert receipt["actual_cost"] == Decimal("0.128")


@pytest.mark.parametrize("bad_usage",[{},{"input_tokens":True,"output_tokens":1},
    usage(-1,1),usage(1,1,2),usage(100001,100000)])
def test_missing_or_invalid_usage_never_releases_money(budget_case,bad_usage):
    c = budget_case
    first = reserve(c,"bad-usage")
    with pytest.raises(DomainError) as error:
        c.http.portal.call(c.ledger.settle_call,first,bad_usage,"completed")
    assert error.value.code in ("PROVIDER_USAGE_INVALID","PROVIDER_USAGE_EXCEEDED")
    with pytest.raises(DomainError):
        reserve(c,"after-bad-usage")


@pytest.mark.parametrize("column,value,key",[
    ("max_requests",1,"STAGE_REQUEST_LIMIT"),
    ("max_responses_requests",1,"STAGE_RESPONSES_LIMIT"),
    ("max_input_tokens",100000,"STAGE_INPUT_LIMIT"),
])
def test_request_and_token_limits_survive_settlement(budget_case,column,value,key):
    c = budget_case
    async def restrict():
        async with c.app.state.pool.acquire() as db:
            await db.execute(f"UPDATE m1_app.stage_budgets SET {column}=$2 WHERE id=$1",c.budget_id,value)
    c.http.portal.call(restrict)
    first = reserve(c,"first")
    c.http.portal.call(c.ledger.settle_call,first,usage(100000,0),"completed")
    with pytest.raises(DomainError) as error:
        reserve(c,"next")
    assert error.value.code == key


def test_workspace_daily_cap_is_shared_by_discovery_and_screening(budget_case):
    c = budget_case
    async def setup_discovery():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.workspace_spending_policies SET daily_limit_usd=0.50 WHERE workspace_id=$1",c.actor.workspace_id)
            return await db.fetchval("""
                INSERT INTO m1_app.stage_budgets(
                    workspace_id,stage,scope_key,limit_usd,max_requests,max_responses_requests,max_input_tokens,approved_by)
                VALUES($1,'discovery','workspace',0.50,8,8,200000,$2) RETURNING id
            """,c.actor.workspace_id,c.actor.user_id)
    discovery = c.http.portal.call(setup_discovery)
    first = c.http.portal.call(c.ledger.reserve_call,discovery,c.actor,"discovery",Decimal("0.30"),limits())
    with pytest.raises(DomainError) as error:
        reserve(c,"screening")
    assert error.value.code == "WORKSPACE_BUDGET_EXHAUSTED"
    assert first["state"] == "reserved"


@pytest.mark.parametrize("kind",["analysis","assistant"])
def test_unbound_legacy_provider_cannot_make_a_request(monkeypatch,kind):
    import openai
    from pydantic import SecretStr
    from app import config
    monkeypatch.setattr(config,"get_settings",lambda: SimpleNamespace(
        openai_api_key=SecretStr("controlled-test-key"),openai_model="controlled-model",openai_prices={}))
    from app.m1.analysis import OpenAIModel
    from app.m1.assistant import OpenAIAssistant

    def unexpected_network(*args,**kwargs):
        pytest.fail("An unbudgeted provider attempted to create a client")
    monkeypatch.setattr(openai,"AsyncOpenAI",unexpected_network)
    async def run():
        if kind == "analysis":
            return await OpenAIModel().generate({},{},"Controlled prompt",[])
        return await OpenAIAssistant().generate([],[],{},"Controlled prompt")
    with pytest.raises(DomainError) as error:
        asyncio.run(run())
    assert error.value.code == "USAGE_BUDGET_REQUIRED"

class ControlledClient:
    def __init__(self, on_count=None, failure=None):
        self.responses = self
        self.input_tokens = self
        self.on_count,self.failure = on_count,failure
        self.requests = []

    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass

    async def count(self,**request):
        if self.on_count: await self.on_count()
        return SimpleNamespace(input_tokens=100000)

    async def create(self,**request):
        self.requests.append(request)
        if self.failure: raise self.failure
        return SimpleNamespace(model="controlled-model",id="controlled-response",status="completed",
            output=[],output_text="{}",usage=SimpleNamespace(model_dump=lambda: usage(100000,10000)),
            model_dump=lambda **kwargs: {"output":[]})


@pytest.mark.parametrize("kind",["analysis","assistant"])
def test_legacy_adapters_use_the_shared_ledger_and_do_not_dispatch_past_token_cap(budget_case,monkeypatch,kind):
    import openai
    from pydantic import SecretStr
    from app import config
    from app.m1.analysis import OpenAIModel
    from app.m1.assistant import OpenAIAssistant
    from app.m1.usage_budget import PaidCall

    c = budget_case
    transport = ControlledClient()
    monkeypatch.setattr(config,"get_settings",lambda: SimpleNamespace(
        openai_api_key=SecretStr("controlled-test-key"),openai_model="controlled-model",openai_prices=c.prices))
    monkeypatch.setattr(openai,"AsyncOpenAI",lambda **kwargs: transport)

    async def call(key):
        scope = PaidCall(c.app.state.pool,c.actor,UUID(c.tender["id"]),key)
        if kind == "analysis":
            return await OpenAIModel().generate({},{},"Controlled",[],paid_call=scope)
        return await OpenAIAssistant().generate([],[],{},"Controlled",paid_call=scope)

    c.http.portal.call(call,"first")
    c.http.portal.call(call,"second")
    with pytest.raises(DomainError) as error:
        c.http.portal.call(call,"third")
    assert error.value.code == "STAGE_INPUT_LIMIT"
    assert len(transport.requests) == 2
    assert all(r["service_tier"] == "default" and r["max_output_tokens"] == 12000 for r in transport.requests)
    async def inspect():
        async with c.app.state.pool.acquire() as db:
            row = await db.fetchrow("""
                SELECT count(*) AS calls,sum(actual_cost) AS cost,sum(actual_input_tokens) AS tokens
                FROM m1_app.usage_reservations WHERE budget_id=$1
            """,c.budget_id)
            assert dict(row) == {"calls":2,"cost":Decimal("0.24"),"tokens":200000}
            assert await db.fetchval(
                "SELECT provider_usage->>'response_id' FROM m1_app.usage_reservations WHERE budget_id=$1 LIMIT 1",
                c.budget_id) == "controlled-response"
    c.http.portal.call(inspect)


def test_transport_failure_and_replay_keep_money_without_redispatch(budget_case):
    from app.m1.usage_budget import PaidCall
    c = budget_case
    transport = ControlledClient(failure=ConnectionError("Controlled unknown outcome"))
    scope = PaidCall(c.app.state.pool,c.actor,UUID(c.tender["id"]),"lost-response")
    request = {"model":"controlled-model","input":"Controlled","max_output_tokens":100000}
    with pytest.raises(ConnectionError):
        c.http.portal.call(scope.create_response,transport,request,c.prices)
    with pytest.raises(DomainError) as error:
        c.http.portal.call(scope.create_response,transport,request,c.prices)
    assert error.value.code == "MODEL_OUTCOME_UNKNOWN"
    assert len(transport.requests) == 1
    with pytest.raises(DomainError) as error:
        reserve(c,"new-attempt")
    assert error.value.code == "STAGE_BUDGET_EXHAUSTED"


@pytest.mark.parametrize("change,code",[
    ("cancel","JOB_NOT_ACTIVE"),("amend","STALE_ANALYSIS"),("attempt","ATTEMPT_SUPERSEDED"),
])
def test_paid_reservation_rechecks_the_job_after_token_count(budget_case,change,code):
    from app.m1.analysis_runtime import ModelLedger
    c = budget_case
    async def seed():
        async with c.app.state.pool.acquire() as db:
            return await db.fetchval("""
                INSERT INTO m1_app.jobs(workspace_id,tender_id,input_revision,manifest,status,attempt,created_by,deadline_at)
                VALUES($1,$2,1,'{}','running',1,$3,now()+interval '60 seconds') RETURNING id
            """,c.actor.workspace_id,UUID(c.tender["id"]),c.actor.user_id)
    job_id = c.http.portal.call(seed)
    ledger = ModelLedger(c.app.state.pool,job_id,c.actor.workspace_id,expected_attempt=1)
    scope = c.http.portal.call(ledger.paid_call,1)
    async def mutate():
        async with c.app.state.pool.acquire() as db:
            if change == "cancel":
                await db.execute("UPDATE m1_app.jobs SET status='cancelled' WHERE id=$1",job_id)
            elif change == "attempt":
                await db.execute("UPDATE m1_app.jobs SET attempt=2 WHERE id=$1",job_id)
            else:
                await db.execute("UPDATE m1_app.tenders SET input_revision=2 WHERE id=$1",UUID(c.tender["id"]))
    transport = ControlledClient(on_count=mutate)
    request = {"model":"controlled-model","input":"Controlled","max_output_tokens":12000}
    with pytest.raises(DomainError) as error:
        c.http.portal.call(scope.create_response,transport,request,c.prices)
    assert error.value.code == code
    assert not transport.requests


def test_two_tender_budgets_share_one_atomic_daily_limit(budget_case):
    c = budget_case
    async def run():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.workspace_spending_policies SET daily_limit_usd=0.50 WHERE workspace_id=$1",c.actor.workspace_id)
            discovery = await db.fetchval("""
                INSERT INTO m1_app.stage_budgets(workspace_id,stage,scope_key,limit_usd,
                    max_requests,max_responses_requests,max_input_tokens,approved_by)
                VALUES($1,'discovery','daily-race',0.50,8,8,200000,$2) RETURNING id
            """,c.actor.workspace_id,c.actor.user_id)
        return await asyncio.gather(
            c.ledger.reserve_call(c.budget_id,c.actor,"screening-race",Decimal("0.30"),limits()),
            c.ledger.reserve_call(discovery,c.actor,"discovery-race",Decimal("0.30"),limits()),
            return_exceptions=True)
    results = c.http.portal.call(run)
    assert sum(isinstance(r,dict) for r in results) == 1
    assert [r.code for r in results if isinstance(r,DomainError)] == ["WORKSPACE_BUDGET_EXHAUSTED"]

def test_job_answer_and_source_revision_resolve_to_one_budget(budget_case):
    from app.m1.analysis_runtime import ModelLedger
    from app.m1.assistant_runtime import TurnLedger
    c = budget_case
    tender_id = UUID(c.tender["id"])

    async def seed():
        async with c.app.state.pool.acquire() as db:
            job_id = await db.fetchval("""
                INSERT INTO m1_app.jobs(workspace_id,tender_id,input_revision,manifest,status,attempt,created_by,deadline_at)
                VALUES($1,$2,1,'{}','running',1,$3,now()+interval '60 seconds') RETURNING id
            """,c.actor.workspace_id,tender_id,c.actor.user_id)
            assessment_id = await db.fetchval("""
                INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
                VALUES($1,$2,'assessment',1,'{}','{}',$3) RETURNING id
            """,c.actor.workspace_id,tender_id,c.actor.user_id)
            run_id = await db.fetchval("""
                INSERT INTO m1_app.assistant_runs(workspace_id,tender_id,assessment_version_id,actor_id,status)
                VALUES($1,$2,$3,$4,'running') RETURNING id
            """,c.actor.workspace_id,tender_id,assessment_id,c.actor.user_id)
            return job_id,run_id

    job_id,run_id = c.http.portal.call(seed)
    job_scope = c.http.portal.call(ModelLedger(c.app.state.pool,job_id,c.actor.workspace_id,expected_attempt=1).paid_call,1)
    answer_scope = c.http.portal.call(TurnLedger(c.app.state.pool,run_id,c.actor.workspace_id).paid_call,1)
    request = {"model":"controlled-model","input":"Controlled","max_output_tokens":100000}
    transport = ControlledClient()
    c.http.portal.call(job_scope.create_response,transport,request,c.prices)
    c.http.portal.call(answer_scope.create_response,transport,request,c.prices)

    async def new_job():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.tenders SET input_revision=2 WHERE id=$1",tender_id)
            return await db.fetchval("""
                INSERT INTO m1_app.jobs(workspace_id,tender_id,input_revision,manifest,status,attempt,created_by,deadline_at)
                VALUES($1,$2,2,'{}','running',1,$3,now()+interval '60 seconds') RETURNING id
            """,c.actor.workspace_id,tender_id,c.actor.user_id)
    next_id = c.http.portal.call(new_job)
    next_scope = c.http.portal.call(ModelLedger(c.app.state.pool,next_id,c.actor.workspace_id,expected_attempt=1).paid_call,1)
    with pytest.raises(DomainError) as error:
        c.http.portal.call(next_scope.create_response,transport,request,c.prices)
    assert error.value.code == "STAGE_BUDGET_EXHAUSTED"
    assert len(transport.requests) == 2
    assert c.http.portal.call(c.ledger.tender_budget,c.actor,tender_id) == c.budget_id


def test_unapproved_budget_never_reaches_token_count_or_generation(budget_case):
    from app.m1.usage_budget import PaidCall
    c = budget_case
    async def pause():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.workspace_spending_policies SET paused=true WHERE workspace_id=$1",c.actor.workspace_id)
    c.http.portal.call(pause)
    async def unexpected_count():
        pytest.fail("An unapproved request transmitted source material")
    transport = ControlledClient(on_count=unexpected_count)
    scope = PaidCall(c.app.state.pool,c.actor,UUID(c.tender["id"]),"paused")
    with pytest.raises(DomainError) as error:
        c.http.portal.call(scope.create_response,transport,
            {"model":"controlled-model","input":"Controlled","max_output_tokens":12000},c.prices)
    assert error.value.code == "USAGE_BUDGET_REQUIRED"
    assert not transport.requests


def test_spending_tables_are_private_and_use_row_security(client):
    http,_,app = client
    async def inspect():
        async with app.state.pool.acquire() as db:
            for table in ("workspace_spending_policies","stage_budgets","usage_reservations"):
                assert await db.fetchval(
                    "SELECT relrowsecurity FROM pg_class WHERE oid=$1::regclass","m1_app."+table)
                for role in ("anon","authenticated"):
                    assert not await db.fetchval(
                        "SELECT has_table_privilege($1,$2,'SELECT,INSERT,UPDATE,DELETE')",role,"m1_app."+table)
    http.portal.call(inspect)

def test_over_reservation_usage_pauses_workspace_and_preserves_evidence(budget_case):
    c = budget_case
    async def seed():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.workspace_spending_policies SET daily_limit_usd=0.50 WHERE workspace_id=$1",c.actor.workspace_id)
            return await db.fetchval("""
                INSERT INTO m1_app.stage_budgets(workspace_id,stage,scope_key,limit_usd,
                    max_requests,max_responses_requests,max_input_tokens,approved_by)
                VALUES($1,'discovery','overage',0.50,8,8,200000,$2) RETURNING id
            """,c.actor.workspace_id,c.actor.user_id)
    discovery = c.http.portal.call(seed)
    first = reserve(c,"anomalous-usage")
    anomalous = usage(100000,250000)  # $0.60 observed against $0.30 reserved.
    with pytest.raises(DomainError) as error:
        c.http.portal.call(c.ledger.settle_call,first,anomalous,"completed")
    assert error.value.code == "PROVIDER_USAGE_EXCEEDED"
    with pytest.raises(DomainError) as error:
        c.http.portal.call(c.ledger.reserve_call,discovery,c.actor,"after-overage",Decimal("0.20"),limits(50000,75000))
    assert error.value.code == "USAGE_BUDGET_REQUIRED"
    async def inspect():
        async with c.app.state.pool.acquire() as db:
            assert await db.fetchval("SELECT paused FROM m1_app.workspace_spending_policies WHERE workspace_id=$1",c.actor.workspace_id)
            stored = await db.fetchval("SELECT provider_usage FROM m1_app.usage_reservations WHERE id=$1",first["id"])
            assert json.loads(stored) == anomalous
    c.http.portal.call(inspect)

@pytest.mark.parametrize("kind,code",[("job","JOB_NOT_ACTIVE"),("assistant","ASSISTANT_NOT_ACTIVE")])
def test_lock_wait_cannot_authorise_work_after_its_deadline(budget_case,kind,code):
    c = budget_case
    tender_id = UUID(c.tender["id"])

    async def run():
        async with c.app.state.pool.acquire() as holder:
            if kind == "job":
                run_id = await holder.fetchval("""
                    INSERT INTO m1_app.jobs(workspace_id,tender_id,input_revision,manifest,status,attempt,created_by,deadline_at)
                    VALUES($1,$2,1,'{}','running',1,$3,now()+interval '60 seconds') RETURNING id
                """,c.actor.workspace_id,tender_id,c.actor.user_id)
                request = limits(job_id=run_id,expected_attempt=1)
                table = "m1_app.jobs"
            else:
                assessment_id = await holder.fetchval("""
                    INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
                    VALUES($1,$2,'assessment',1,'{}','{}',$3) RETURNING id
                """,c.actor.workspace_id,tender_id,c.actor.user_id)
                run_id = await holder.fetchval("""
                    INSERT INTO m1_app.assistant_runs(workspace_id,tender_id,assessment_version_id,actor_id,status)
                    VALUES($1,$2,$3,$4,'running') RETURNING id
                """,c.actor.workspace_id,tender_id,assessment_id,c.actor.user_id)
                request = limits(assistant_run_id=run_id)
                table = "m1_app.assistant_runs"
            holder_pid = await holder.fetchval("SELECT pg_backend_pid()")
            async with holder.transaction():
                await holder.fetchrow("SELECT * FROM m1_app.workspace_spending_policies WHERE workspace_id=$1 FOR UPDATE",c.actor.workspace_id)
                pending = asyncio.create_task(c.ledger.reserve_call(c.budget_id,c.actor,"expiry-race",Decimal("0.30"),request))
                for _ in range(100):
                    # Activity snapshots are transaction-cached; the waiting backend may have connected after the first probe.
                    await holder.execute("SELECT pg_stat_clear_snapshot()")
                    blocked = await holder.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE $1=ANY(pg_blocking_pids(pid)))",holder_pid)
                    if blocked: break
                    await asyncio.sleep(0.01)
                assert blocked, "The reservation must be waiting before the deadline is changed."
                await holder.execute(f"UPDATE {table} SET deadline_at=clock_timestamp()+interval '50 milliseconds' WHERE id=$1",run_id)
                await asyncio.sleep(0.15)
            return await pending

    with pytest.raises(DomainError) as error:
        c.http.portal.call(run)
    assert error.value.code == code
