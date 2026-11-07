from uuid import UUID
from typing import Annotated, Literal

import asyncio
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Query, Body
from fastapi.responses import Response, JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.auth import get_actor
from app.tenders.models import ActorContext, CreateTender, RequestAnalysis, UploadMetadata, RegisterSources, SourceInput
from app.tenders.policy import DomainError
from app.tenders.documents import inspect_upload, MAX_PACK, MAX_FILE, MAX_FILES
from app.tenders.models import SaveCompanyProfile,AcceptCompanyEvidence,CreateReviewTask,AnswerReviewTask

from app.tenders.views import ActorView,InboxView,TenderDetail,JobView,CompanyVersion,CompanyView,AssessmentView,ReviewTaskView,MembersView,SourcesView,HistoryView

from app.tenders.models import ImportOpportunity,TriageSuggestion,RequestOpportunityFeedback,AnswerOpportunityFeedback,SetOpportunityDiscovery
from app.tenders.opportunities import Opportunities
from app.tenders.opportunity_discovery import discovery_settings
from app.tenders.opportunity_feedback import OpportunityFeedback
from app.tenders.views import OpportunityView,OpportunitiesView,OpportunityFeedbackList,OpportunityFeedbackView,OpportunityDiscoveryView
from app.tenders.preparation import (
    CreateDeliverable, DeliverableReceipt, FileCommand, Preparation, PreparationFile,
    PreparationView, UpdateDeliverablePlan, ReviewCommand, VersionCommand, DraftProposal,
)
from app.tenders.proposal import ProposalView
from app.tenders.submission import (
    DecideRelease, PackageId, PortalReceiptUpload, RecordPortalReceipt, SealPackage, Submission, SubmissionView,
)

router = APIRouter(prefix="/api/v1")


@router.get("/me",response_model=ActorView)
async def me(actor: ActorContext = Depends(get_actor)):
    return {"schema_version":"m1.v1",**actor.model_dump(mode="json")}


@router.get("/tenders",response_model=InboxView)
async def list_tenders(request: Request, actor: ActorContext = Depends(get_actor)):
    return await request.app.state.repository.list_tenders(actor)


@router.post("/tenders",status_code=201)
async def create_tender(command: CreateTender, request: Request, actor: ActorContext = Depends(get_actor)):
    return await request.app.state.repository.create_tender(actor,command)


@router.get("/tenders/{tender_id}",response_model=TenderDetail)
async def get_tender(tender_id: UUID, request: Request, actor: ActorContext = Depends(get_actor)):
    return await request.app.state.repository.get_tender(actor,tender_id)


@router.delete("/tenders/{tender_id}")
async def delete_tender(tender_id: UUID, command: RequestAnalysis, request: Request, actor: ActorContext = Depends(get_actor)):
    return await request.app.state.repository.delete_tender(actor,tender_id,command)


@router.post('/tenders/{tender_id}/documents',status_code=201,openapi_extra={'requestBody':{
    'required':True,'content':{'multipart/form-data':{'schema':{'type':'object','required':['metadata','files'],
        'properties':{'metadata':{'type':'string','description':'JSON: expected_input_revision, client_request_id, files [{role, amends_version_id?}]'},
                      'files':{'type':'array','maxItems':MAX_FILES,'items':{'type':'string','format':'binary'}}}}}}}})
async def upload_documents(tender_id: UUID,request: Request,actor: ActorContext=Depends(get_actor)):
    # Bound chunked requests too, before multipart parsing can spool unbounded files.
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PACK+64*1024:
            raise DomainError(413,'PACK_LIMIT','The upload exceeds the 100 MiB source-set limit.')
        chunks.append(chunk)
    async def receive():
        return {'type':'http.request','body':b''.join(chunks),'more_body':False}
    bounded = Request(request.scope,receive)
    try:
        async with bounded.form(max_files=MAX_FILES,max_fields=1,max_part_size=32768) as form:
            metadata = UploadMetadata.model_validate_json(form.get('metadata',''))
            files = form.getlist('files')
            if len(files)!=len(metadata.files) or any(not isinstance(f,UploadFile) for f in files):
                raise DomainError(422,'INVALID_UPLOAD','Each file needs matching role metadata.')
            sources,contents = [],[]
            for file,entry in zip(files,metadata.files,strict=True):
                data = await file.read(MAX_FILE+1)
                info = await asyncio.to_thread(inspect_upload,file.filename,file.content_type,data)
                key = f'{actor.workspace_id}/{tender_id}/{info["sha256"]}{Path(file.filename).suffix.lower()}'
                sources.append(SourceInput(**info,storage_key=key,**entry.model_dump()))
                contents.append(data)
            command = RegisterSources(tender_id=tender_id,expected_input_revision=metadata.expected_input_revision,
                client_request_id=metadata.client_request_id,sources=sources)
            return await request.app.state.repository.register_sources(actor,command,contents,request.app.state.storage)
    except (ValidationError,ValueError,HTTPException):
        raise DomainError(422,'INVALID_UPLOAD','Upload metadata does not match the required schema.') from None


@router.get('/sources/{version_id}')
async def get_source(version_id: UUID,request: Request,actor: ActorContext=Depends(get_actor)):
    source = await request.app.state.repository.get_source(actor,version_id)
    headers = {'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}
    if source['content_type'] == 'application/pdf':
        data = await request.app.state.storage.get(source['storage_key'])
        headers['Content-Disposition'] = "inline; filename*=UTF-8''"+quote(source['filename'],safe='')
        return Response(data,media_type='application/pdf',headers=headers)
    return JSONResponse(await request.app.state.repository.get_source_text(actor,version_id),headers=headers)


@router.get('/sources/{version_id}/original')
async def get_original_source(version_id: UUID,request: Request,actor: ActorContext=Depends(get_actor)):
    source = await request.app.state.repository.get_source(actor,version_id)
    data = await request.app.state.storage.get(source['storage_key'])
    headers = {'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
               'Content-Disposition':"attachment; filename*=UTF-8''"+quote(source['filename'],safe='')}
    return Response(data,media_type=source['content_type'],headers=headers)


@router.get('/jobs/{job_id}',response_model=JobView)
async def get_job(job_id: UUID,request: Request,actor: ActorContext=Depends(get_actor)):
    return await request.app.state.repository.get_job(actor,job_id)


@router.get('/company-evidence',response_model=CompanyView)
async def company_evidence(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.assessments import get_company
    return await get_company(request.app.state.repository,actor)


@router.get('/company-evidence/versions/{version_id}',response_model=CompanyVersion)
async def company_version(version_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.assessments import get_company_version
    return await get_company_version(request.app.state.repository,actor,version_id)


@router.post('/company-evidence',status_code=201,openapi_extra={'requestBody':{'required':True,'content':{'multipart/form-data':{'schema':{'type':'object','required':['metadata','file'],'properties':{'metadata':{'type':'string','description':'JSON: expected_evidence_revision, client_request_id, accept: true, effective_on, expires_on?, reason'},'file':{'type':'string','format':'binary'}}}}}}})
async def accept_company_evidence(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.assessments import accept_company
    repository=request.app.state.repository
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'admin')
    chunks=[]
    size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>20*1024*1024+65536: raise DomainError(413,'FILE_TOO_LARGE','Company evidence must be at most 20 MiB.')
        chunks.append(chunk)
    async def receive(): return {'type':'http.request','body':b''.join(chunks),'more_body':False}
    try:
        async with Request(request.scope,receive).form(max_files=1,max_fields=1,max_part_size=16384) as form:
            command=AcceptCompanyEvidence.model_validate_json(form.get('metadata',''))
            file=form.get('file')
            if not isinstance(file,UploadFile): raise ValueError()
            data=await file.read(20*1024*1024+1)
            info=await asyncio.to_thread(inspect_upload,file.filename,file.content_type,data)
            return await accept_company(repository,actor,command,info,data,request.app.state.storage)
    except (ValidationError,ValueError,HTTPException):
        raise DomainError(422,'INVALID_UPLOAD','Company evidence metadata or source is invalid.') from None


@router.post('/company-evidence/profile',status_code=201)
async def save_company_profile(command:SaveCompanyProfile,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.assessments import accept_company,profile_document
    from app.tenders.documents import DOCX_MIME
    repository=request.app.state.repository
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'admin')
    data=await asyncio.to_thread(profile_document,command.profile)
    info=await asyncio.to_thread(inspect_upload,'Company.docx',DOCX_MIME,data)
    return await accept_company(repository,actor,command,info,data,request.app.state.storage)


@router.get('/assessments/{version_id}',response_model=AssessmentView)
async def get_assessment(version_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.assessments import get_assessment as get
    return await get(request.app.state.repository,actor,version_id)


@router.post('/jobs/{job_id}/cancel')
async def cancel_job(job_id: UUID,command: RequestAnalysis,request: Request,actor: ActorContext=Depends(get_actor)):
    return await request.app.state.repository.cancel_job(actor,job_id,command)


@router.post('/tenders/{tender_id}/review-tasks',status_code=201,response_model=ReviewTaskView)
async def create_review_task(tender_id:UUID,command:CreateReviewTask,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).confirm_task(actor,tender_id,command)


@router.post('/review-tasks/{task_id}/answers',status_code=201)
async def answer_review_task(task_id:UUID,command:AnswerReviewTask,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).answer(actor,task_id,command)


@router.get('/members',response_model=MembersView)
async def workspace_members(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.workspace_views import members
    return await members(request.app.state.repository,actor)


@router.get('/assessments/{assessment_id}/sources',response_model=SourcesView)
async def assessment_sources(assessment_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.workspace_views import sources
    return await sources(request.app.state.repository,actor,assessment_id)


@router.get('/tenders/{tender_id}/history',response_model=HistoryView)
async def tender_history(tender_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.workspace_views import history
    return await history(request.app.state.repository,actor,tender_id)




@router.get("/opportunity-suggestions",response_model=OpportunitiesView)
async def opportunity_suggestions(request:Request,actor:ActorContext=Depends(get_actor),
        state:Literal["suggested","deferred","dismissed","activated"]="suggested",
        after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    return await Opportunities(request.app.state.pool).list_suggestions(actor,state,after,limit)


@router.post("/opportunity-suggestions/import",status_code=201,response_model=OpportunityView)
async def import_opportunity(command:ImportOpportunity,request:Request,actor:ActorContext=Depends(get_actor)):
    return await Opportunities(request.app.state.pool).import_notice(actor,command)


@router.post("/opportunity-suggestions/{suggestion_id}/triage",response_model=OpportunityView)
async def triage_opportunity(suggestion_id:UUID,command:TriageSuggestion,request:Request,actor:ActorContext=Depends(get_actor)):
    return await Opportunities(request.app.state.pool).triage_suggestion(actor,suggestion_id,command)


@router.get("/opportunity-discovery",response_model=OpportunityDiscoveryView)
async def get_opportunity_discovery(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.config import get_settings
    return await discovery_settings(request.app.state.repository,actor,get_settings())


@router.put("/opportunity-discovery",response_model=OpportunityDiscoveryView)
async def set_opportunity_discovery(command:SetOpportunityDiscovery,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.config import get_settings
    return await discovery_settings(request.app.state.repository,actor,get_settings(),command)


@router.get("/opportunity-feedback",response_model=OpportunityFeedbackList)
async def opportunity_feedback(request:Request,actor:ActorContext=Depends(get_actor),
        after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    return await OpportunityFeedback(request.app.state.pool).list_feedback(actor,after,limit)


@router.post("/opportunity-suggestions/{suggestion_id}/feedback",status_code=201,response_model=OpportunityFeedbackView)
async def request_opportunity_feedback(suggestion_id:UUID,command:RequestOpportunityFeedback,
        request:Request,actor:ActorContext=Depends(get_actor)):
    return await OpportunityFeedback(request.app.state.pool).request_feedback(actor,suggestion_id,command)


@router.post("/opportunity-feedback/{feedback_id}/answer",response_model=OpportunityFeedbackView)
async def answer_opportunity_feedback(feedback_id:UUID,command:AnswerOpportunityFeedback,
        request:Request,actor:ActorContext=Depends(get_actor)):
    return await OpportunityFeedback(request.app.state.pool).answer_feedback(actor,feedback_id,command)


from app.tenders.models import RequestScreening,RecordPreparationDecision
from app.tenders.views import ReviewCaseView,ReviewCasesView,InboxActionsView,PreparationDecisionView


def qualification_workflow(request):
    from app.tenders.screening_workflow import ScreeningWorkflow
    return ScreeningWorkflow(request.app.state.pool)


@router.post("/tenders/{tender_id}/screenings",status_code=202,response_model=JobView)
async def request_screening(tender_id:UUID,command:RequestScreening,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).request(actor,tender_id,command)


@router.post("/tenders/{tender_id}/preparation-decisions",status_code=201,response_model=PreparationDecisionView)
async def record_preparation(tender_id:UUID,command:RecordPreparationDecision,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).decide(actor,tender_id,command)


def preparation_tracking(request):
    return Preparation(request.app.state.repository, request.app.state.storage)


@router.get("/tenders/{tender_id}/preparation", response_model=PreparationView)
async def get_preparation(tender_id: UUID, request: Request, actor: ActorContext = Depends(get_actor)):
    return await preparation_tracking(request).read(actor, tender_id)


@router.post("/tenders/{tender_id}/preparation", status_code=201, response_model=DeliverableReceipt)
async def create_deliverable(tender_id: UUID, command: CreateDeliverable, request: Request,
                             actor: ActorContext = Depends(get_actor)):
    result = await preparation_tracking(request).create(actor, tender_id, command)
    return DeliverableReceipt(id=result["id"], revision=result["revision"])


@router.post("/tenders/{tender_id}/preparation/{item_id}/actions", status_code=201, response_model=DeliverableReceipt)
async def change_deliverable(tender_id: UUID, item_id: UUID,
                             command: Annotated[ReviewCommand | UpdateDeliverablePlan, Body(discriminator="action")],
                             request: Request, actor: ActorContext = Depends(get_actor)):
    result = await preparation_tracking(request).change(actor, tender_id, item_id, command)
    return DeliverableReceipt(id=result["id"], revision=result["revision"])


@router.get("/tenders/{tender_id}/preparation/{item_id}/proposal", response_model=ProposalView)
async def read_proposal(tender_id: UUID, item_id: UUID, request: Request,
                        actor: ActorContext = Depends(get_actor)):
    from app.tenders.proposal import read
    return await read(preparation_tracking(request), actor, tender_id, item_id)


@router.post("/tenders/{tender_id}/preparation/{item_id}/proposal", status_code=201, response_model=PreparationFile)
async def draft_proposal(tender_id: UUID, item_id: UUID, command: DraftProposal, request: Request,
                         actor: ActorContext = Depends(get_actor)):
    return await preparation_tracking(request).change(actor, tender_id, item_id, command)


def upload_schema(metadata):
    return {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["metadata", "file"], "properties": {
            "metadata": {"type": "string", "description": metadata},
            "file": {"type": "string", "format": "binary"}}}}}}}


async def read_file_upload(request, metadata_model):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FILE + 64 * 1024:
            raise DomainError(413, "FILE_TOO_LARGE", "Files must be at most 20 MiB.")
        body.extend(chunk)

    async def receive():
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    try:
        async with Request(request.scope, receive).form(max_files=1, max_fields=1) as form:
            metadata = metadata_model.model_validate_json(form.get("metadata", ""))
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise ValueError("A file is required.")
            data = await file.read(MAX_FILE + 1)
            info = await asyncio.to_thread(inspect_upload, file.filename, file.content_type, data)
    except (ValidationError, ValueError, HTTPException):
        raise DomainError(422, "INVALID_UPLOAD", "Choose a file and provide valid upload details.") from None
    return metadata, info, data


@router.post("/tenders/{tender_id}/preparation/{item_id}/files", status_code=201, response_model=PreparationFile,
             openapi_extra=upload_schema("JSON: approval_id, expected_revision, client_request_id"))
async def upload_preparation_file(tender_id: UUID, item_id: UUID, request: Request,
                                  actor: ActorContext = Depends(get_actor)):
    metadata, info, data = await read_file_upload(request, VersionCommand)
    command = FileCommand(**metadata.model_dump(), filename=info["filename"], sha256=info["sha256"])
    return await preparation_tracking(request).change(actor, tender_id, item_id, command, (info, data))


@router.get("/tenders/{tender_id}/preparation/{item_id}/files/{file_id}")
async def get_preparation_file(tender_id: UUID, item_id: UUID, file_id: UUID, request: Request,
                               actor: ActorContext = Depends(get_actor)):
    file, data = await preparation_tracking(request).download(actor, tender_id, item_id, file_id)
    return private_attachment(file["filename"], file["content_type"], data)


def private_attachment(filename, content_type, data):
    return Response(data, media_type=content_type, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
    })


def submission_control(request):
    return Submission(preparation_tracking(request))


@router.get("/tenders/{tender_id}/submission", response_model=SubmissionView)
async def get_submission(tender_id: UUID, request: Request, actor: ActorContext = Depends(get_actor)):
    return await submission_control(request).read(actor, tender_id)


@router.post("/tenders/{tender_id}/submission/packages", status_code=201, response_model=PackageId)
async def seal_submission(tender_id: UUID, command: SealPackage, request: Request,
                          actor: ActorContext = Depends(get_actor)):
    return await submission_control(request).write(actor, tender_id, command, "seal")


@router.post("/tenders/{tender_id}/submission/packages/{package_id}/decision", status_code=201, response_model=PackageId)
async def decide_submission(tender_id: UUID, package_id: UUID, command: DecideRelease, request: Request,
                            actor: ActorContext = Depends(get_actor)):
    return await submission_control(request).write(actor, tender_id, command, "decision", package_id)


@router.post("/tenders/{tender_id}/submission/packages/{package_id}/receipt", status_code=201, response_model=PackageId,
             openapi_extra=upload_schema("JSON: portal_reference, submitted_at, client_request_id"))
async def record_submission_receipt(tender_id: UUID, package_id: UUID, request: Request,
                                    actor: ActorContext = Depends(get_actor)):
    metadata, info, data = await read_file_upload(request, RecordPortalReceipt)
    if info["content_type"] != "application/pdf":
        raise DomainError(422, "INVALID_RECEIPT", "Upload the portal receipt as a PDF.")
    command = PortalReceiptUpload(**metadata.model_dump(), filename=info["filename"], sha256=info["sha256"])
    return await submission_control(request).write(actor, tender_id, command, "receipt", package_id, data)


@router.get("/tenders/{tender_id}/submission/packages/{package_id}/receipt")
async def get_submission_receipt(tender_id: UUID, package_id: UUID, request: Request,
                                 actor: ActorContext = Depends(get_actor)):
    filename, data = await submission_control(request).download(actor, tender_id, package_id)
    return private_attachment(filename, "application/pdf", data)


@router.get("/review-cases",response_model=ReviewCasesView)
async def review_cases(request:Request,actor:ActorContext=Depends(get_actor),after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    from app.tenders.workspace_views import list_review_cases
    return await list_review_cases(request.app.state.repository,actor,after,limit)


@router.get("/review-cases/{tender_id}",response_model=ReviewCaseView)
async def review_case(tender_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.tenders.workspace_views import get_review_case
    return await get_review_case(request.app.state.repository,actor,tender_id)


@router.get("/inbox-actions",response_model=InboxActionsView)
async def human_actions(request:Request,actor:ActorContext=Depends(get_actor),after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    from app.tenders.workspace_views import list_inbox_actions
    return await list_inbox_actions(request.app.state.repository,actor,after,limit)
