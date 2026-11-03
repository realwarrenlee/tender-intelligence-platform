from app.tenders.models import CompanyProfile
"""Response schemas shared with the generated browser contract."""
from datetime import datetime
from typing import Any,Literal
from uuid import UUID

from pydantic import BaseModel
from app.tenders.notice_sources import NoticeSnapshot
from app.tenders.models import ActorContext,TenderView,AnalysisCandidate,Requirement,ReviewDraft,Citation

JobStatus=Literal['queued','running','needs_input','failed','completed','cancelled','non_current']


class ActorView(ActorContext):
    schema_version:Literal['m1.v1']
    qualification_workflow_enabled:bool=False
    preparation_tracking_enabled:bool=False
    submission_control_enabled:bool|None=None


class MemberView(BaseModel):
    user_id:str
    display_name:str
    roles:list[str]


class MembersView(BaseModel):
    schema_version:Literal['m1.v1']
    items:list[MemberView]


class JobView(BaseModel):
    schema_version:Literal['m1.v1']
    id:str
    tender_id:str
    input_revision:int
    status:JobStatus
    attempt:int
    completed_stages:list[str]
    warnings:list[dict[str,Any]]
    error_code:str|None
    output_version_id:str|None


class RequirementRecord(BaseModel):
    id:str
    requirement:Requirement
    carried_forward:bool


class Blocker(BaseModel):
    code:str
    requirement_id:str|None


class Reconciliation(BaseModel):
    kind:str
    requirement_id:str|None=None
    fact_id:str|None=None
    resolved:bool
    previous_requirement:Requirement|None=None
    replacement_requirement_ids:list[str]=[]


class AssessmentView(BaseModel):
    schema_version:Literal['m1.v1']='m1.v1'
    id:str
    input_revision:int
    created_by:str
    is_current:bool
    candidate:AnalysisCandidate
    requirements:list[RequirementRecord]
    blockers:list[Blocker]
    reconciliation:list[Reconciliation]
    manual_corrections:list[dict[str,Any]]|None
    run:dict[str,Any]|None
    human_reason:str|None


class DecisionView(BaseModel):
    schema_version:Literal['m1.v1']
    id:str
    tender_id:str
    assessment_version_id:str
    actor_id:str
    input_revision:int
    decision:Literal['pursue','hold','decline']
    reason:str
    review_complete:bool
    created_at:str
    manifest:dict[str,Any]
    is_current:bool
    currency_reason:str|None


class TaskAnswer(BaseModel):
    id:str
    evidence_version_id:str
    actor_id:str
    created_at:str
    response_kind:Literal['confirmed','denied','unable_to_confirm']
    text:str
    basis:str|None
    reassessment_job_id:str
    reassessment_status:JobStatus


class ReviewTaskView(BaseModel):
    schema_version:Literal['m1.v1']
    id:str
    tender_id:str
    assessment_version_id:str
    assignee_id:str
    created_by:str
    draft_ref:str
    requirement_ids:list[str]
    purpose:str
    question:str
    status:Literal['open','answered','cancelled']
    revision:int
    due_at:str
    created_at:str
    manifest:dict[str,Any]
    is_current:bool
    answer:TaskAnswer|None=None


class DocumentView(BaseModel):
    id:UUID
    filename:str
    sha256:str
    role:Literal['tender','addendum','reference_note','company_evidence']
    content_type:str|None
    byte_size:int
    page_count:int
    amends_version_id:UUID|None
    created_at:datetime


class SourceCoverage(BaseModel):
    complete:bool
    documents:list[dict[str,Any]]
    total_files:int
    parsed_files:int
    pending_files:int
    issues:int


class TenderOpportunity(BaseModel):
    suggestion_id:str
    notice_version_id:str
    notice_version:int
    notice:dict[str,Any]


class TenderDetail(TenderView):
    workflow:Literal['legacy','screening']='legacy'
    documents:list[DocumentView]
    source_set_version_id:str|None
    assessment:AssessmentView|None
    assessment_status:Literal['current','non_current','not_ready']
    review_tasks:list[ReviewTaskView]
    decision:DecisionView|None
    jobs:list[JobView]
    source_coverage:SourceCoverage|None=None
    opportunity:TenderOpportunity|None=None


class InboxItem(TenderView):
    buyer:str|None
    closing_at:str|None
    recommendation:Literal['pursue','hold','decline']|None
    assessment_status:Literal['current','non_current','not_ready']
    decision:DecisionView|None
    next_action:str


class InboxView(BaseModel):
    schema_version:Literal['m1.v1']
    items:list[InboxItem]


class SourceAnchor(BaseModel):
    anchor_id:str
    document_version_id:str
    source_role:str
    text:str
    page:int|None=None
    paragraph:int|None=None
    location_label:str|None=None
    actor_id:str|None=None
    answer_id:str|None=None
    question:str|None=None
    response_kind:str|None=None
    basis:str|None=None
    assessment_version_id:str|None=None
    requirement_ids:list[str]|None=None
    source_manifest:dict[str,Any]|None=None


class SourcesView(BaseModel):
    schema_version:Literal['m1.v1']
    assessment_version_id:str
    anchors:list[SourceAnchor]


class AssessmentHistory(BaseModel):
    id:str
    input_revision:int
    created_at:str
    created_by:str
    is_current:bool


class HistoryView(BaseModel):
    schema_version:Literal['m1.v1']
    assessments:list[AssessmentHistory]
    decisions:list[DecisionView]


class CompanyVersion(BaseModel):
    id:str
    evidence_revision:int
    created_by:str
    effective_on:str
    expires_on:str|None
    reason:str
    filename:str
    created_at:str
    profile:CompanyProfile|None=None
    reference_text:str|None=None


class CompanyView(BaseModel):
    schema_version:Literal['m1.v1']
    evidence_revision:int
    current:CompanyVersion|None
    history:list[CompanyVersion]=[]


class AssistantView(BaseModel):
    schema_version:Literal['m1.v1']
    answer:str
    citations:list[Citation]
    review_request_drafts:list[ReviewDraft]
    out_of_scope:bool
    run:dict[str,Any]
    run_id:str
    assessment_version_id:str
    is_current:bool




class OpportunityView(BaseModel):
    schema_version:Literal["m1.opportunity.v1"]
    id:str
    revision:int
    source_identity:str
    intake_owner_user_id:str
    state:Literal["suggested","deferred","dismissed","activated"]
    notice_version_id:str
    notice_version:int
    notice:NoticeSnapshot
    match:dict[str,Any]
    tender_id:str|None
    budget_id:str|None
    budget_status:Literal["not_approved","available","blocked"]
    created_at:datetime
    last_checked_at:datetime


class OpportunitiesView(BaseModel):
    schema_version:Literal["m1.opportunity.v1"]
    items:list[OpportunityView]
    next_cursor:str|None


class OpportunityFeedbackView(BaseModel):
    id:str
    sender_id:str
    recipient_id:str
    question:str
    answer:str|None
    created_at:datetime
    answered_at:datetime|None
    notice:NoticeSnapshot


class OpportunityFeedbackList(BaseModel):
    items:list[OpportunityFeedbackView]
    next_cursor:str|None


class OpportunityDiscoveryView(BaseModel):
    configured:bool
    enabled:bool
    can_edit:bool


from app.tenders.screening import ScreeningArtifact
from app.tenders.models import PreparationBudget,PreparationCondition


class ScreeningView(BaseModel):
    id:str
    input_revision:int
    is_current:bool
    artifact:ScreeningArtifact


class PreparationDecisionView(BaseModel):
    id:str
    screening_version_id:str
    approval_task_id:str
    actor_id:str
    outcome:Literal["approve_preparation","request_information","decline"]
    reason:str
    preparation_scope:str|None
    preparation_budget:PreparationBudget|None
    conditions:list[PreparationCondition]
    created_at:str
    is_current:bool
    currency_reason:str|None


class PreparationProgress(BaseModel):
    total: int
    accepted: int
    pending_reviews: int
    non_current: int


class OversightAction(BaseModel):
    label: str
    assignee_id: str | None
    due_at: str | None
    section: Literal["assessment", "questions", "preparation"]
    task_id: str | None = None


class ReviewCaseView(BaseModel):
    schema_version:Literal["qualification.v1"]
    tender_id:str
    title:str
    owner_user_id:str
    input_revision:int
    evidence_revision:int
    screening_version_id:str|None
    screening_is_current:bool
    state:Literal["In progress","Waiting for input","Ready for decision","Completed","Needs reassessment"]
    tender_stage:Literal["assessing","preparing_bid","closed"]
    next_actor_id:str|None
    open_inputs:int
    open_approvals:int
    recommendation:Literal["promising","outside_policy","needs_information"]|None
    attention:str|None
    closing_at:str|None
    job_status:JobStatus|None
    permitted_actions:list[str]
    preparation_decision:PreparationDecisionView|None
    screening:ScreeningView|None
    preparation:PreparationProgress|None=None
    submission_history:bool|None=None
    next_action:OversightAction|None=None


class ReviewCasesView(BaseModel):
    schema_version:Literal["qualification.v1"]
    items:list[ReviewCaseView]
    next_cursor:str|None


class InboxAction(BaseModel):
    task_id:str
    tender_id:str
    tab:Literal["human"]
    kind:Literal["screening_input","preparation_approval","information_request","preparation_deliverable","preparation_review","preparation_reconfirm"]
    screening_version_id:str
    question:str
    due_at:str
    task_revision:int
    is_current:bool
    can_act:bool


class InboxActionsView(BaseModel):
    schema_version:Literal["qualification.v1"]
    items:list[InboxAction]
    next_cursor:str|None
