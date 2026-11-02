"""Human-confirmed review requests and atomic answer/reassessment commands."""
from datetime import datetime,timedelta,timezone
import hashlib
import json

from app.m1.analysis import requirement_identity
from app.m1.analysis_runtime import utc_now
from app.m1.assessments import assessment_view
from app.m1.policy import DomainError

ROUTING={'engineering_lead':'service_reviewer'}


def default_due_at(now,closing_at):
    if now.utcoffset() is None or closing_at is None or closing_at.utcoffset() is None or closing_at<=now:
        raise DomainError(422,'DUE_DATE_REQUIRED','Resolve the closing time or supply an explicit future review deadline.')
    now,closing_at=now.astimezone(timezone.utc),closing_at.astimezone(timezone.utc)
    return max(now,min(now+timedelta(hours=48),closing_at-timedelta(hours=24)))


def task_view(row,input_revision,evidence_revision):
    manifest=json.loads(row['manifest'])
    return {'schema_version':'m1.v1',**{key:str(row[key]) for key in ('id','tender_id','assessment_version_id','assignee_id','created_by')},
        **{key:row[key] for key in ('draft_ref','requirement_ids','purpose','question','status','revision')},
        'due_at':row['due_at'].isoformat(),'created_at':row['created_at'].isoformat(),'manifest':manifest,
        'is_current':manifest.get('assessment_input_revision')==input_revision and manifest.get('evidence_revision',0)==evidence_revision}


async def list_review_tasks(connection,workspace_id,tender_id,input_revision,evidence_revision):
    rows=await connection.fetch("""SELECT t.*,a.id answer_id,a.evidence_version_id,a.actor_id,a.created_at answered_at,
        a.reassessment_job_id,v.payload answer_payload,j.status reassessment_status
        FROM m1_app.review_tasks t LEFT JOIN m1_app.review_answers a ON a.workspace_id=t.workspace_id AND a.task_id=t.id
        LEFT JOIN m1_app.artifact_versions v ON v.workspace_id=a.workspace_id AND v.id=a.evidence_version_id
        LEFT JOIN m1_app.jobs j ON j.workspace_id=a.workspace_id AND j.id=a.reassessment_job_id
        WHERE t.workspace_id=$1 AND t.tender_id=$2 ORDER BY t.created_at,t.id""",workspace_id,tender_id)
    result=[]
    for row in rows:
        view=task_view(row,input_revision,evidence_revision)
        view['answer']=None
        if row['answer_id']:
            payload=json.loads(row['answer_payload'])
            view['answer']={'id':str(row['answer_id']),'evidence_version_id':str(row['evidence_version_id']),
                'actor_id':str(row['actor_id']),'created_at':row['answered_at'].isoformat(),
                **{key:payload.get(key) for key in ('response_kind','text','basis')},
                'reassessment_job_id':str(row['reassessment_job_id']),'reassessment_status':row['reassessment_status']}
        result.append(view)
    return result


async def create_review_task(repository,actor,tender_id,command,screening_enabled=None):
    async with repository.pool.acquire() as c:
        kind=await c.fetchval("SELECT kind FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2",
                             actor.workspace_id,command.expected_assessment_version_id)
    if kind=="screening":
        from app.m1.screening_workflow import ScreeningWorkflow
        if screening_enabled is None:
            from app.config import get_settings
            screening_enabled=get_settings().qualification_workflow_enabled
        return await ScreeningWorkflow(repository.pool,screening_enabled).confirm_task(actor,tender_id,command)
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'bid_owner')
        operation='create_review_task:'+str(tender_id)
        replay=await repository._claim(connection,actor,operation,command)
        if replay is not None: return replay
        evidence_revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1 FOR SHARE',actor.workspace_id)
        tender=await repository._tender(connection,actor,tender_id,lock=True)
        assessment=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,tender_id)
        if not assessment or assessment['id']!=command.expected_assessment_version_id or not assessment_view(assessment,tender['input_revision'],evidence_revision)['is_current']:
            raise DomainError(409,'STALE_ASSESSMENT','Confirm a draft from the current assessment.')
        payload=json.loads(assessment['payload'])
        draft=next((d for d in payload['candidate']['review_requests'] if d['draft_ref']==command.draft_ref),None)
        if draft is None:
            prepared=await connection.fetchval("SELECT response FROM m1_app.assistant_runs WHERE workspace_id=$1 AND tender_id=$2 AND assessment_version_id=$3 AND status='completed' AND response @> $4::jsonb ORDER BY created_at DESC LIMIT 1",actor.workspace_id,tender_id,assessment['id'],json.dumps({'review_request_drafts':[{'draft_ref':command.draft_ref}]}))
            if prepared: draft=next((d for d in json.loads(prepared)['review_request_drafts'] if d['draft_ref']==command.draft_ref),None)
        if draft is None: raise DomainError(422,'INVALID_DRAFT','The review draft does not exist in this assessment or a completed assistant turn.')
        requirements=[r for r in payload['candidate']['requirements'] if r['local_ref'] in draft['requirement_refs']]
        if not any(r['kind'] in ('eligibility','delivery') and r['status'] in ('unconfirmed','unmet') for r in requirements):
            raise DomainError(422,'DRAFT_RESOLVED','This draft no longer concerns an unresolved qualification finding.')
        roles=await connection.fetchval('SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2 FOR SHARE',actor.workspace_id,command.assignee_id)
        required_role=ROUTING.get(draft['suggested_role'])
        if not roles or ('bid_owner' not in roles and (required_role is None or required_role not in roles)):
            raise DomainError(422,'INVALID_ASSIGNEE','Choose an authorized reviewer in this workspace.')
        ids=sorted(requirement_identity(r) for r in requirements)
        purpose=hashlib.sha256(json.dumps(ids).encode()).hexdigest()
        existing=await connection.fetchrow("SELECT * FROM m1_app.review_tasks WHERE workspace_id=$1 AND tender_id=$2 AND requirement_ref=$3 AND assignee_id=$4 AND purpose='qualification_review' AND status='open'",actor.workspace_id,tender_id,purpose,command.assignee_id)
        if existing:
            return await repository._finish(connection,actor,operation,command,task_view(existing,tender['input_revision'],evidence_revision))
        now=utc_now()
        closing=payload['candidate']['key_facts']['closing_at']['value']
        closing=datetime.fromisoformat(closing) if closing else None
        if command.due_at is None: due=default_due_at(now,closing)
        else:
            latest=default_due_at(now,closing) if closing and closing>now else now+timedelta(hours=48)
            due=command.due_at.astimezone(timezone.utc)
            if due<=now or due>latest: raise DomainError(422,'INVALID_DUE_AT','Choose an earlier future due time within the review window.')
        sources=json.loads(assessment['manifest'])
        manifest={'source_set_version_id':sources['source_set_version_id'],'assessment_input_revision':assessment['input_revision'],
            'evidence_revision':evidence_revision,'company_evidence_version_ids':sources.get('company_evidence_version_ids',[]),
            'review_answer_version_ids':[a['id'] for a in sources.get('review_answers',[])],
            'documents':[{key:document[key] for key in ('id','sha256','role')} for document in sources.get('documents',[])]}
        row=await connection.fetchrow("""INSERT INTO m1_app.review_tasks(workspace_id,tender_id,assessment_version_id,requirement_ref,
            requirement_ids,draft_ref,assignee_id,question,status,due_at,manifest,created_by)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,'open',$9,$10::jsonb,$11) RETURNING *""",
            actor.workspace_id,tender_id,assessment['id'],purpose,ids,command.draft_ref,command.assignee_id,command.question or draft['question'],due,json.dumps(manifest),actor.user_id)
        return await repository._finish(connection,actor,operation,command,task_view(row,tender['input_revision'],evidence_revision))


async def answer_review_task(repository,actor,task_id,command):
    async with repository.pool.acquire() as c:
        workflow=await c.fetchval("SELECT manifest->>'workflow' FROM m1_app.review_tasks WHERE workspace_id=$1 AND id=$2",
                                 actor.workspace_id,task_id)
    if workflow=="screening.v1":
        from app.m1.screening_workflow import ScreeningWorkflow
        return await ScreeningWorkflow(repository.pool).answer(actor,task_id,command)
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor)
        operation='answer_review_task:'+str(task_id)
        replay=await repository._claim(connection,actor,operation,command)
        if replay is not None: return replay
        evidence_revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1 FOR SHARE',actor.workspace_id)
        tender_id=await connection.fetchval('SELECT tender_id FROM m1_app.review_tasks WHERE workspace_id=$1 AND id=$2',actor.workspace_id,task_id)
        if tender_id is None: raise DomainError(404,'NOT_FOUND','Review task not found.')
        tender=await repository._tender(connection,actor,tender_id,lock=True)
        task=await connection.fetchrow('SELECT * FROM m1_app.review_tasks WHERE workspace_id=$1 AND id=$2 FOR UPDATE',actor.workspace_id,task_id)
        roles=await connection.fetchval('SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2',actor.workspace_id,actor.user_id)
        if task['assignee_id']!=actor.user_id or not set(roles)&{'service_reviewer','bid_owner'}:
            raise DomainError(403,'FORBIDDEN','Only the assigned authorized reviewer may answer.')
        if 'bid_owner' in roles and not command.basis:
            raise DomainError(422,'ANSWER_BASIS_REQUIRED','An assigned bid owner must record the basis for the answer.')
        if task['status']!='open' or task['revision']!=command.expected_task_revision:
            raise DomainError(409,'STALE_TASK','The task changed or already has an answer.')
        manifest=json.loads(task['manifest'])
        payload={'task_id':str(task_id),'requirement_ids':task['requirement_ids'],'assessment_version_id':str(task['assessment_version_id']),
            'question':task['question'],'source_manifest':manifest,'response_kind':command.response_kind,'text':command.text,'basis':command.basis}
        revision=await connection.fetchval('UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1 RETURNING input_revision',tender_id)
        evidence=await connection.fetchval("""INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
            VALUES($1,$2,'review_answer',$3,$4::jsonb,$5::jsonb,$6) RETURNING id""",actor.workspace_id,tender_id,revision,json.dumps(manifest),json.dumps(payload),actor.user_id)
        job=await repository._enqueue_analysis(connection,actor,{**dict(tender),'input_revision':revision},evidence_revision)
        answer=await connection.fetchval("""INSERT INTO m1_app.review_answers(workspace_id,task_id,evidence_version_id,actor_id,reassessment_job_id)
            VALUES($1,$2,$3,$4,$5) RETURNING id""",actor.workspace_id,task_id,evidence,actor.user_id,job['id'])
        await connection.execute("UPDATE m1_app.review_tasks SET status='answered',revision=revision+1 WHERE id=$1",task_id)
        result={'schema_version':'m1.v1','answer_id':str(answer),'evidence_version_id':str(evidence),'reassessment_job_id':job['id'],
            'input_revision':revision,'task_id':str(task_id),'task_revision':task['revision']+1}
        return await repository._finish(connection,actor,operation,command,result)
