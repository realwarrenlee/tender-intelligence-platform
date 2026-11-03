"""Persistent USD reservations shared across jobs, revisions and provider adapters."""
from dataclasses import dataclass
import asyncio
from decimal import Decimal
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.tenders.models import ActorContext
from app.tenders.policy import DomainError

INPUT_TOKEN_HEADROOM=32


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input_per_million: Decimal = Field(ge=0)
    cached_input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)
    cache_write_per_million: Decimal | None = Field(default=None,ge=0)

    @model_validator(mode="after")
    def check_cache_rate(self):
        if self.cached_input_per_million > self.input_per_million:
            raise ValueError("Cached input cannot exceed the reserved regular input rate.")
        return self

    def maximum_cost(self,input_tokens,output_tokens):
        rate=max(self.input_per_million,self.cached_input_per_million,
                 self.cache_write_per_million if self.cache_write_per_million is not None else self.input_per_million)
        return (input_tokens*rate+output_tokens*self.output_per_million)/Decimal(1000000)

    def cost(self, input_tokens, output_tokens, cached_tokens=0, cache_write_tokens=0):
        if cache_write_tokens and self.cache_write_per_million is None:
            raise ValueError("Cache-write pricing is required for reported cache writes.")
        return ((input_tokens-cached_tokens-cache_write_tokens)*self.input_per_million
                + cached_tokens*self.cached_input_per_million
                + cache_write_tokens*(self.cache_write_per_million or Decimal(0))
                + output_tokens*self.output_per_million)/Decimal(1000000)


class RequestLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1)
    api: Literal["responses","decisions"] = "responses"
    input_tokens: int = Field(ge=0,strict=True)
    counted_input_tokens: int | None = Field(default=None,ge=0,strict=True)
    output_tokens: int = Field(gt=0,strict=True)
    request_sha256: str = ""
    job_id: UUID | None = None
    expected_attempt: int | None = None
    assistant_run_id: UUID | None = None
    source_index_version_id: UUID | None = None


def receipt(row, dispatch=False):
    return {**dict(row),"dispatch":dispatch}


class UsageBudget:
    def __init__(self, pool, prices):
        self.pool,self.prices = pool,prices

    def price(self, model):
        price = self.prices.get(model)
        if price is None:
            raise DomainError(422,"MODEL_PRICING_MISSING","Configure explicit USD token prices before dispatch.")
        return price

    async def tender_budget(self, actor, tender_id):
        async with self.pool.acquire() as c:
            await self._member(c,actor)
            budget_id = await c.fetchval("""
                SELECT b.id FROM m1_app.stage_budgets b
                JOIN m1_app.workspace_spending_policies p ON p.workspace_id=b.workspace_id
                JOIN m1_app.tenders t ON t.workspace_id=b.workspace_id AND t.id=b.tender_id
                WHERE b.workspace_id=$1 AND b.tender_id=$2 AND b.stage='screening'
                  AND b.blocked_reason IS NULL AND NOT p.paused AND t.deleted_at IS NULL
            """,actor.workspace_id,tender_id)
            if budget_id is None:
                raise DomainError(422,"USAGE_BUDGET_REQUIRED","An approved workspace policy and tender screening budget are required.")
            return budget_id

    async def _member(self, c, actor):
        roles = await c.fetchval("SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2 FOR SHARE",
                                actor.workspace_id,actor.user_id)
        if roles is None:
            raise DomainError(403,"FORBIDDEN","An active workspace membership is required.")
        return roles

    async def _active(self, c, budget, actor, limits, roles):
        if budget["tender_id"] is None:
            if limits.job_id or limits.assistant_run_id or limits.source_index_version_id:
                raise DomainError(409,"BUDGET_SCOPE_MISMATCH","A tender call requires its tender budget.")
            return
        tender = await c.fetchrow("SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 AND deleted_at IS NULL FOR SHARE",
                                  actor.workspace_id,budget["tender_id"])
        if tender is None:
            raise DomainError(404,"NOT_FOUND","Tender not found.")
        if limits.source_index_version_id:
            if not set(roles)&{"member","admin"}:
                raise DomainError(403,"FORBIDDEN","Paid screening classification requires an active bid owner.")
            index=await c.fetchrow("SELECT tender_id,input_revision FROM m1_app.source_index_versions WHERE workspace_id=$1 AND id=$2",
                                   actor.workspace_id,limits.source_index_version_id)
            if index is None or index["tender_id"]!=budget["tender_id"]:
                raise DomainError(409,"BUDGET_SCOPE_MISMATCH","Source evidence must use its own tender budget.")
            if index["input_revision"]!=tender["input_revision"]:
                raise DomainError(409,"STALE_SOURCE_INDEX","Source evidence changed before dispatch.")
        if limits.job_id:
            job = await c.fetchrow("""
                SELECT * FROM m1_app.jobs
                WHERE workspace_id=$1 AND id=$2 AND tender_id=$3 AND created_by=$4 FOR UPDATE
            """,actor.workspace_id,limits.job_id,budget["tender_id"],actor.user_id)
            if not set(roles)&{"member","admin"}:
                raise DomainError(403,"FORBIDDEN","Analysis requires an active bid owner.")
            if job is None or job["status"] != "running" or job["deadline_at"] is None or job["deadline_at"] <= await c.fetchval("SELECT clock_timestamp()"):
                raise DomainError(409,"JOB_NOT_ACTIVE","The analysis job is no longer active.")
            if job["attempt"] != limits.expected_attempt:
                raise DomainError(409,"ATTEMPT_SUPERSEDED","A newer attempt owns this analysis job.")
            if job["input_revision"] != tender["input_revision"]:
                raise DomainError(409,"STALE_ANALYSIS","The pinned analysis is stale.")
        if limits.assistant_run_id:
            run = await c.fetchrow("""
                SELECT status,deadline_at FROM m1_app.assistant_runs
                WHERE workspace_id=$1 AND id=$2 AND tender_id=$3 AND actor_id=$4 FOR UPDATE
            """,actor.workspace_id,limits.assistant_run_id,budget["tender_id"],actor.user_id)
            if run is None or run["status"] != "running" or run["deadline_at"] <= await c.fetchval("SELECT clock_timestamp()"):
                raise DomainError(409,"ASSISTANT_NOT_ACTIVE","The assistant turn is no longer active.")

    async def reserve_call(self, budget_id, actor_scope, idempotency_key, maximum_cost, request_limits):
        actor,limits = actor_scope,request_limits
        price = self.price(limits.model)
        if (not maximum_cost.is_finite() or maximum_cost < price.maximum_cost(limits.input_tokens,limits.output_tokens)
                or not 1 <= len(idempotency_key) <= 256):
            raise DomainError(422,"INVALID_COST_RESERVATION","Reserve the complete worst-case request cost.")
        pinned_limits=limits.model_dump(mode="json")
        if limits.counted_input_tokens is None: pinned_limits.pop("counted_input_tokens")
        fingerprint = hashlib.sha256(json.dumps({
            "limits":pinned_limits,"maximum_cost":str(maximum_cost),
            "price":price.model_dump(mode="json"),"actor_id":str(actor.user_id),
        },sort_keys=True).encode()).hexdigest()
        async with self.pool.acquire() as c,c.transaction():
            roles = await self._member(c,actor)
            # One workspace lock serialises stage and daily accounting; no network under this lock.
            policy = await c.fetchrow("""
                SELECT * FROM m1_app.workspace_spending_policies WHERE workspace_id=$1 FOR UPDATE
            """,actor.workspace_id)
            budget = await c.fetchrow("SELECT * FROM m1_app.stage_budgets WHERE workspace_id=$1 AND id=$2 FOR UPDATE",
                                      actor.workspace_id,budget_id)
            if budget is None:
                raise DomainError(404,"NOT_FOUND","Budget not found.")
            previous = await c.fetchrow("SELECT * FROM m1_app.usage_reservations WHERE budget_id=$1 AND idempotency_key=$2",budget_id,idempotency_key)
            if previous:
                if previous["request_hash"] != fingerprint:
                    raise DomainError(409,"DUPLICATE_CONFLICT","This call identity was used with different content.")
                return receipt(previous)
            if policy is None or policy["paused"] or budget["blocked_reason"]:
                raise DomainError(422,"USAGE_BUDGET_REQUIRED","An active approved spending policy and stage budget are required.")
            await self._active(c,budget,actor,limits,roles)
            budget_day = await c.fetchval("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
            totals = await c.fetchrow("""
                SELECT coalesce(sum(coalesce(actual_cost,maximum_cost)),0) AS cost,
                       count(*) AS requests,count(*) FILTER(WHERE api='responses') AS responses,
                       coalesce(sum(coalesce(actual_input_tokens,max_input_tokens)),0) AS input_tokens
                FROM m1_app.usage_reservations WHERE budget_id=$1
            """,budget_id)
            checks = [
                (totals["cost"]+maximum_cost > budget["limit_usd"],"STAGE_BUDGET_EXHAUSTED"),
                (totals["requests"] >= budget["max_requests"],"STAGE_REQUEST_LIMIT"),
                (limits.api=="responses" and totals["responses"] >= budget["max_responses_requests"],"STAGE_RESPONSES_LIMIT"),
                (totals["input_tokens"]+limits.input_tokens > budget["max_input_tokens"],"STAGE_INPUT_LIMIT"),
            ]
            for exceeded,code in checks:
                if exceeded:
                    raise DomainError(422,code,"The approved cumulative stage limit is exhausted.")
            daily = await c.fetchval("""
                SELECT coalesce(sum(coalesce(actual_cost,maximum_cost)),0)
                FROM m1_app.usage_reservations WHERE workspace_id=$1 AND budget_day=$2
            """,actor.workspace_id,budget_day)
            if daily+maximum_cost > policy["daily_limit_usd"]:
                raise DomainError(422,"WORKSPACE_BUDGET_EXHAUSTED","The approved workspace daily limit is exhausted.")
            row = await c.fetchrow("""
                INSERT INTO m1_app.usage_reservations(workspace_id,budget_id,actor_id,idempotency_key,request_hash,
                    model,api,max_input_tokens,max_output_tokens,maximum_cost,price,budget_day,counted_input_tokens)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13) RETURNING *
            """,actor.workspace_id,budget_id,actor.user_id,idempotency_key,fingerprint,limits.model,limits.api,
                limits.input_tokens,limits.output_tokens,maximum_cost,price.model_dump_json(),budget_day,limits.counted_input_tokens)
            return receipt(row,True)

    async def settle_call(self, reservation, provider_usage, outcome):
        if outcome not in ("completed","rejected","unknown"):
            raise DomainError(422,"INVALID_USAGE_OUTCOME","A known completion, rejection or unknown outcome is required.")
        error = None
        async with self.pool.acquire() as c,c.transaction():
            await c.fetchrow("SELECT workspace_id FROM m1_app.workspace_spending_policies WHERE workspace_id=$1 FOR UPDATE",reservation["workspace_id"])
            row = await c.fetchrow("SELECT * FROM m1_app.usage_reservations WHERE workspace_id=$1 AND budget_id=$2 AND id=$3 FOR UPDATE",
                                   reservation["workspace_id"],reservation["budget_id"],reservation["id"])
            if row is None or row["actor_id"] != reservation["actor_id"]:
                raise DomainError(404,"NOT_FOUND","Reservation not found.")
            stored = json.loads(row["provider_usage"]) if row["provider_usage"] is not None else None
            if row["state"] == "settled":
                if row["outcome"] != outcome or stored != provider_usage:
                    raise DomainError(409,"DUPLICATE_CONFLICT","The reservation already has a different usage receipt.")
                return receipt(row)
            cost,input_tokens,output_tokens = None,None,None
            if outcome == "rejected":
                if provider_usage is not None:
                    raise DomainError(422,"PROVIDER_USAGE_INVALID","A billed response cannot be settled as an unbilled rejection.")
                cost,input_tokens,output_tokens = Decimal(0),0,0
            elif outcome == "completed":
                try:
                    input_tokens = provider_usage["input_tokens"]
                    output_tokens = provider_usage["output_tokens"]
                    cached = provider_usage.get("input_tokens_details",{}).get("cached_tokens",0)
                    writes = provider_usage.get("input_tokens_details",{}).get("cache_write_tokens",0)
                    if any(type(v) is not int or v < 0 for v in (input_tokens,output_tokens,cached,writes)) or cached+writes > input_tokens:
                        raise ValueError()
                    price = ModelPrice.model_validate_json(row["price"])
                    cost = price.cost(input_tokens,output_tokens,cached,writes)
                    if input_tokens > row["max_input_tokens"] or output_tokens > row["max_output_tokens"] or cost > row["maximum_cost"]:
                        error = "PROVIDER_USAGE_EXCEEDED"
                except (KeyError,TypeError,AttributeError,ValueError):
                    error = "PROVIDER_USAGE_INVALID"
            if error or outcome == "unknown":
                updated = await c.fetchrow("""
                    UPDATE m1_app.usage_reservations SET state='unknown',outcome='unknown',
                        provider_usage=coalesce($2::jsonb,provider_usage) WHERE id=$1 RETURNING *
                """,row["id"],json.dumps(provider_usage) if provider_usage is not None else None)
                if error == "PROVIDER_USAGE_EXCEEDED":
                    await c.execute("UPDATE m1_app.stage_budgets SET blocked_reason=$2 WHERE id=$1",row["budget_id"],error)
                    await c.execute("UPDATE m1_app.workspace_spending_policies SET paused=true WHERE workspace_id=$1",row["workspace_id"])
            else:
                updated = await c.fetchrow("""
                    UPDATE m1_app.usage_reservations SET state='settled',outcome=$2,actual_cost=$3,
                        actual_input_tokens=$4,actual_output_tokens=$5,provider_usage=$6::jsonb,settled_at=now()
                    WHERE id=$1 RETURNING *
                """,row["id"],outcome,cost,input_tokens,output_tokens,json.dumps(provider_usage))
        if error:
            raise DomainError(422,error,"Provider usage could not be reconciled; the full reservation remains held.")
        return receipt(updated)


    async def reconcile_call(self,actor,reservation_id,provider_response,authorized_cost,authorization_reference,reason,*,apply=False):
        """Operator-only repair of confirmed, bounded input-count drift; never dispatch or reopen spending."""
        if (not authorized_cost.is_finite() or authorized_cost<=0 or
            any(not isinstance(v,str) or not 1<=len(v.strip())<=2000 for v in (authorization_reference,reason))):
            raise DomainError(422,"INVALID_RECONCILIATION","Record the explicit authorization cap, reference and reason.")
        async with self.pool.acquire() as c,c.transaction():
            roles=await self._member(c,actor)
            if "admin" not in roles: raise DomainError(403,"FORBIDDEN","Usage reconciliation requires a current workspace admin.")
            found=await c.fetchrow("SELECT budget_id FROM m1_app.usage_reservations WHERE workspace_id=$1 AND id=$2",
                                   actor.workspace_id,reservation_id)
            if found is None: raise DomainError(404,"NOT_FOUND","Reservation not found.")
            policy=await c.fetchrow("SELECT * FROM m1_app.workspace_spending_policies WHERE workspace_id=$1 FOR UPDATE",actor.workspace_id)
            budget=await c.fetchrow("SELECT * FROM m1_app.stage_budgets WHERE workspace_id=$1 AND id=$2 FOR UPDATE",actor.workspace_id,found["budget_id"])
            row=await c.fetchrow("SELECT * FROM m1_app.usage_reservations WHERE workspace_id=$1 AND id=$2 FOR UPDATE",actor.workspace_id,reservation_id)
            audit=await c.fetchrow("SELECT * FROM m1_app.usage_reconciliations WHERE reservation_id=$1",row["id"])
            if audit:
                if (audit["actor_id"]!=actor.user_id or audit["authorized_cost"]!=authorized_cost or
                    audit["authorization_reference"]!=authorization_reference or audit["reason"]!=reason or
                    json.loads(audit["provider_response"])!=provider_response):
                    raise DomainError(409,"DUPLICATE_CONFLICT","The reservation already has a different reconciliation record.")
                return {"state":"settled","reservation_id":str(row["id"]),"reconciliation_id":str(audit["id"]),
                        "actual_cost_usd":str(row["actual_cost"])}
            try:
                stored=json.loads(row["provider_usage"]) if row["provider_usage"] else None
                usage=provider_response["usage"]
                confirmed={**usage,"response_id":provider_response["id"],"model":provider_response["model"]}
                if (row["api"]!="responses" or row["state"]!="unknown" or stored!=confirmed or
                    not provider_response["id"] or not provider_response["model"] or
                    provider_response["status"] not in {"completed","incomplete"}): raise ValueError()
                inputs,outputs=usage["input_tokens"],usage["output_tokens"]
                cached=usage.get("input_tokens_details",{}).get("cached_tokens",0)
                writes=usage.get("input_tokens_details",{}).get("cache_write_tokens",0)
                if any(type(v) is not int or v<0 for v in (inputs,outputs,cached,writes)) or cached+writes>inputs: raise ValueError()
                counted=row["counted_input_tokens"] if row["counted_input_tokens"] is not None else row["max_input_tokens"]
                if not row["max_input_tokens"]<inputs<=counted+INPUT_TOKEN_HEADROOM or outputs>row["max_output_tokens"]: raise ValueError()
                cost=ModelPrice.model_validate_json(row["price"]).cost(inputs,outputs,cached,writes)
                if cost>authorized_cost: raise ValueError()
            except (KeyError,TypeError,AttributeError,ValueError):
                raise DomainError(422,"RECONCILIATION_NOT_ALLOWED","Confirm the exact recorded terminal receipt, bounded input drift and sufficient authority; the reservation remains held.") from None
            totals=await c.fetchrow("""SELECT coalesce(sum(coalesce(actual_cost,maximum_cost)),0) AS cost,
                coalesce(sum(coalesce(actual_input_tokens,max_input_tokens)),0) AS tokens
                FROM m1_app.usage_reservations WHERE budget_id=$1 AND id<>$2""",row["budget_id"],row["id"])
            daily=await c.fetchval("""SELECT coalesce(sum(coalesce(actual_cost,maximum_cost)),0)
                FROM m1_app.usage_reservations WHERE workspace_id=$1 AND budget_day=$2 AND id<>$3""",
                actor.workspace_id,row["budget_day"],row["id"])
            if totals["cost"]+cost>budget["limit_usd"] or daily+cost>policy["daily_limit_usd"] or totals["tokens"]+inputs>budget["max_input_tokens"]:
                raise DomainError(422,"RECONCILIATION_BUDGET_EXCEEDED","The confirmed usage must fit the existing stage, daily and input limits.")
            result={"state":"preview","reservation_id":str(row["id"]),"actual_cost_usd":str(cost),
                    "original_maximum_cost_usd":str(row["maximum_cost"]),"input_token_difference":inputs-row["max_input_tokens"]}
            if not apply: return result
            audit_id=await c.fetchval("""INSERT INTO m1_app.usage_reconciliations(workspace_id,budget_id,reservation_id,
                actor_id,authorized_cost,authorization_reference,reason,original_reservation,provider_response,actual_cost)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10) RETURNING id""",
                actor.workspace_id,row["budget_id"],row["id"],actor.user_id,authorized_cost,authorization_reference,reason,
                json.dumps(dict(row),default=str),json.dumps(provider_response),cost)
            await c.execute("""UPDATE m1_app.usage_reservations SET state='settled',outcome='completed',actual_cost=$2,
                actual_input_tokens=$3,actual_output_tokens=$4,reconciliation_id=$5,settled_at=now() WHERE id=$1""",
                row["id"],cost,inputs,outputs,audit_id)
            return {**result,"state":"settled","reconciliation_id":str(audit_id)}


    async def summary(self,budget_id,actor):
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            await self._member(c,actor)
            budget=await c.fetchrow("SELECT * FROM m1_app.stage_budgets WHERE workspace_id=$1 AND id=$2",
                                   actor.workspace_id,UUID(str(budget_id)))
            if budget is None: raise DomainError(404,"NOT_FOUND","Budget not found.")
            rows=await c.fetch("SELECT id,state,actual_cost,maximum_cost FROM m1_app.usage_reservations WHERE workspace_id=$1 AND budget_id=$2",
                               actor.workspace_id,budget["id"])
            return {"budget_id":str(budget["id"]),"provider_requests":len(rows),
                "actual_cost_usd":str(sum((r["actual_cost"] or Decimal(0) for r in rows),Decimal(0))),
                "reserved_usd":str(sum((r["maximum_cost"] for r in rows if r["actual_cost"] is None),Decimal(0))),
                "limit_usd":str(budget["limit_usd"]),"blocked_reason":budget["blocked_reason"]}


@dataclass
class PaidCall:
    pool: object
    actor: ActorContext
    tender_id: UUID
    key: str
    job_id: UUID | None = None
    expected_attempt: int | None = None
    assistant_run_id: UUID | None = None
    source_index_version_id: UUID | None = None

    async def create_response(self, client, request, prices):
        ledger = UsageBudget(self.pool,prices)
        price = ledger.price(request["model"])
        budget_id = await ledger.tender_budget(self.actor,self.tender_id)
        # Count the exact payload, including schemas/tools, before reserving inference.
        count_args = {k:v for k,v in request.items() if k in (
            "model","instructions","input","text","tools","parallel_tool_calls","truncation")}
        count = await client.responses.input_tokens.count(**count_args)
        # Reserve bounded count drift up front; the existing cumulative limits still apply.
        limits = RequestLimits(model=request["model"],input_tokens=count.input_tokens+INPUT_TOKEN_HEADROOM,counted_input_tokens=count.input_tokens,
            output_tokens=request["max_output_tokens"],
            request_sha256=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
            job_id=self.job_id,expected_attempt=self.expected_attempt,assistant_run_id=self.assistant_run_id,source_index_version_id=self.source_index_version_id)
        reservation = await ledger.reserve_call(budget_id,self.actor,self.key,price.maximum_cost(limits.input_tokens,limits.output_tokens),limits)
        if not reservation["dispatch"]:
            raise DomainError(409,"MODEL_OUTCOME_UNKNOWN","This call was already reserved; replay cannot dispatch it again.")
        acknowledgement=None
        try:
            response = await client.responses.create(**request)
            if request.get("background"):
                # Persist the acknowledgement before waiting; the screening job bounds polling.
                response_id=response.id
                acknowledgement={"response_id":response_id,"model":response.model}
                await ledger.settle_call(reservation,acknowledgement,"unknown")
                while response.status in {"queued","in_progress"}:
                    await asyncio.sleep(1)
                    response=await client.responses.retrieve(response_id)
                    if response.id!=response_id:
                        raise DomainError(409,"MODEL_OUTCOME_UNKNOWN","The provider response identity changed; the reservation remains held.")
        except BaseException:
            # Cancellation, timeouts and transport errors never refund an uncertain dispatch.
            await ledger.settle_call(reservation,acknowledgement,"unknown")
            raise
        usage = {**(response.usage.model_dump() if response.usage else {}),
                 "response_id":response.id,"model":response.model}
        await ledger.settle_call(reservation,usage,"completed")
        return response
