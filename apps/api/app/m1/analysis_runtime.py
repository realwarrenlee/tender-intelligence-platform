"""Trusted context assembly and persistent model-call reservations."""
from datetime import datetime,timezone
import json
import hashlib
from zoneinfo import ZoneInfo

from app.m1.policy import DomainError


def utc_now():
    return datetime.now(timezone.utc)


class ModelLedger:
    def __init__(self,pool,job_id,workspace_id,expected_attempt=None,part_index=0):
        self.pool,self.job_id,self.workspace_id=pool,job_id,workspace_id
        self.expected_attempt=expected_attempt
        self.part_index=part_index
        self.input_sha256=None
        self.legacy_input_sha256=None
        self.requested_model=None

    def for_part(self,index):
        return ModelLedger(self.pool,self.job_id,self.workspace_id,self.expected_attempt,index)

    def bind_context(self,context,config):
        values={k:v for k,v in context.items() if k not in ('run_id','as_of')}
        values['as_of_date']=datetime.fromisoformat(context['as_of']).astimezone(ZoneInfo(context['closing_timezone'])).date().isoformat()
        digest=lambda cfg:hashlib.sha256(json.dumps({'context':values,'config':cfg},sort_keys=True).encode()).hexdigest()
        self.input_sha256=digest(config)
        self.context_values=values
        self.generation_config=config
        self.requested_model=config.get('requested_model')
        self.legacy_input_sha256=digest({k:v for k,v in config.items() if k!='requested_model'}) if self.requested_model else None

    async def history(self):
        async with self.pool.acquire() as connection:
            rows=await connection.fetch('SELECT sequence,purpose,state,result FROM m1_app.analysis_model_calls WHERE workspace_id=$1 AND job_id=$2 AND part_index=$3 ORDER BY sequence',self.workspace_id,self.job_id,self.part_index)
            if rows or not self.input_sha256:
                return [{**dict(row),'result':json.loads(row['result']) if row['result'] else None} for row in rows]
            cached=await connection.fetchrow("SELECT job_id,sequence,purpose,state,result FROM m1_app.analysis_model_calls WHERE workspace_id=$1 AND (input_sha256=$2 OR (input_sha256=$3 AND result->>'model'=$4)) AND validated AND state='completed' ORDER BY created_at DESC LIMIT 1",self.workspace_id,self.input_sha256,self.legacy_input_sha256,self.requested_model)
            if cached:
                return [{**dict(cached),'result':json.loads(cached['result']),'cached_from':str(cached['job_id'])}]
            candidates=await connection.fetch("SELECT m.job_id,m.sequence,m.purpose,m.state,m.result,m.input_sha256 FROM m1_app.analysis_model_calls m JOIN m1_app.jobs j ON j.id=m.job_id WHERE m.workspace_id=$1 AND m.part_index=$2 AND m.validated AND m.state='completed' AND j.tender_id=(SELECT tender_id FROM m1_app.jobs WHERE id=$3) AND j.input_revision=(SELECT input_revision FROM m1_app.jobs WHERE id=$3) ORDER BY m.created_at DESC LIMIT 8",self.workspace_id,self.part_index,self.job_id)
            for row in candidates:
                result=json.loads(row['result'])
                old=result.get('config') or {}
                same_model=old.get('requested_model',result.get('model'))==self.requested_model
                if not same_model or any(old.get(k)!=self.generation_config.get(k) for k in ('prompt_sha256','parser')):
                    continue
                digest=hashlib.sha256(json.dumps({'context':self.context_values,'config':old},sort_keys=True).encode()).hexdigest()
                if digest==row['input_sha256']:
                    # Schema-only changes are revalidated by analyse before any cache use.
                    return [{**dict(row),'result':result,'cached_from':str(row['job_id'])}]
            return []

    async def reserve(self,purpose):
        async with self.pool.acquire() as connection,connection.transaction():
            job=await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE workspace_id=$1 AND id=$2 FOR UPDATE',self.workspace_id,self.job_id)
            if job is None or job['status'] in ('cancelled','non_current','failed','completed','needs_input'):
                raise DomainError(409,'JOB_NOT_ACTIVE','The analysis job is no longer active.')
            if self.expected_attempt is not None and job['attempt']!=self.expected_attempt:
                raise DomainError(409,'ATTEMPT_SUPERSEDED','A newer attempt owns this analysis job.')
            if await connection.fetchval("SELECT EXISTS(SELECT 1 FROM m1_app.analysis_model_calls WHERE job_id=$1 AND part_index=$2 AND state='reserved')",self.job_id,self.part_index):
                raise DomainError(409,'MODEL_OUTCOME_UNKNOWN','An outstanding model call prevents another reservation.')
            current=await connection.fetchval('SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2',self.workspace_id,job['tender_id'])
            if current!=job['input_revision'] or (job['deadline_at'] and job['deadline_at']<=utc_now()):
                raise DomainError(409,'STALE_ANALYSIS','The pinned analysis is stale or timed out.')
            sequence=await connection.fetchval('SELECT coalesce(max(sequence),0)+1 FROM m1_app.analysis_model_calls WHERE job_id=$1',self.job_id)
            count=await connection.fetchval('SELECT count(*) FROM m1_app.analysis_model_calls WHERE job_id=$1 AND part_index=$2',self.job_id,self.part_index)
            if sequence>192 or count>=3: raise DomainError(422,'MODEL_BUDGET_EXHAUSTED','The durable model-call budget is exhausted.')
            await connection.execute("INSERT INTO m1_app.analysis_model_calls(workspace_id,job_id,sequence,purpose,state,part_index,input_sha256) VALUES($1,$2,$3,$4,'reserved',$5,$6)",self.workspace_id,self.job_id,sequence,purpose,self.part_index,self.input_sha256)
            return sequence

    async def paid_call(self,sequence):
        from app.m1.models import ActorContext
        from app.m1.usage_budget import PaidCall
        async with self.pool.acquire() as c:
            job=await c.fetchrow('SELECT tender_id,created_by FROM m1_app.jobs WHERE workspace_id=$1 AND id=$2',self.workspace_id,self.job_id)
            if job is None:
                raise DomainError(404,'NOT_FOUND','Job not found.')
        actor=ActorContext(workspace_id=self.workspace_id,user_id=job['created_by'],roles=set())
        return PaidCall(self.pool,actor,job['tender_id'],f'analysis:{self.job_id}:{sequence}',
                        job_id=self.job_id,expected_attempt=self.expected_attempt)

    async def mark_valid(self,sequence):
        async with self.pool.acquire() as connection:
            await connection.execute("UPDATE m1_app.analysis_model_calls SET validated=true WHERE workspace_id=$1 AND job_id=$2 AND sequence=$3 AND state='completed'",self.workspace_id,self.job_id,sequence)

    async def finish(self,sequence,result,state):
        async with self.pool.acquire() as connection:
            await connection.execute('UPDATE m1_app.analysis_model_calls SET state=$4,result=$5::jsonb WHERE workspace_id=$1 AND job_id=$2 AND sequence=$3',self.workspace_id,self.job_id,sequence,state,json.dumps(result) if result is not None else None)


def build_context(job,parsed):
    manifest=json.loads(job['manifest'])
    anchors={}
    documents={source['id']:source for source in manifest['documents']}
    for document in parsed['documents']:
        for anchor in document['anchors']:
            value={**anchor,'page':anchor.get('page'),'paragraph':anchor.get('paragraph'),'answer_id':None,
                   'amends_version_id':documents[document['document_version_id']].get('amends_version_id'),
                   'filename':documents[document['document_version_id']].get('filename')}
            if value['anchor_id'] in anchors: raise DomainError(422,'DUPLICATE_ANCHOR','Parsed source anchors are not unique.')
            anchors[value['anchor_id']]=value
    for answer in manifest.get('review_answers',[]):
        anchor_id=f"{answer['id']}-answer"
        anchors[anchor_id]={'anchor_id':anchor_id,'document_version_id':answer['id'],'source_role':'review_answer',
            'page':None,'paragraph':None,'answer_id':answer['id'],'actor_id':answer['actor_id'],'text':answer['text'],
            **{key:answer[key] for key in ('response_kind','task_id','requirement_ids','assessment_version_id','basis','question','source_manifest') if key in answer}}
    return {'workspace_id':str(job['workspace_id']),'tender_id':str(job['tender_id']),
        'input_revision':job['input_revision'],'source_set_id':manifest['source_set_version_id'],
        'company_evidence_version_ids':manifest.get('company_evidence_version_ids',[]),
        'review_answer_version_ids':[a['id'] for a in manifest.get('review_answers',[])],
        'source_anchors':anchors,'as_of':manifest.get('as_of',utc_now().isoformat()),
        'closing_timezone':'Asia/Singapore','routing_roles':['engineering_lead'],'schema_version':'m1.v1',
        'run_id':str(job['id']),'source_complete':parsed['complete'],
        'evidence_dates':manifest.get('evidence_dates',{}),'previous_assessment':manifest.get('previous_assessment')}
