"""Human-confirmed review requests and atomic answer/reassessment commands."""
from datetime import datetime,timedelta,timezone
import json

from app.tenders.policy import DomainError


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
