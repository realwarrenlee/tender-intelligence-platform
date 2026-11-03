"""Human-owned bid production, separate from incoming evidence and screening."""
from datetime import datetime
import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.tenders.analysis_runtime import utc_now
from app.tenders.models import Citation, Model
from app.tenders.policy import DomainError

Kind = Literal["technical_response", "pricing_workbook"]
Status = Literal["draft", "in_review", "changes_requested", "accepted", "non_current"]
Action = Literal["upload", "draft_proposal", "request_review", "accept", "request_changes", "reconfirm", "update_plan"]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
FindingIds = Annotated[list[Annotated[str, Field(min_length=1, max_length=160)]], Field(max_length=30)]
ProposalEntity = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]

LABELS = {"technical_response": "Technical response", "pricing_workbook": "Pricing workbook"}
FORMATS = {"technical_response": {".docx", ".pdf"}, "pricing_workbook": {".xlsx"}}


class PreparationCommand(Model):
    client_request_id: str = Field(min_length=1, max_length=100)
    approval_id: UUID


class CreateDeliverable(PreparationCommand):
    kind: Kind
    owner_id: UUID
    reviewer_id: UUID
    due_at: AwareDatetime
    finding_ids: FindingIds = Field(default_factory=list)
    proposal_entity: ProposalEntity | None = Field(default=None, exclude_if=lambda value: value is None)


class VersionCommand(PreparationCommand):
    expected_revision: int = Field(ge=1)


class FileCommand(VersionCommand):
    filename: str
    sha256: str


class DraftProposal(VersionCommand):
    action: Literal["draft_proposal"]
    company_version_id: UUID | None
    selections: dict[str, Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]] = Field(max_length=30)


class UpdateDeliverablePlan(VersionCommand):
    action: Literal["reconfirm", "update_plan"]
    owner_id: UUID
    reviewer_id: UUID
    due_at: AwareDatetime
    finding_ids: FindingIds = Field(default_factory=list)
    proposal_entity: ProposalEntity | None = Field(default=None, exclude_if=lambda value: value is None)


class ReviewCommand(VersionCommand):
    action: Literal["request_review", "accept", "request_changes"]
    note: Note
    requirements_checked: bool | None = Field(default=None, exclude_if=lambda value: value is None)


class DeliverableReceipt(Model):
    id: UUID
    revision: int


class PreparationFile(Model):
    id: UUID
    version: int
    filename: str
    sha256: str
    actor_id: UUID
    created_at: datetime


class PreparationReview(Model):
    id: UUID
    approval_id: UUID
    file_id: UUID
    plan_revision: int
    requested_by: UUID
    reviewer_id: UUID
    scope: str
    outcome: Literal["accepted", "changes_requested"] | None
    reason: str | None
    created_at: datetime
    reviewed_at: datetime | None
    is_current: bool
    requirements_checked: bool


class PreparationFinding(Model):
    id: str
    statement: str
    citations: list[Citation]
    condition: str | None = None


class PreviousPreparationPlan(Model):
    revision: int
    screening_version_id: UUID
    owner_id: UUID
    reviewer_id: UUID
    due_at: datetime
    actor_id: UUID
    created_at: datetime
    findings: list[PreparationFinding]
    proposal_entity: str | None = None


class Deliverable(Model):
    id: UUID
    kind: Kind
    owner_id: UUID
    reviewer_id: UUID
    due_at: datetime
    revision: int
    plan_revision: int
    screening_version_id: UUID
    status: Status
    findings: list[PreparationFinding]
    files: list[PreparationFile]
    reviews: list[PreparationReview]
    previous_plans: list[PreviousPreparationPlan]
    permitted_actions: list[Action]
    proposal_issue: str | None = None
    proposal_entity: str | None = None
    proposal_requires_confirmation: bool | None = None


class PreparationView(Model):
    approval_id: UUID | None
    scope: str | None
    can_create: bool
    items: list[Deliverable]


def current_approval(review):
    decision = review["preparation_decision"]
    return decision if decision and decision["is_current"] and decision["outcome"] == "approve_preparation" else None


def status(item, approval):
    if not approval or str(item["approval_id"]) != approval["id"]:
        return "non_current"
    return item["outcome"] or ("in_review" if item["review_id"] else "draft")


def proposal_issue(item):
    manifest = json.loads(item["proposal_manifest"]) if item["proposal_manifest"] else None
    if item["proposal_entity"] and item["file_id"] and not manifest:
        return "Generate a proposal for this plan before requesting review."
    if manifest and manifest["plan_revision"] != item["plan_revision"]:
        return "Generate a new proposal from the current plan before requesting review."
    if manifest and manifest["missing_finding_ids"]:
        return "Resolve the evidence gaps and generate a new proposal before requesting review."
    return None


PREPARATION_ROWS = """
        SELECT i.*,d.screening_version_id,f.id file_id,f.version,f.filename,f.sha256,f.proposal_manifest,r.id review_id,r.outcome,r.requirements_checked
        FROM m1_app.preparation_items i
        JOIN m1_app.preparation_decisions d ON d.workspace_id=i.workspace_id AND d.id=i.approval_id
        LEFT JOIN LATERAL (SELECT id,version,filename,sha256,proposal_manifest FROM m1_app.preparation_files
            WHERE workspace_id=i.workspace_id AND item_id=i.id ORDER BY version DESC LIMIT 1) f ON true
        LEFT JOIN m1_app.preparation_reviews r ON r.workspace_id=i.workspace_id AND r.item_id=i.id
            AND r.file_id=f.id AND r.plan_revision=i.plan_revision
"""


async def rows(c, workspace, tender_ids):
    return await c.fetch(PREPARATION_ROWS + """
        WHERE i.workspace_id=$1 AND i.tender_id=ANY($2::uuid[]) ORDER BY i.created_at,i.id
    """, workspace, tender_ids)


async def inbox_rows(c, actor, cursor, limit):
    return await c.fetch(f"""
        SELECT i.*,plan.reconfirm FROM ({PREPARATION_ROWS}) i
        JOIN m1_app.tenders t ON t.workspace_id=i.workspace_id AND t.id=i.tender_id
        LEFT JOIN LATERAL (SELECT d.id<>i.approval_id AND d.outcome='approve_preparation' reconfirm
            FROM m1_app.preparation_decisions d WHERE d.workspace_id=i.workspace_id AND d.tender_id=i.tender_id
            ORDER BY d.created_at DESC,d.id DESC LIMIT 1) plan ON true
        WHERE i.workspace_id=$1 AND t.deleted_at IS NULL
        AND (CASE WHEN plan.reconfirm THEN t.owner_user_id=$2 ELSE
            (i.owner_id=$2 AND (i.review_id IS NULL OR i.outcome='changes_requested'))
            OR (i.reviewer_id=$2 AND i.review_id IS NOT NULL AND i.outcome IS NULL) END)
        AND ($3::timestamptz IS NULL OR (i.created_at,i.id)>($3,$4))
        ORDER BY i.created_at,i.id LIMIT $5
    """, actor.workspace_id, actor.user_id, cursor["created_at"] if cursor else None,
        cursor["id"] if cursor else None, limit)


class Preparation:
    def __init__(self, repository, storage, enabled):
        self.repo = repository
        self.storage = storage
        self.enabled = enabled

    async def context(self, c, actor, tender_id, write=False, *, check_closing=True):
        from app.tenders.workspace_views import _review_rows, _review_view

        await self.repo._member(c, actor, "member" if write else None)
        if write and not self.enabled:
            raise DomainError(409, "PREPARATION_DISABLED", "Preparation tracking is read-only.")
        if write:
            # Match screening's workspace-before-tender lock order.
            await c.fetchval("SELECT id FROM m1_app.workspaces WHERE id=$1 FOR SHARE", actor.workspace_id)
        tender = await self.repo._tender(c, actor, tender_id, write)
        roles = await c.fetchval("SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2",
                                 actor.workspace_id, actor.user_id)
        review = _review_view((await _review_rows(self.repo, c, actor, tender_id=tender_id, limit=1))[0],
                              actor, roles, check_closing=check_closing)
        return tender, roles, review, current_approval(review)

    async def findings(self, c, actor, tender_id, screening_id):
        payload = await c.fetchval("""SELECT payload->'findings' FROM m1_app.artifact_versions
            WHERE workspace_id=$1 AND tender_id=$2 AND id=$3 AND kind='screening'""",
            actor.workspace_id, tender_id, screening_id)
        return {f["id"]: f for f in json.loads(payload or "[]")}

    async def linked_findings(self, c, actor, tender_id, plan, conditions=None):
        findings = await self.findings(c, actor, tender_id, plan["screening_version_id"])
        return [{"id": key, "statement": findings[key]["statement"], "citations": findings[key]["tender_citations"],
                 "condition": (conditions or {}).get(key)}
                for key in plan["finding_ids"] if key in findings]

    async def save_plan(self, c, actor, item_id):
        await c.execute("""INSERT INTO m1_app.preparation_plans
            (workspace_id,item_id,revision,approval_id,owner_id,reviewer_id,due_at,finding_ids,actor_id,proposal_entity)
            SELECT workspace_id,id,plan_revision,approval_id,owner_id,reviewer_id,due_at,finding_ids,$3,proposal_entity
            FROM m1_app.preparation_items WHERE workspace_id=$1 AND id=$2""", actor.workspace_id, item_id, actor.user_id)

    async def validate_plan(self, c, actor, tender_id, command, approval, review):
        if not utc_now() < command.due_at < datetime.fromisoformat(review["closing_at"]):
            raise DomainError(422, "INVALID_PREPARATION_DUE", "Set an internal due time before tender closing.")
        findings = await self.findings(c, actor, tender_id, UUID(approval["screening_version_id"]))
        if not set(command.finding_ids) <= findings.keys():
            raise DomainError(422, "INVALID_PREPARATION_FINDING", "Choose requirements from the approved screening.")

    async def check_assignees(self, c, actor, owner, reviewer):
        members = await c.fetch("""SELECT user_id FROM m1_app.memberships
            WHERE workspace_id=$1 AND user_id=ANY($2::uuid[]) AND roles && ARRAY['member','admin'] FOR SHARE""",
            actor.workspace_id, [owner, reviewer])
        if len(members) != 2:
            raise DomainError(422, "INVALID_PREPARATION_ASSIGNEES", "Choose a deliverable owner and a different workspace reviewer.")

    @staticmethod
    def require_approval(command, approval):
        if not approval or str(command.approval_id) != approval["id"]:
            raise DomainError(409, "PREPARATION_APPROVAL_REQUIRED", "A current preparation approval is required.")

    async def read(self, actor, tender_id):
        async with self.repo.pool.acquire() as c, c.transaction(isolation="repeatable_read"):
            tender, roles, _, approval = await self.context(c, actor, tender_id)
            items = []
            writable = self.enabled and bool(approval) and bool(set(roles) & {"member", "admin"})
            conditions = {entry["finding_id"]: entry["condition"] for entry in approval["conditions"]} if approval else {}
            for item in await rows(c, actor.workspace_id, [tender_id]):
                state = status(item, approval)
                issue = proposal_issue(item)
                actions = []
                if writable and tender["owner_user_id"] == actor.user_id:
                    actions.append("reconfirm" if state == "non_current" else "update_plan")
                if writable and state != "non_current" and item["owner_id"] == actor.user_id:
                    actions.append("draft_proposal" if item["proposal_entity"] else "upload")
                    if item["file_id"] and state == "draft" and not issue:
                        actions.append("request_review")
                if writable and state == "in_review" and item["reviewer_id"] == actor.user_id:
                    actions.extend(["accept", "request_changes"])
                files = await c.fetch("""SELECT id,version,filename,sha256,actor_id,created_at FROM m1_app.preparation_files
                    WHERE workspace_id=$1 AND item_id=$2 ORDER BY version DESC""", actor.workspace_id, item["id"])
                reviews = await c.fetch("""SELECT id,approval_id,file_id,plan_revision,requested_by,reviewer_id,scope,outcome,reason,created_at,reviewed_at,requirements_checked
                    FROM m1_app.preparation_reviews WHERE workspace_id=$1 AND item_id=$2 ORDER BY created_at DESC,id DESC""",
                    actor.workspace_id, item["id"])
                plans = await c.fetch("""SELECT p.revision,d.screening_version_id,p.owner_id,p.reviewer_id,p.due_at,
                    p.actor_id,p.created_at,p.finding_ids,p.proposal_entity FROM m1_app.preparation_plans p
                    JOIN m1_app.preparation_decisions d ON d.workspace_id=p.workspace_id AND d.id=p.approval_id
                    WHERE p.workspace_id=$1 AND p.item_id=$2 AND p.revision<>$3 ORDER BY p.revision DESC""",
                    actor.workspace_id, item["id"], item["plan_revision"])
                items.append(Deliverable(
                    **{k: item[k] for k in ("id", "kind", "owner_id", "reviewer_id", "due_at", "revision", "plan_revision", "screening_version_id")},
                    status=state, permitted_actions=actions, files=[dict(f) for f in files], proposal_issue=issue,
                    proposal_entity=item["proposal_entity"],
                    proposal_requires_confirmation=bool(item["proposal_manifest"]),
                    reviews=[{**dict(r), "is_current": state != "non_current" and r["id"] == item["review_id"]} for r in reviews],
                    findings=await self.linked_findings(c, actor, tender_id, item,
                                                       conditions if state != "non_current" else None),
                    previous_plans=[PreviousPreparationPlan(
                        **{k: v for k, v in plan.items() if k != "finding_ids"},
                        findings=await self.linked_findings(c, actor, tender_id, plan)) for plan in plans]))
            return PreparationView(approval_id=approval["id"] if approval else None,
                scope=approval["preparation_scope"] if approval else None,
                can_create=writable and tender["owner_user_id"] == actor.user_id, items=items)

    async def create(self, actor, tender_id, command):
        operation = f"create_deliverable:{tender_id}"
        async with self.repo.pool.acquire() as c, c.transaction():
            tender, _, review, approval = await self.context(c, actor, tender_id, True)
            self.require_actor(actor, tender["owner_user_id"])
            replay = await self.repo._claim(c, actor, operation, command)
            if replay is not None:
                return replay
            self.require_approval(command, approval)
            await self.validate_plan(c, actor, tender_id, command, approval, review)
            await self.check_assignees(c, actor, command.owner_id, command.reviewer_id)
            item = await c.fetchrow("""INSERT INTO m1_app.preparation_items
                (workspace_id,tender_id,approval_id,kind,owner_id,reviewer_id,due_at,finding_ids,proposal_entity)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(workspace_id,tender_id,kind) DO NOTHING RETURNING id,revision""",
                actor.workspace_id, tender_id, command.approval_id, command.kind, command.owner_id,
                command.reviewer_id, command.due_at, list(dict.fromkeys(command.finding_ids)),
                (command.proposal_entity or None) if command.kind == "technical_response" else None)
            if item is None:
                raise DomainError(409, "DELIVERABLE_EXISTS", "This deliverable is already tracked.")
            await self.save_plan(c, actor, item["id"])
            return await self.repo._finish(c, actor, operation, command, {
                "id": str(item["id"]), "revision": item["revision"], "approval_id": str(command.approval_id),
                "kind": command.kind, "owner_id": str(command.owner_id), "reviewer_id": str(command.reviewer_id),
                "due_at": command.due_at.isoformat(), "finding_ids": command.finding_ids,
                "proposal_entity": command.proposal_entity if command.kind == "technical_response" else None})

    @staticmethod
    def require_actor(actor, user_id):
        if actor.user_id != user_id:
            raise DomainError(403, "FORBIDDEN", "Only the assigned person may take this preparation action.")

    async def change(self, actor, tender_id, item_id, command, file=None):
        action = "upload" if file else command.action
        operation = f"preparation_{action}:{item_id}"
        async with self.repo.pool.acquire() as c, c.transaction():
            tender, _, review, approval = await self.context(c, actor, tender_id, True)
            item = next((i for i in await rows(c, actor.workspace_id, [tender_id]) if i["id"] == item_id), None)
            if item is None:
                raise DomainError(404, "NOT_FOUND", "Deliverable not found.")
            assigned = (tender["owner_user_id"] if action in {"reconfirm", "update_plan"} else item["reviewer_id"]
                        if action in {"accept", "request_changes"} else item["owner_id"])
            self.require_actor(actor, assigned)
            replay = await self.repo._claim(c, actor, operation, command)
            if replay is not None:
                return replay
            self.require_approval(command, approval)
            if command.expected_revision != item["revision"]:
                raise DomainError(409, "STALE_DELIVERABLE", "Refresh the deliverable before changing it.")
            state = status(item, approval)
            if state == "non_current" and action != "reconfirm":
                raise DomainError(409, "STALE_DELIVERABLE", "The bid owner must reconfirm this deliverable.")
            result = {"id": str(item_id), "revision": item["revision"] + 1, "approval_id": str(command.approval_id)}
            if action == ("reconfirm" if state == "non_current" else "update_plan"):
                await self.validate_plan(c, actor, tender_id, command, approval, review)
                await self.check_assignees(c, actor, command.owner_id, command.reviewer_id)
                entity = item["proposal_entity"]
                if item["kind"] == "technical_response" and command.proposal_entity is not None:
                    entity = command.proposal_entity or None
                await c.execute("""UPDATE m1_app.preparation_items
                    SET approval_id=$3,due_at=$4,finding_ids=$5,owner_id=$6,reviewer_id=$7,plan_revision=revision+1,
                        proposal_entity=$8
                    WHERE workspace_id=$1 AND id=$2""", actor.workspace_id, item_id, command.approval_id,
                    command.due_at, list(dict.fromkeys(command.finding_ids)), command.owner_id, command.reviewer_id,
                    entity)
                await self.save_plan(c, actor, item_id)
                result.update(due_at=command.due_at.isoformat(), finding_ids=command.finding_ids,
                    owner_id=str(command.owner_id), reviewer_id=str(command.reviewer_id),
                    proposal_entity=entity)
            elif action in {"upload", "draft_proposal"}:
                manifest = None
                if action == "draft_proposal":
                    from app.tenders.proposal import generate
                    info, data, manifest = await generate(self, c, actor, tender, review, item, command)
                else:
                    info, data = file
                    if item["proposal_entity"]:
                        raise DomainError(422, "GENERATED_PROPOSAL_REQUIRED",
                                          "Generate the technical proposal from this plan and its current evidence.")
                    if await c.fetchval("""SELECT EXISTS(SELECT 1 FROM m1_app.preparation_files
                        WHERE workspace_id=$1 AND item_id=$2 AND sha256=$3 AND proposal_manifest IS NOT NULL)""",
                        actor.workspace_id, item_id, info["sha256"]):
                        raise DomainError(422, "PROPOSAL_ALREADY_SAVED", "Generate a new proposal for the current plan.")
                suffix = Path(info["filename"]).suffix.lower()
                if suffix not in FORMATS[item["kind"]]:
                    raise DomainError(422, "INVALID_DELIVERABLE_FORMAT", "Use PDF or DOCX for the technical response, XLSX for pricing.")
                key = f'{actor.workspace_id}/{tender_id}/preparation/{info["sha256"]}{suffix}'
                await self.storage.put(key, data, info["content_type"])
                saved = await c.fetchrow("""INSERT INTO m1_app.preparation_files
                    (workspace_id,item_id,version,filename,content_type,sha256,storage_key,actor_id,proposal_manifest)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb) RETURNING id,version,filename,sha256,actor_id,created_at""",
                    actor.workspace_id, item_id, (item["version"] or 0) + 1, info["filename"],
                    info["content_type"], info["sha256"], key, actor.user_id, json.dumps(manifest) if manifest else None)
                result = PreparationFile(**dict(saved)).model_dump(mode="json")
            elif action == "request_review" and state == "draft" and item["file_id"]:
                if issue := proposal_issue(item):
                    raise DomainError(409, "PROPOSAL_REVIEW_BLOCKED", issue)
                await self.check_assignees(c, actor, item["owner_id"], item["reviewer_id"])
                review_id = await c.fetchval("""INSERT INTO m1_app.preparation_reviews
                    (workspace_id,item_id,file_id,approval_id,plan_revision,requested_by,reviewer_id,scope)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""", actor.workspace_id, item_id,
                    item["file_id"], command.approval_id, item["plan_revision"], actor.user_id, item["reviewer_id"], command.note)
                result.update(review_id=str(review_id), file_id=str(item["file_id"]), scope=command.note)
            elif action in {"accept", "request_changes"} and state == "in_review":
                outcome = "accepted" if action == "accept" else "changes_requested"
                checked = bool(action == "accept" and command.requirements_checked and item["finding_ids"])
                if action == "accept" and item["proposal_manifest"] and not checked:
                    raise DomainError(422, "PROPOSAL_COVERAGE_REQUIRED",
                                      "Confirm that the draft addresses all linked requirements and approval conditions.")
                await c.execute("""UPDATE m1_app.preparation_reviews
                    SET outcome=$3,reason=$4,reviewed_at=clock_timestamp(),requirements_checked=$5
                    WHERE workspace_id=$1 AND id=$2""", actor.workspace_id, item["review_id"], outcome, command.note, checked)
                result.update(review_id=str(item["review_id"]), file_id=str(item["file_id"]), outcome=outcome,
                    reason=command.note, requirements_checked=checked)
            else:
                raise DomainError(409, "PREPARATION_ACTION_UNAVAILABLE", "This action does not apply to the current deliverable.")
            await c.execute("UPDATE m1_app.preparation_items SET revision=revision+1 WHERE workspace_id=$1 AND id=$2",
                            actor.workspace_id, item_id)
            return await self.repo._finish(c, actor, operation, command, result)

    async def download(self, actor, tender_id, item_id, file_id):
        async with self.repo.pool.acquire() as c, c.transaction(isolation="repeatable_read"):
            await self.repo._member(c, actor)
            await self.repo._tender(c, actor, tender_id)
            file = await c.fetchrow("""SELECT f.* FROM m1_app.preparation_files f JOIN m1_app.preparation_items i
                ON i.workspace_id=f.workspace_id AND i.id=f.item_id
                WHERE f.workspace_id=$1 AND i.tender_id=$2 AND f.item_id=$3 AND f.id=$4""",
                actor.workspace_id, tender_id, item_id, file_id)
            if not file:
                raise DomainError(404, "NOT_FOUND", "Working file not found.")
            return file, await self.storage.get(file["storage_key"])
