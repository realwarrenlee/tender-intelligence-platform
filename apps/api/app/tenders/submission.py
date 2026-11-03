"""Release decisions and manual portal receipts pinned to immutable bid packages."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.tenders.analysis_runtime import utc_now
from app.tenders.models import Model
from app.tenders.policy import DomainError
from app.tenders.preparation import Kind, LABELS, Note, Preparation, rows, status
from app.tenders.screening import conditional_preparation

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Outcome = Literal["approved", "rejected"]
PackageState = Literal["awaiting_release", "approved", "rejected", "submitted", "closed", "non_current"]


class SubmissionCommand(Model):
    client_request_id: str = Field(min_length=1, max_length=100)


class SealPackage(SubmissionCommand):
    expected_snapshot: Digest
    previous_package_id: UUID | None
    approver_id: UUID


class DecideRelease(SubmissionCommand):
    outcome: Outcome
    note: Note
    checks_confirmed: bool = False


class RecordPortalReceipt(SubmissionCommand):
    portal_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    submitted_at: AwareDatetime


class PortalReceiptUpload(RecordPortalReceipt):
    filename: str
    sha256: Digest


class PackageId(Model):
    id: UUID


class ReleaseFile(Model):
    kind: Kind
    item_id: UUID
    file_id: UUID
    filename: str
    version: int
    sha256: Digest
    review_id: UUID
    reviewer_id: UUID
    plan_revision: int
    requirements_checked: bool


class ReleaseDecision(Model):
    outcome: Outcome
    actor_id: UUID
    note: str
    decided_at: datetime


class PortalReceipt(Model):
    portal_reference: str
    submitted_at: datetime
    recorded_by: UUID
    recorded_at: datetime
    filename: str
    sha256: Digest


class SubmissionPackage(Model):
    id: UUID
    version: int
    approver_id: UUID
    sealed_by: UUID
    sealed_at: datetime
    closing_at: datetime
    preparation_approval_id: UUID
    files: list[ReleaseFile]
    decision: ReleaseDecision | None
    receipt: PortalReceipt | None
    state: PackageState
    can_decide: bool
    can_record_receipt: bool


class ReleaseCheck(Model):
    label: str
    passed: bool


class SubmissionView(Model):
    snapshot: Digest | None
    candidate_files: list[ReleaseFile]
    checks: list[ReleaseCheck]
    can_seal: bool
    packages: list[SubmissionPackage]


def unresolved(finding, linked, conditions):
    if finding["status"] == "supported":
        return False
    if conditional_preparation(finding) and finding["id"] in conditions:
        return finding["preparation_role"] != "future_duty" and finding["id"] not in linked
    return (finding["status"] == "evidenced_failure" or finding["critical"]
            or finding["material_now"] is not False or finding["due_stage"] in {"submission", "unknown"})


class Submission:
    def __init__(self, preparation: Preparation, enabled: bool):
        self.prep = preparation
        self.repo = preparation.repo
        self.enabled = enabled

    async def readiness(self, c, actor, tender_id, review, approval):
        accepted = {item["kind"]: item for item in await rows(c, actor.workspace_id, [tender_id])
                    if status(item, approval) == "accepted"}
        files = [
            ReleaseFile(kind=kind, item_id=item["id"], **{key: item[key] for key in (
                "file_id", "filename", "version", "sha256", "review_id", "reviewer_id", "plan_revision", "requirements_checked"
            )}).model_dump(mode="json")
            for kind in LABELS if (item := accepted.get(kind))
        ]
        linked = {key for item in accepted.values() if item["requirements_checked"] for key in item["finding_ids"]}
        blockers = []
        if approval:
            conditions = {condition["finding_id"] for condition in approval["conditions"]}
            findings = await self.prep.findings(c, actor, tender_id, UUID(approval["screening_version_id"]))
            blockers = [f["statement"] for f in findings.values() if unresolved(f, linked, conditions)]
        checks = [
            ReleaseCheck(label="Current qualification evidence and preparation approval", passed=bool(approval)),
            ReleaseCheck(label="Qualification requests resolved", passed=review["open_inputs"] == 0),
            *[ReleaseCheck(label=f"Current {label.lower()} version accepted", passed=kind in accepted)
              for kind, label in LABELS.items()],
            *[ReleaseCheck(label=f"Resolve before release: {statement}", passed=False) for statement in blockers],
        ]
        snapshot = None
        if all(check.passed for check in checks):
            content = [approval["id"], review["closing_at"], files]
            snapshot = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        return snapshot, files, checks

    async def packages(self, c, actor, tender_id, *, latest_only=False):
        records = await c.fetch("""
            SELECT p.*, to_jsonb(d)-'workspace_id'-'package_id' decision,
                   to_jsonb(r)-'workspace_id'-'package_id'-'decision_outcome'-'storage_key' receipt
            FROM m1_app.submission_packages p
            LEFT JOIN m1_app.submission_decisions d ON d.workspace_id=p.workspace_id AND d.package_id=p.id
            LEFT JOIN m1_app.submission_receipts r ON r.workspace_id=p.workspace_id AND r.package_id=p.id
            WHERE p.workspace_id=$1 AND p.tender_id=$2 ORDER BY p.version DESC LIMIT $3
        """, actor.workspace_id, tender_id, 1 if latest_only else None)
        return [{**dict(p), **{key: json.loads(p[key]) if p[key] else None
                              for key in ("files", "decision", "receipt")}} for p in records]

    @staticmethod
    def state(package, current, before_close):
        if not current:
            return "non_current"
        if package["receipt"]:
            return "submitted"
        if package["decision"] and package["decision"]["outcome"] == "rejected":
            return "rejected"
        if not before_close:
            return "closed"
        return "approved" if package["decision"] else "awaiting_release"

    async def read(self, actor, tender_id):
        async with self.repo.pool.acquire() as c, c.transaction(isolation="repeatable_read"):
            tender, roles, review, approval = await self.prep.context(c, actor, tender_id, check_closing=False)
            snapshot, files, checks = await self.readiness(c, actor, tender_id, review, approval)
            records = await self.packages(c, actor, tender_id)
            before_close = bool(review["closing_at"] and utc_now() < datetime.fromisoformat(review["closing_at"]))
            checks.append(ReleaseCheck(label="Tender closing time has not passed", passed=before_close))
            writable = self.enabled and bool(set(roles) & {"member", "admin"})
            owner = actor.user_id == tender["owner_user_id"]
            packages = []
            for index, package in enumerate(records):
                current = index == 0 and package["snapshot"] == snapshot
                state = self.state(package, current, before_close)
                approved = package["decision"] and package["decision"]["outcome"] == "approved"
                packages.append(SubmissionPackage(
                    **{key: package[key] for key in SubmissionPackage.model_fields
                       if key in package}, state=state,
                    can_decide=writable and state == "awaiting_release" and actor.user_id == package["approver_id"],
                    can_record_receipt=bool(writable and current and owner and approved and not package["receipt"])))
            already_submitted = any(p["snapshot"] == snapshot and p["receipt"] for p in records)
            return SubmissionView(snapshot=snapshot, candidate_files=files, checks=checks, packages=packages,
                can_seal=bool(writable and owner and snapshot and before_close and not already_submitted))

    async def write(self, actor, tender_id, command, action, package_id=None, data=None):
        operation = f"submission_{action}:{tender_id}:{package_id or ''}"
        async with self.repo.pool.acquire() as c, c.transaction():
            tender, _, review, approval = await self.prep.context(c, actor, tender_id, True, check_closing=False)
            if not self.enabled:
                raise DomainError(409, "SUBMISSION_DISABLED", "Submission control is read-only.")
            if action != "decision":
                self.prep.require_actor(actor, tender["owner_user_id"])
            replay = await self.repo._claim(c, actor, operation, command)
            if replay is not None:
                return replay
            latest = next(iter(await self.packages(c, actor, tender_id, latest_only=True)), None)
            snapshot, files, _ = await self.readiness(c, actor, tender_id, review, approval)
            now = utc_now()
            closing = datetime.fromisoformat(review["closing_at"]) if review["closing_at"] else None
            if action == "seal":
                if snapshot != command.expected_snapshot or not closing or now >= closing:
                    raise DomainError(409, "PACKAGE_NOT_READY", "Refresh the release checks and resolve the outstanding requirements.")
                if command.previous_package_id != (latest["id"] if latest else None):
                    raise DomainError(409, "STALE_PACKAGE", "Refresh the submission packages before sealing.")
                if latest and latest["snapshot"] == snapshot and (
                    latest["receipt"] or (latest["approver_id"] == command.approver_id and
                    (not latest["decision"] or latest["decision"]["outcome"] == "approved"))
                ):
                    raise DomainError(409, "PACKAGE_EXISTS", "This package is already sealed.")
                await self.prep.check_assignees(c, actor, actor.user_id, command.approver_id)
                package_id = await c.fetchval("""
                    INSERT INTO m1_app.submission_packages(workspace_id,tender_id,version,preparation_approval_id,
                        approver_id,sealed_by,closing_at,snapshot,files)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id
                """, actor.workspace_id, tender_id, latest["version"] + 1 if latest else 1, UUID(approval["id"]),
                    command.approver_id, actor.user_id, closing, snapshot, json.dumps(files))
            else:
                if not latest or latest["id"] != package_id or latest["snapshot"] != snapshot:
                    raise DomainError(409, "STALE_PACKAGE", "Only the current package can be released or recorded.")
                if action == "decision":
                    self.prep.require_actor(actor, latest["approver_id"])
                    if latest["decision"] or now >= latest["closing_at"]:
                        raise DomainError(409, "RELEASE_UNAVAILABLE", "The package already has a decision or the tender has closed.")
                    if command.outcome == "approved" and not command.checks_confirmed:
                        raise DomainError(422, "CHECKS_REQUIRED", "Confirm the release checks for this exact package.")
                    await c.execute("""
                        INSERT INTO m1_app.submission_decisions(workspace_id,package_id,outcome,actor_id,note)
                        VALUES($1,$2,$3,$4,$5)
                    """, actor.workspace_id, package_id, command.outcome, actor.user_id, command.note)
                else:
                    decision = latest["decision"]
                    if not decision or decision["outcome"] != "approved" or latest["receipt"]:
                        raise DomainError(409, "RECEIPT_UNAVAILABLE", "Record a receipt once for an approved package.")
                    if not datetime.fromisoformat(decision["decided_at"]) <= command.submitted_at <= now or (
                        command.submitted_at > latest["closing_at"]
                    ):
                        raise DomainError(422, "INVALID_SUBMISSION_TIME", "Enter a portal time between release approval and tender closing.")
                    key = f"{actor.workspace_id}/{tender_id}/submission/{command.sha256}.pdf"
                    await self.prep.storage.put(key, data, "application/pdf")
                    await c.execute("""
                        INSERT INTO m1_app.submission_receipts(workspace_id,package_id,portal_reference,submitted_at,
                            recorded_by,filename,sha256,storage_key) VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                    """, actor.workspace_id, package_id, command.portal_reference, command.submitted_at,
                        actor.user_id, command.filename, command.sha256, key)
            return await self.repo._finish(c, actor, operation, command, {"id": str(package_id)})

    async def download(self, actor, tender_id, package_id):
        async with self.repo.pool.acquire() as c, c.transaction(isolation="repeatable_read"):
            await self.repo._member(c, actor)
            await self.repo._tender(c, actor, tender_id)
            receipt = await c.fetchrow("""
                SELECT r.filename,r.storage_key FROM m1_app.submission_receipts r
                JOIN m1_app.submission_packages p ON p.workspace_id=r.workspace_id AND p.id=r.package_id
                WHERE r.workspace_id=$1 AND p.tender_id=$2 AND r.package_id=$3
            """, actor.workspace_id, tender_id, package_id)
            if not receipt:
                raise DomainError(404, "NOT_FOUND", "Submission receipt not found.")
            return receipt["filename"], await self.prep.storage.get(receipt["storage_key"])
