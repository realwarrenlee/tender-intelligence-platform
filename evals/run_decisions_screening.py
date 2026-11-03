"""Offline by default. Live evaluation needs human labels and an existing approved budget."""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/api"))

from app.tenders.policy import DomainError


def label_status(manifest):
    examples=manifest.get("examples",[])
    questions=manifest.get("questions",[])
    if not examples or not questions:
        return "awaiting_human_labels"
    for item in examples:
        labels=item.get("labels")
        if not item.get("reviewer") or not item.get("family_reviewed") or not isinstance(labels,dict):
            return "awaiting_human_labels"
        if set(labels)!={q["name"] for q in questions} or any(labels[q["name"]] not in q["choices"] for q in questions):
            return "awaiting_human_labels"
    development=[x for x in examples if x.get("split")=="development"]
    held=[x for x in examples if x.get("split")=="held_out"]
    if len(development)!=24 or len(held)!=24 or len({x["id"] for x in examples})!=48:
        raise DomainError(422,"INVALID_BENCHMARK","Use 24 development and 24 held-out examples with unique IDs.")
    if {x["clause_family"] for x in development}&{x["clause_family"] for x in held}:
        raise DomainError(422,"BENCHMARK_LEAKAGE","Clause families must remain separate across evaluation splits.")
    for split in (development,held):
        if any(sum(x.get("stratum")==kind for x in split)<8 for kind in ("critical","benign_scored_delivery","ambiguous")):
            raise DomainError(422,"INVALID_BENCHMARK","Each split needs eight human-confirmed examples in each required stratum.")
    return "ready"


async def run_benchmark(manifest,live=False,budget_id=None,client=None):
    if live and budget_id is None:
        raise DomainError(422,"USAGE_BUDGET_REQUIRED","Live benchmarking requires a persisted, explicitly approved budget.")
    status=label_status(manifest)
    split_metrics={split:{"planned_examples":sum(x.get("split")==split for x in manifest.get("examples",[])),
        "evaluated_examples":0,"evaluated_answers":0,"correct_answers":0,"accuracy":None}
        for split in ("development","held_out")}
    result={"mode":"live" if live else "offline","status":status if status!="ready" else "ready_for_authorised_live_run",
            "examples":len(manifest.get("examples",[])),"provider_requests":0,"accuracy":None,
            "critical_gate_misses":0,"actual_cost_usd":"0","results":[],
            "split_metrics":split_metrics,"evaluation_complete":False,"receipt_scope":"manifest_cumulative"}
    if not live or status!="ready": return result
    if client is None:
        raise DomainError(422,"USAGE_BUDGET_REQUIRED","A scoped client and approved persisted budget are required.")
    async with client.pool.acquire() as c:
        budget=await c.fetchrow("""
            SELECT b.limit_usd,b.max_requests,p.paused FROM m1_app.stage_budgets b
            JOIN m1_app.workspace_spending_policies p ON p.workspace_id=b.workspace_id
            WHERE b.workspace_id=$1 AND b.id=$2 AND b.blocked_reason IS NULL
        """,client.actor.workspace_id,UUID(str(budget_id)))
    if budget is None or budget["paused"] or budget["limit_usd"]>Decimal("1") or budget["max_requests"]>60:
        raise DomainError(422,"BENCHMARK_BUDGET_INVALID","The approved benchmark budget must cap cumulative spend at US$1 and requests at 60.")
    identity=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    for example in manifest["examples"]:
        started=time.monotonic()
        try:
            answer=await client.classify_excerpt(example["source"],manifest["questions"],manifest["rubric_version"],
                budget_id,"benchmark:"+identity[:32]+":"+example["id"])
        except DomainError as error:
            result.update(status="stopped",error_code=error.code)
            result["results"].append({"id":example["id"],"split":example["split"],
                "error_code":error.code,"latency_seconds":round(time.monotonic()-started,3)})
            break
        result["provider_requests"]+=1
        predicted={x["name"]:x["label"] for x in answer["answers"]}
        metrics=split_metrics[example["split"]]
        metrics["evaluated_examples"]+=1
        for name,want in example["labels"].items():
            metrics["evaluated_answers"]+=1
            metrics["correct_answers"]+=predicted[name]==want
        metrics["accuracy"]=metrics["correct_answers"]/metrics["evaluated_answers"]
        missed=example["stratum"]=="critical" and predicted!=example["labels"]
        result["results"].append({"id":example["id"],"split":example["split"],"predicted":predicted,
            "latency_seconds":round(time.monotonic()-started,3),"usage_receipt":answer["usage_receipt"]})
        if missed:
            result.update(status="critical_gate_missed",critical_gate_misses=1)
            break
    else:
        result["status"]="completed"
    async with client.pool.acquire() as c:
        receipts=await c.fetch("""
            SELECT id,api,state,maximum_cost,actual_cost,provider_usage,idempotency_key
            FROM m1_app.usage_reservations WHERE workspace_id=$1 AND budget_id=$2 ORDER BY created_at,id
        """,client.actor.workspace_id,UUID(str(budget_id)))
    cumulative={"provider_requests":len(receipts),
        "actual_cost_usd":str(sum((r["actual_cost"] or Decimal(0) for r in receipts),Decimal(0))),
        "reserved_usd":str(sum((r["maximum_cost"] for r in receipts if r["actual_cost"] is None),Decimal(0)))}
    receipts=[r for r in receipts if r["idempotency_key"].startswith("benchmark:"+identity[:32]+":")]
    # Include this manifest's charged invalid answers and uncertain attempts.
    result.update(accuracy=split_metrics["held_out"]["accuracy"],
        evaluation_complete=sum(m["evaluated_examples"] for m in split_metrics.values())==len(manifest["examples"]),
        cumulative_budget=cumulative,provider_requests=len(receipts),
        actual_cost_usd=str(sum((r["actual_cost"] or Decimal(0) for r in receipts),Decimal(0))),
        reserved_usd=str(sum((r["maximum_cost"] for r in receipts if r["actual_cost"] is None),Decimal(0))),
        usage_receipts=[{**dict(r),"id":str(r["id"]),"maximum_cost":str(r["maximum_cost"]),
            "actual_cost":str(r["actual_cost"]) if r["actual_cost"] is not None else None,
            "provider_usage":json.loads(r["provider_usage"]) if r["provider_usage"] else None} for r in receipts])
    return result


async def execute(args,manifest):
    if not args.live or not args.budget_id:
        return await run_benchmark(manifest,live=args.live,budget_id=args.budget_id)
    # Labels are checked before loading credentials or opening a provider client.
    if label_status(manifest)!="ready":
        return await run_benchmark(manifest,live=True,budget_id=args.budget_id)
    if not args.actor_id or not args.workspace_id:
        raise DomainError(422,"FORBIDDEN","Live evaluation requires an explicit real actor and workspace scope.")
    from app.config import get_settings
    from app.db import create_pool
    from app.tenders.models import ActorContext
    from app.tenders.decisions_client import DecisionsClient
    pool=await create_pool()
    try:
        settings=get_settings()
        actor=ActorContext(user_id=UUID(args.actor_id),workspace_id=UUID(args.workspace_id),roles=set())
        client=DecisionsClient(pool,actor,settings.openai_decisions_model,settings.openai_prices)
        return await run_benchmark(manifest,live=True,budget_id=args.budget_id,client=client)
    finally:
        await pool.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=ROOT/"evals/fixtures/development/PUB-screening/manifest.json")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--budget-id")
    parser.add_argument("--actor-id")
    parser.add_argument("--workspace-id")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args(argv)
    try:
        manifest=json.loads(args.manifest.read_text())
        result=asyncio.run(execute(args,manifest))
    except DomainError as error:
        result={"status":"blocked","error_code":error.code,"provider_requests":0,"accuracy":None}
    value=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(value+"\n")
    print(value)
    return 2 if result["status"] in ("blocked","stopped","critical_gate_missed") or (args.live and result["status"]!="completed") else 0


if __name__=="__main__":
    raise SystemExit(main())
