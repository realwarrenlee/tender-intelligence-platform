"""Assemble a bounded draft from linked requirements and approved reusable wording."""
from datetime import date, datetime
from hashlib import sha256
import json
import re
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from docx import Document

from app.tenders.analysis_runtime import utc_now
from app.tenders.assessments import current_company
from app.tenders.documents import DOCX_MIME, docx_bytes
from app.tenders.models import Model
from app.tenders.policy import DomainError
from app.tenders.preparation import PreparationFinding, rows, status


class ReusableWording(Model):
    id: str
    entity: str
    text: str
    location: str


class ProposalRequirement(PreparationFinding):
    section: Literal["Delivery approach", "Qualifications and supporting evidence"]
    evidenced_failure: bool
    request_ref: str
    question: str


class ProposalView(Model):
    entity: str | None
    company_version_id: UUID | None
    company_filename: str | None
    wording: list[ReusableWording]
    requirements: list[ProposalRequirement]
    can_request_input: bool
    saved_selections: dict[str, str] | None = None


def reusable_wording(company, pinned_company_id, as_of, required_on, *, entity=None):
    if not company or str(company["id"]) != pinned_company_id:
        return []
    payload = json.loads(company["payload"])
    if (date.fromisoformat(payload["effective_on"]) > as_of or
        payload.get("expires_on") and date.fromisoformat(payload["expires_on"]) < max(as_of, required_on)):
        return []
    options = {}
    for anchor in payload["parsed"]["anchors"]:
        for line in anchor["text"].splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3 or parts[0].strip() != "Proposal reuse":
                continue
            owner, wording = (part.strip() for part in parts[1:])
            if (entity is not None and owner != entity) or not 0 < len(owner) <= 200 or not 0 < len(wording) <= 1000:
                continue
            identifier = sha256(json.dumps([str(company["id"]), anchor["anchor_id"], line]).encode()).hexdigest()
            location = anchor.get("location_label") or f"Source anchor {anchor['anchor_id']}"
            options[identifier] = ReusableWording(id=identifier, entity=owner, text=wording, location=location)
            if len(options) == 30:
                return list(options.values())
    return list(options.values())


def input_question(finding):
    return f"Provide current evidence or approved response wording for this proposal requirement: {finding['statement']}"


async def proposal_request_draft(repo, c, actor, tender_id, screening_id, payload, ref):
    from app.tenders.preparation import current_approval
    from app.tenders.workspace_views import _review_rows, _review_view

    item = next((item for item in await rows(c, actor.workspace_id, [tender_id])
                 if item["kind"] == "technical_response"), None)
    if item is None or item["screening_version_id"] != screening_id:
        return None
    review_rows = await _review_rows(repo, c, actor, tender_id=tender_id, limit=1)
    if status(item, current_approval(_review_view(review_rows[0], actor, []))) == "non_current":
        return None
    finding_id = ref.removeprefix("proposal:")
    if finding_id not in item["finding_ids"]:
        return None
    finding = next((f for f in payload["findings"] if f["id"] == finding_id), None)
    if finding is None:
        return None
    return {"draft_ref": ref, "purpose": "screening_input", "finding_ids": [finding_id],
            "question": input_question(finding)}


async def proposal_view(prep, c, actor, tender, review, item, can_request_input):
    if item["kind"] != "technical_response":
        raise DomainError(422, "PROPOSAL_WRONG_DELIVERABLE", "Use the Technical response for proposal drafting.")
    workspace, tender_id = actor.workspace_id, tender["id"]
    findings = await prep.findings(c, actor, tender_id, item["screening_version_id"])
    requirements = []
    for key in item["finding_ids"]:
        f = findings[key]
        requirements.append(ProposalRequirement(
            id=key, statement=f["statement"], citations=f["tender_citations"],
            section="Delivery approach" if f["kind"] in {"bid_artifact", "delivery_commitment"}
            else "Qualifications and supporting evidence",
            evidenced_failure=f["status"] == "evidenced_failure", request_ref=f"proposal:{key}",
            question=input_question(f)))
    company = await current_company(c, workspace)
    pinned = await c.fetchval("""SELECT manifest->>'company_version_id' FROM m1_app.artifact_versions
        WHERE workspace_id=$1 AND tender_id=$2 AND id=$3 AND kind='screening'""",
        workspace, tender_id, item["screening_version_id"])
    zone = ZoneInfo("Asia/Singapore")
    today = utc_now().astimezone(zone).date()
    deadline = datetime.fromisoformat(review["closing_at"]).astimezone(zone).date() if review["closing_at"] else today
    options = reusable_wording(company, pinned, today, deadline, entity=item["proposal_entity"]) if item["proposal_entity"] else []
    manifest = json.loads(item["proposal_manifest"] or "null")
    saved = manifest if manifest and manifest["plan_revision"] == item["plan_revision"] else None
    return ProposalView(
        entity=item["proposal_entity"],
        company_version_id=company["id"] if options else None,
        company_filename=json.loads(company["payload"])["document"]["filename"] if options else None,
        wording=options, requirements=requirements, can_request_input=can_request_input,
        saved_selections=saved["selections"] if saved else None,
    )


async def read(prep, actor, tender_id, item_id):
    async with prep.repo.pool.acquire() as c, c.transaction(isolation="repeatable_read"):
        tender, roles, review, approval = await prep.context(c, actor, tender_id)
        item = next((item for item in await rows(c, actor.workspace_id, [tender_id]) if item["id"] == item_id), None)
        if item is None:
            raise DomainError(404, "NOT_FOUND", "Deliverable not found.")
        can_request = (prep.enabled and status(item, approval) != "non_current"
                       and tender["owner_user_id"] == actor.user_id and bool(set(roles) & {"member", "admin"}))
        if status(item, approval) == "non_current":
            return ProposalView(entity=None, company_version_id=None, company_filename=None, wording=[],
                                requirements=[], can_request_input=False)
        return await proposal_view(prep, c, actor, tender, review, item, can_request)


def assemble(view, entity, selections):
    requirements = {row.id: row for row in view.requirements}
    options = {wording.id: wording for wording in view.wording if wording.entity == entity}
    if not requirements:
        raise DomainError(422, "PROPOSAL_NO_REQUIREMENTS", "Link at least one requirement to the technical response.")
    if any(key not in requirements or requirements[key].evidenced_failure or value not in options
           for key, value in selections.items()):
        raise DomainError(422, "INVALID_PROPOSAL_EVIDENCE",
                          "Choose current approved wording for the confirmed bidding entity and linked requirement.")
    return [(row, options.get(selections.get(row.id))) for row in view.requirements]


def draft_document(tender, item, view, entity, matrix):
    document = Document()

    def clean(text):
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)

    document.add_heading("Technical proposal draft", 0)
    document.add_paragraph(clean(tender["title"]))
    document.add_paragraph(clean(f"Bidding entity: {entity}"))
    document.add_paragraph(f"Tender {tender['id']} · Plan {item['plan_revision']} · Screening {item['screening_version_id']}")
    document.add_paragraph("Working draft for assigned review.")
    for section in dict.fromkeys(row.section for row, wording in matrix if wording):
        document.add_heading(section, 1)
        for row, wording in matrix:
            if row.section == section and wording:
                document.add_heading(clean(row.statement), 2)
                document.add_paragraph(clean(wording.text))
                document.add_paragraph(clean(
                    f"Company evidence: {view.company_filename} · {wording.location} · Version {view.company_version_id}"))
    document.add_heading("Requirement and evidence matrix", 1)
    for row, wording in matrix:
        document.add_heading(clean(f"{row.id} · {row.statement}"), 2)
        for citation in row.citations:
            document.add_paragraph(clean(f"Tender source {citation.anchor_id}: {citation.quote}"))
        if wording:
            document.add_paragraph(clean(f"Response: {wording.text}"))
        else:
            document.add_paragraph(clean(f"Input needed. {row.question}"))
    return docx_bytes(document)


async def generate(prep, c, actor, tender, review, item, command):
    view = await proposal_view(prep, c, actor, tender, review, item, False)
    if not view.entity:
        raise DomainError(422, "PROPOSAL_ENTITY_REQUIRED", "Confirm the bidding legal entity in the technical response plan.")
    if command.company_version_id != view.company_version_id:
        raise DomainError(409, "STALE_PROPOSAL_EVIDENCE", "Refresh the proposal matrix before generating a draft.")
    matrix = assemble(view, view.entity, command.selections)
    data = draft_document(tender, item, view, view.entity, matrix)
    manifest = {"plan_revision": item["plan_revision"], "entity": view.entity,
                "company_version_id": str(view.company_version_id) if view.company_version_id else None,
                "selections": command.selections, "missing_finding_ids": [row.id for row, wording in matrix if not wording]}
    return {"filename": "technical-proposal-draft.docx", "sha256": sha256(data).hexdigest(),
            "content_type": DOCX_MIME}, data, manifest
