"""Task 6: audit saved PUB evidence delivery. No model clients or paid calls."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


def audit_delivery(expectations, excerpts):
    items = []
    keys = ("source_index_version", "document_version_id", "anchor_id")
    for item in expectations:
        source = item["source"]
        delivered = any(
            all(e.get(k) == source[k] for k in keys)
            and source["quote"] and source["quote"] in e.get("quote", "")
            for e in excerpts
        )
        items.append({"id": item["id"], "critical_now": item["critical_now"],
                      "evidence_delivered": bool(delivered)})
    critical = [i for i in items if i["critical_now"]]
    delivered_critical = sum(i["evidence_delivered"] for i in critical)
    return {
        "expected_items": len(items),
        "delivered_items": sum(i["evidence_delivered"] for i in items),
        "expected_critical_items": len(critical),
        "delivered_critical_items": delivered_critical,
        "critical_evidence_delivery_rate": delivered_critical / len(critical) if critical else None,
        "model_critical_gate_recall": None, "model_accuracy": None,
        "unsupported_model_assertions": None, "items": items,
    }


class AuditPool:
    """Reuse one rollback-only transaction, including the app's SELECT row locks."""
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def run():
    from app.db import create_pool
    from app.m1.company_facts import CompanyFacts
    from app.m1.models import ActorContext
    from app.m1.policy import DomainError
    from app.m1.retrieval import SourceIndex
    from app.m1.screening_workflow import DEFAULT_QUERIES, ScreeningReasoner, _context, snapshot
    from app.m1.screening import screening_artifact

    manifest_path = ROOT / "evals/fixtures/development/PUB-screening/task-6-scenario.json"
    manifest = json.loads(manifest_path.read_text())
    scope = manifest["scope"]
    actor = ActorContext(user_id=UUID(scope["actor_id"]),
                         workspace_id=UUID(scope["workspace_id"]), roles=set())
    pool = await create_pool()
    try:
        async with pool.acquire() as c:
            transaction = c.transaction(isolation="repeatable_read")
            await transaction.start()
            try:
                before = {
                    table: await c.fetchval(
                        "SELECT count(*) FROM m1_app." + table + " WHERE workspace_id=$1",
                        actor.workspace_id)
                    for table in ("jobs", "artifact_versions", "review_tasks", "preparation_decisions",
                                  "usage_reservations", "document_versions")
                }
                audit_pool = AuditPool(c)
                tender, pins, documents, company, notice = await snapshot(
                    c, actor, UUID(scope["tender_id"]))
                index = await SourceIndex(audit_pool)._load(
                    c, scope["source_index_version"], actor)
                assert tender["input_revision"] == scope["input_revision"]
                assert str(index["parsed_sources_version_id"]) == scope["parsed_sources_version"]
                inventory = json.loads(index["inventory"])
                assert json.loads((ROOT / manifest["source_manifest"]).read_text())["inventory"] == inventory
                assert company and str(company["id"]) == scope["company_version_id"]
                for item in manifest["expectations"]:
                    await SourceIndex(audit_pool).validate_excerpt(actor, item["source"])

                async def saved_index(*args):
                    return {"id": index["id"]}

                cases = []
                # Freeze the existing native index: never reparse/reindex or save a job.
                with patch("app.m1.screening_workflow._native_index", saved_index):
                    for name, queries in [
                        ("default", list(DEFAULT_QUERIES)),
                        ("oracle_informed_diagnostic", manifest["diagnostic_queries"]),
                    ]:
                        job = {"id": uuid4(), "tender_id": tender["id"],
                               "input_revision": tender["input_revision"], "attempt": 0,
                               "manifest": json.dumps({
                                   **pins, "documents": documents, "queries": queries,
                                   "previous_screening_version_id": None,
                                   "affected_ids": None, "budget_id": None,
                               })}
                        started = asyncio.get_running_loop().time()
                        ctx = await _context(audit_pool, None, actor, job)
                        # A missing model stops after the real input-size guard, before any client/reservation.
                        reasoner = ScreeningReasoner(audit_pool, actor, job, {}, None)
                        try:
                            await reasoner.interpret(ctx, [])
                        except DomainError as error:
                            assert error.code == "MODEL_PRICING_MISSING", error.code
                        else:
                            raise AssertionError("The preflight must stop without a configured model.")
                        control = screening_artifact(ctx, {
                            "findings": [], "needs_wider_review": False,
                            "wider_review_reason": None,
                        }, {})
                        assert control["recommendation"] == "needs_information"
                        assert {"CRITICAL_COVERAGE_UNKNOWN", "CLOSING_UNKNOWN",
                                "FINDINGS_NOT_ESTABLISHED"} <= set(control["approval_blockers"])
                        cases.append({
                            "name": name, "queries": queries,
                            "latency_seconds": round(asyncio.get_running_loop().time() - started, 3),
                            "selected_excerpts": ctx["excerpts"], "coverage": ctx["coverage"],
                            "company_excerpts": ctx["company_excerpts"],
                            "company_gaps": ctx["company_gaps"],
                            "reasoner_preflight": "passed_input_limit_stopped_before_model_configuration",
                            "delivery": audit_delivery(manifest["expectations"], ctx["excerpts"]),
                            "controlled_empty_interpretation": {
                                "model_generated": False,
                                "recommendation": control["recommendation"],
                                "approval_blockers": control["approval_blockers"],
                                "request_drafts": control["request_drafts"],
                            },
                        })
                membership = await c.fetch("SELECT user_id,roles FROM m1_app.memberships WHERE workspace_id=$1",
                                           actor.workspace_id)
                policy_count = await c.fetchval(
                    "SELECT count(*) FROM m1_app.workspace_spending_policies WHERE workspace_id=$1", actor.workspace_id)
                budget_count = await c.fetchval(
                    "SELECT count(*) FROM m1_app.stage_budgets WHERE workspace_id=$1", actor.workspace_id)
                anchor_count = await c.fetchval("""
                    SELECT coalesce(sum(e.anchor_count),0) FROM m1_app.source_index_documents d
                    JOIN m1_app.source_extractions e ON e.workspace_id=d.workspace_id AND e.id=d.extraction_id
                    WHERE d.workspace_id=$1 AND d.index_id=$2
                """, actor.workspace_id, index["id"])
                company_fact = await CompanyFacts(audit_pool).lookup_company_facts(
                    {"query": "registration", "entity": "CBM Pte. Ltd.",
                     "as_of": datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()},
                    company["id"], actor)
            finally:
                await transaction.rollback()
            after = {
                table: await c.fetchval(
                    "SELECT count(*) FROM m1_app." + table + " WHERE workspace_id=$1",
                    actor.workspace_id)
                for table in before
            }
            assert before == after, "Workspace row counts changed during the audit."
    finally:
        await pool.close()

    return {
        "schema_version": "pub-source-audit.v1",
        "observed_at": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "evidence_level": "source-grounded agent development audit, not independent UAT",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "scope": scope, "provider_requests": 0, "actual_model_cost_usd": "0",
        "database_transaction": "rolled_back", "workspace_row_counts_before": before,
        "workspace_row_counts_after": after, "business_records_written": 0,
        "sources_reuploaded": 0, "sources_reparsed": 0,
        "source_count": len(inventory), "native_anchor_count": anchor_count,
        "source_status_counts": {s: sum(d["status"] == s for d in inventory)
                                 for s in sorted({d["status"] for d in inventory})},
        "memberships": [{"user_id": str(m["user_id"]), "roles": list(m["roles"])} for m in membership],
        "customer_delegations_verified": False, "independent_reviewer": None,
        "spending_policy_count": policy_count, "stage_budget_count": budget_count,
        "accepted_company_lookup": company_fact, "cases": cases,
        "manual_active_minutes": None, "assisted_active_minutes": None,
        "human_effort_saving": None, "representative_user_acceptance": None,
        "decision": "improve_narrow_m1a_before_pilot",
        "task_6_complete": False,
        "limitations": [
            "Provisional agent-authored oracle on known development material; not a blind or complete tender answer key.",
            "Evidence delivery measures exact source spans supplied to the reasoner, not extraction or interpretation quality.",
            "Diagnostic queries were chosen after reading the sources and do not improve the default app policy.",
            "The native indexing step alone was replaced with the existing saved index; actual context/retrieval/Company code ran.",
            "No live model output, independent human baseline, confirmed customer delegation or productivity outcome.",
            "All app reads ran in one rolled-back transaction; row-count equality is a limited concurrent-change check.",
        ],
        "code_sha256": {
            f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
            for f in ("apps/api/app/m1/retrieval.py", "apps/api/app/m1/screening_workflow.py",
                      "apps/api/app/m1/company_facts.py", "evals/run_pub_source_audit.py")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "decision": result["decision"], "provider_requests": result["provider_requests"],
        "source_count": result["source_count"],
        "cases": [{"name": c["name"], "excerpts": len(c["selected_excerpts"]),
                   "delivery": {k: v for k, v in c["delivery"].items() if k != "items"}}
                  for c in result["cases"]],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
