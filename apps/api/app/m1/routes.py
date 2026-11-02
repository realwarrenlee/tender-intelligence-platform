from uuid import UUID
from typing import Literal

import asyncio
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response, JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.auth import get_actor
from app.m1.models import ActorContext, CreateTender, RecordDecision, RequestAnalysis, UploadMetadata, RegisterSources, SourceInput
from app.m1.policy import DomainError
from app.m1.documents import inspect_upload, MAX_PACK, MAX_FILE, MAX_FILES
from app.m1.models import SaveCompanyProfile,AcceptCompanyEvidence,CorrectAssessment,CreateReviewTask,AnswerReviewTask,AskAssessment

from app.m1.views import ActorView,InboxView,TenderDetail,JobView,CompanyVersion,CompanyView,AssessmentView,DecisionView,AssistantView,ReviewTaskView,MembersView,SourcesView,HistoryView

from app.m1.models import ImportOpportunity,TriageSuggestion
from app.m1.opportunities import Opportunities
from app.m1.views import OpportunityView,OpportunitiesView

router = APIRouter(prefix="/api/v1")


@router.get("/me",response_model=ActorView)
async def me(request:Request,actor: ActorContext = Depends(get_actor)):
    return {"schema_version":"m1.v1",**actor.model_dump(mode="json"),
            "qualification_workflow_enabled":qualification_workflow(request).enabled}


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


@router.post("/tenders/{tender_id}/analyses",status_code=202,response_model=JobView)
async def request_analysis(tender_id: UUID, command: RequestAnalysis, request: Request, actor: ActorContext = Depends(get_actor)):
    if qualification_workflow(request).enabled:
        raise DomainError(409,"BOUNDED_WORKFLOW_REQUIRED","Use bounded screening for new enabled-workflow assessments.")
    return await request.app.state.repository.request_analysis(actor,tender_id,command)


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


@router.get('/jobs/{job_id}',response_model=JobView)
async def get_job(job_id: UUID,request: Request,actor: ActorContext=Depends(get_actor)):
    return await request.app.state.repository.get_job(actor,job_id)


@router.get('/company-evidence',response_model=CompanyView)
async def company_evidence(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assessments import get_company
    return await get_company(request.app.state.repository,actor)


@router.get('/company-evidence/versions/{version_id}',response_model=CompanyVersion)
async def company_version(version_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assessments import get_company_version
    return await get_company_version(request.app.state.repository,actor,version_id)


@router.post('/company-evidence',status_code=201,openapi_extra={'requestBody':{'required':True,'content':{'multipart/form-data':{'schema':{'type':'object','required':['metadata','file'],'properties':{'metadata':{'type':'string','description':'JSON: expected_evidence_revision, client_request_id, accept: true, effective_on, expires_on?, reason'},'file':{'type':'string','format':'binary'}}}}}}})
async def accept_company_evidence(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assessments import accept_company
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
    from app.m1.assessments import accept_company,profile_document
    from app.m1.documents import DOCX_MIME
    repository=request.app.state.repository
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'admin')
    data=await asyncio.to_thread(profile_document,command.profile)
    info=await asyncio.to_thread(inspect_upload,'Company.docx',DOCX_MIME,data)
    return await accept_company(repository,actor,command,info,data,request.app.state.storage)


@router.patch('/tenders/{tender_id}/assessment',response_model=AssessmentView)
async def correct_assessment(tender_id:UUID,command:CorrectAssessment,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assessments import correct_assessment as correct
    return await correct(request.app.state.repository,actor,tender_id,command)


@router.get('/assessments/{version_id}',response_model=AssessmentView)
async def get_assessment(version_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assessments import get_assessment as get
    return await get(request.app.state.repository,actor,version_id)


@router.post('/jobs/{job_id}/cancel')
async def cancel_job(job_id: UUID,command: RequestAnalysis,request: Request,actor: ActorContext=Depends(get_actor)):
    return await request.app.state.repository.cancel_job(actor,job_id,command)


@router.post("/tenders/{tender_id}/decisions",status_code=201,response_model=DecisionView)
async def record_decision(tender_id: UUID, command: RecordDecision, request: Request, actor: ActorContext = Depends(get_actor)):
    return await request.app.state.repository.record_decision(actor,tender_id,command)


@router.post('/tenders/{tender_id}/review-tasks',status_code=201,response_model=ReviewTaskView)
async def create_review_task(tender_id:UUID,command:CreateReviewTask,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.reviews import create_review_task as create
    return await create(request.app.state.repository,actor,tender_id,command,qualification_workflow(request).enabled)


@router.post('/review-tasks/{task_id}/answers',status_code=201)
async def answer_review_task(task_id:UUID,command:AnswerReviewTask,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.reviews import answer_review_task as answer
    return await answer(request.app.state.repository,actor,task_id,command)


@router.get('/tenders/{tender_id}/qualification-brief')
async def qualification_brief(tender_id:UUID,assessment_version_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.exports import export_qualification_brief
    body=await export_qualification_brief(request.app.state.repository,actor,tender_id,assessment_version_id)
    return Response(body,media_type='text/markdown',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
        'Content-Disposition':f'attachment; filename="qualification-{tender_id}-{assessment_version_id}.md"'})


@router.post('/tenders/{tender_id}/assistant-messages',response_model=AssistantView)
async def assistant_message(tender_id:UUID,command:AskAssessment,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.assistant_runtime import answer_assessment_question
    return await answer_assessment_question(request.app.state.repository,actor,tender_id,command,getattr(request.app.state,'assistant_model',None))

@router.get('/members',response_model=MembersView)
async def workspace_members(request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.workspace_views import members
    return await members(request.app.state.repository,actor)


@router.get('/assessments/{assessment_id}/sources',response_model=SourcesView)
async def assessment_sources(assessment_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.workspace_views import sources
    return await sources(request.app.state.repository,actor,assessment_id)


@router.get('/tenders/{tender_id}/history',response_model=HistoryView)
async def tender_history(tender_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.workspace_views import history
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


from app.m1.models import RequestScreening,RecordPreparationDecision
from app.m1.views import ReviewCaseView,ReviewCasesView,InboxActionsView,PreparationDecisionView


def qualification_workflow(request):
    from app.config import get_settings
    from app.m1.screening_workflow import ScreeningWorkflow
    return ScreeningWorkflow(request.app.state.pool,
        getattr(request.app.state,"qualification_enabled",get_settings().qualification_workflow_enabled))


@router.post("/tenders/{tender_id}/screenings",status_code=202,response_model=JobView)
async def request_screening(tender_id:UUID,command:RequestScreening,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).request(actor,tender_id,command)


@router.post("/tenders/{tender_id}/preparation-decisions",status_code=201,response_model=PreparationDecisionView)
async def record_preparation(tender_id:UUID,command:RecordPreparationDecision,request:Request,actor:ActorContext=Depends(get_actor)):
    return await qualification_workflow(request).decide(actor,tender_id,command)


@router.get("/review-cases",response_model=ReviewCasesView)
async def review_cases(request:Request,actor:ActorContext=Depends(get_actor),after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    from app.m1.workspace_views import list_review_cases
    return await list_review_cases(request.app.state.repository,actor,after,limit)


@router.get("/review-cases/{tender_id}",response_model=ReviewCaseView)
async def review_case(tender_id:UUID,request:Request,actor:ActorContext=Depends(get_actor)):
    from app.m1.workspace_views import get_review_case
    return await get_review_case(request.app.state.repository,actor,tender_id)


@router.get("/inbox-actions",response_model=InboxActionsView)
async def human_actions(request:Request,actor:ActorContext=Depends(get_actor),after:UUID|None=None,limit:int=Query(default=50,ge=1,le=50)):
    from app.m1.workspace_views import list_inbox_actions
    return await list_inbox_actions(request.app.state.repository,actor,after,limit)
