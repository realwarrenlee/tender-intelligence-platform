from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.m1.documents import MAX_FILES,MAX_PAGES

from pydantic import HttpUrl, BaseModel, ConfigDict, Field,field_validator

Role = Literal["bid_owner", "service_reviewer", "approver", "admin", "viewer"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActorContext(Model):
    user_id: UUID
    workspace_id: UUID
    roles: set[Role]


class CreateTender(Model):
    title: str = Field(min_length=1, max_length=300)
    source_label: str = Field(default="manual_upload", min_length=1, max_length=100)
    client_request_id: str = Field(min_length=1, max_length=100)


class TenderView(Model):
    schema_version: Literal["m1.v1"] = "m1.v1"
    id: UUID
    workspace_id: UUID
    title: str
    source_label: str
    owner_user_id: UUID
    input_revision: int
    created_at: datetime


class SourceInput(Model):
    filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storage_key: str = Field(min_length=1, max_length=1000)
    role: Literal["tender", "addendum", "company_evidence", "reference_note"]
    content_type: str | None = None
    byte_size: int = Field(default=0,ge=0,le=20*1024*1024)
    page_count: int = Field(default=0,ge=0,le=MAX_PAGES)
    amends_version_id: UUID | None = None


class RegisterSources(Model):
    tender_id: UUID
    expected_input_revision: int
    client_request_id: str = Field(min_length=1, max_length=100)
    sources: list[SourceInput] = Field(min_length=1, max_length=MAX_FILES)


class RequestAnalysis(Model):
    expected_input_revision: int
    client_request_id: str = Field(min_length=1, max_length=100)


class UploadEntry(Model):
    role: Literal['tender','addendum','company_evidence','reference_note']
    amends_version_id: UUID | None = None


class UploadMetadata(RequestAnalysis):
    files: list[UploadEntry] = Field(min_length=1,max_length=MAX_FILES)


class RecordDecision(RequestAnalysis):
    assessment_version_id: UUID
    decision: Literal["pursue", "hold", "decline"]
    reason: str = Field(min_length=1, max_length=2000)
    review_complete: bool

    @field_validator('reason')
    @classmethod
    def nonblank_reason(cls,value):
        if not value.strip(): raise ValueError('A human reason is required.')
        return value


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)


class Citation(CandidateModel):
    anchor_id: str = Field(min_length=1,max_length=160)
    quote: str = Field(min_length=1,max_length=1000)


class TextFact(CandidateModel):
    value: str | None = Field(max_length=1500)
    citations: list[Citation] = Field(max_length=12)


class IntegerFact(CandidateModel):
    value: int | None = Field(ge=1,le=1200)
    citations: list[Citation] = Field(max_length=12)


class KeyFacts(CandidateModel):
    title: TextFact
    buyer: TextFact
    closing_at: TextFact
    service_start_on: TextFact
    term_months: IntegerFact


class Requirement(CandidateModel):
    local_ref: str = Field(min_length=1,max_length=80)
    text: str = Field(min_length=1,max_length=3000)
    kind: Literal['eligibility','delivery','submission','evaluation']
    mandatory: bool
    tender_citations: list[Citation] = Field(min_length=1,max_length=12)
    status: Literal['met','unmet','unconfirmed','not_assessed']
    company_citations: list[Citation] = Field(max_length=12)
    explanation: str = Field(min_length=1,max_length=2000)
    missing_information: str | None = Field(max_length=2000)


class Recommendation(CandidateModel):
    decision: Literal['pursue','hold','decline']
    reasons: list[str] = Field(min_length=1,max_length=8)
    condition_refs: list[str] = Field(max_length=1000)


class ReviewDraft(CandidateModel):
    draft_ref: str = Field(min_length=1,max_length=80)
    requirement_refs: list[str] = Field(min_length=1,max_length=20)
    suggested_role: str = Field(min_length=1,max_length=80)
    question: str = Field(min_length=1,max_length=1000)
    rationale: str = Field(min_length=1,max_length=1000)


class AnalysisWarning(CandidateModel):
    code: Literal['missing_fact','conflicting_dates','incomplete_source','unsupported_input','untrusted_instruction']
    message: str = Field(min_length=1,max_length=1500)
    citations: list[Citation] = Field(max_length=12)


class AnalysisCandidate(CandidateModel):
    summary: str = Field(min_length=1,max_length=1200)
    key_facts: KeyFacts
    requirements: list[Requirement] = Field(max_length=1000)
    recommendation: Recommendation
    review_requests: list[ReviewDraft] = Field(max_length=1000)
    warnings: list[AnalysisWarning] = Field(max_length=1000)


class AcceptCompanyEvidence(Model):
    expected_evidence_revision: int = Field(ge=0)
    client_request_id: str = Field(min_length=1,max_length=100)
    accept: Literal[True]
    effective_on: date
    expires_on: date | None = None
    reason: str = Field(min_length=1,max_length=2000)


class CompanySource(Model):
    title: str = Field(min_length=1,max_length=200)
    url: HttpUrl
    publisher: str = Field(min_length=1,max_length=200)
    checked_on: date

    @field_validator('title','publisher')
    @classmethod
    def source_text(cls,value):
        if not value.strip() or any(ord(c)<32 and c not in '\t\n\r' for c in value):
            raise ValueError('Source text must be nonblank and contain valid characters.')
        return value.strip()


class CompanyProfile(Model):
    content: str = Field(min_length=1,max_length=80000)
    sources: list[CompanySource] = Field(max_length=30)

    @field_validator('content')
    @classmethod
    def profile_text(cls,value):
        if not value.strip() or any(ord(c)<32 and c not in '\t\n\r' for c in value):
            raise ValueError('Company text must be nonblank and contain valid characters.')
        return value


class SaveCompanyProfile(AcceptCompanyEvidence):
    profile: CompanyProfile


class EvidenceRegistration(Model):
    client_request_id: str
    body: dict


class FindingCorrection(Model):
    requirement_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    status: Literal['met','unmet','unconfirmed','not_assessed']
    company_citations: list[Citation] = Field(max_length=12)
    explanation: str = Field(min_length=1,max_length=2000)
    missing_information: str | None


class FactCorrections(Model):
    title: TextFact | None = None
    buyer: TextFact | None = None
    closing_at: TextFact | None = None
    service_start_on: TextFact | None = None
    term_months: IntegerFact | None = None


class ReconcileChange(Model):
    previous_requirement_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    replacement_requirement_ids: list[str] = Field(min_length=1,max_length=20)
    citations: list[Citation] = Field(min_length=1,max_length=12)


class AssessmentEdits(Model):
    requirements: list[FindingCorrection] = Field(default_factory=list,max_length=300)
    key_facts: FactCorrections | None = None
    reconciliations: list[ReconcileChange] = Field(default_factory=list,max_length=300)


class CorrectAssessment(Model):
    expected_assessment_version_id: UUID
    client_request_id: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=1,max_length=2000)
    edits: AssessmentEdits


class CreateReviewTask(Model):
    expected_assessment_version_id: UUID
    draft_ref: str = Field(min_length=1,max_length=80)
    assignee_id: UUID
    due_at: datetime | None = None
    # Keep retries of pre-editor requests byte-compatible for command hashing.
    question: str | None = Field(default=None,min_length=1,max_length=2000,exclude_if=lambda value:value is None)
    client_request_id: str = Field(min_length=1,max_length=100)

    @field_validator('question')
    @classmethod
    def question_nonblank(cls,value):
        if value is not None and not value.strip(): raise ValueError('Question cannot be blank.')
        return value.strip() if value is not None else None

    @field_validator('due_at')
    @classmethod
    def due_has_offset(cls,value):
        if value is not None and value.utcoffset() is None: raise ValueError('Due time requires an explicit UTC offset.')
        return value


class AnswerReviewTask(Model):
    expected_task_revision: int = Field(ge=1)
    response_kind: Literal['confirmed','denied','unable_to_confirm']
    text: str = Field(min_length=1,max_length=10000)
    basis: str | None = Field(default=None,min_length=1,max_length=2000)
    client_request_id: str = Field(min_length=1,max_length=100)

    @field_validator('text','basis')
    @classmethod
    def nonblank(cls,value):
        if value is not None and not value.strip(): raise ValueError('Answer and basis cannot be blank.')
        return value


class AskAssessment(Model):
    assessment_version_id: UUID
    text: str = Field(min_length=1,max_length=4000)
    client_request_id: str = Field(min_length=1,max_length=100)

    @field_validator('text')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Ask a nonblank question.')
        return value


class GetAssessmentInput(CandidateModel):
    pass


class SearchEvidenceInput(CandidateModel):
    query: str = Field(min_length=1,max_length=500)
    source_kind: Literal['tender','company','review_answer','all']
    limit: int = Field(default=5,ge=1,le=10)


class ReviewDraftInput(CandidateModel):
    requirement_refs: list[str] = Field(min_length=1,max_length=20)
    suggested_role: str = Field(min_length=1,max_length=80)
    question: str = Field(min_length=1,max_length=1000)
    rationale: str = Field(min_length=1,max_length=1000)


class AssistantText(CandidateModel):
    answer: str = Field(min_length=1,max_length=3800)
    citations: list[Citation] = Field(max_length=20)
    out_of_scope: bool


class ImportOpportunity(Model):
    notice_id:str=Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    title:str=Field(min_length=1,max_length=300)
    buyer:str|None=Field(default=None,max_length=200)
    reference:str=Field(min_length=1,max_length=100)
    category:str|None=Field(default=None,max_length=400)
    closing_at:datetime|None=None
    notice_text:str=Field(min_length=1,max_length=30000)
    client_request_id:str=Field(min_length=1,max_length=100)

    @field_validator("closing_at")
    @classmethod
    def aware_closing(cls,value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("An explicit closing timezone is required.")
        return value

    @field_validator("title","reference","notice_text")
    @classmethod
    def nonblank_notice(cls,value):
        if not value.strip(): raise ValueError("Notice fields cannot be blank.")
        return value


class TriageSuggestion(Model):
    expected_revision:int=Field(ge=1)
    action:Literal["start_assessment","defer","dismiss"]
    client_request_id:str=Field(min_length=1,max_length=100)


class RequestScreening(RequestAnalysis):
    investigation_queries:list[str]=Field(default_factory=list,max_length=3)

    @field_validator("investigation_queries")
    @classmethod
    def bounded_queries(cls,values):
        if any(not v.strip() or len(v)>200 for v in values): raise ValueError("Use bounded investigation queries.")
        return values


class PreparationBudget(Model):
    amount:Decimal=Field(gt=0,allow_inf_nan=False)
    currency:Literal["SGD","USD"]


class PreparationCondition(Model):
    finding_id:str=Field(min_length=1,max_length=64)
    condition:str=Field(min_length=1,max_length=1500,pattern=r"\S")


class RecordPreparationDecision(Model):
    expected_input_revision:int=Field(ge=1)
    expected_evidence_revision:int=Field(ge=0)
    screening_version_id:UUID
    approval_task_id:UUID
    outcome:Literal["approve_preparation","request_information","decline"]
    reason:str=Field(min_length=1,max_length=2000)
    preparation_scope:str|None=Field(default=None,min_length=1,max_length=3000)
    preparation_budget:PreparationBudget|None=None
    conditions:list[PreparationCondition]|None=Field(default=None,max_length=24)
    next_assignee_id:UUID|None=None
    information_request:str|None=Field(default=None,min_length=1,max_length=2000)
    due_at:datetime|None=None
    client_request_id:str=Field(min_length=1,max_length=100)

    @field_validator("reason","preparation_scope","information_request")
    @classmethod
    def nonblank_preparation(cls,value):
        if value is not None and not value.strip(): raise ValueError("A specific human statement is required.")
        return value

    @field_validator("due_at")
    @classmethod
    def aware_preparation_due(cls,value):
        if value is not None and value.utcoffset() is None: raise ValueError("An explicit timezone is required.")
        return value
