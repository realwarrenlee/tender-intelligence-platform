"""Durable parsing and validated assessment execution."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID

import asyncpg

from app.m1.documents import build_source_set, parse_isolated
from app.m1.policy import DomainError

# A fixed private installation, independent of the earlier disposable probe schemas.
os.environ['PGQUEUER_SCHEMA'] = 'm1_queue'
from pgqueuer import PgQueuer, Queries, RetryRequested

TERMINAL = {'needs_input','failed','completed','cancelled','non_current'}
JOB_VIEW_COLUMNS = 'id,tender_id,input_revision,status,attempt,completed_stages,warnings,error_code,output_version_id'


def queue_queries(connection):
    return Queries.from_asyncpg_connection(connection)


async def setup_queue(connection):
    queries = queue_queries(connection)
    if not await queries.schema_is_installed():
        async with connection.transaction():
            await queries.install()
    await connection.execute('REVOKE ALL ON SCHEMA m1_queue FROM PUBLIC,anon,authenticated')
    await connection.execute('REVOKE ALL ON ALL TABLES IN SCHEMA m1_queue FROM PUBLIC,anon,authenticated')
    await connection.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA m1_queue FROM PUBLIC,anon,authenticated')
    await connection.execute('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA m1_queue FROM PUBLIC,anon,authenticated')
    for row in await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname='m1_queue'"):
        # Names come only from PostgreSQL's catalogue; quote identifiers explicitly.
        name = row['tablename'].replace('"','""')
        await connection.execute(f'ALTER TABLE m1_queue."{name}" ENABLE ROW LEVEL SECURITY')


def job_view(row):
    return {'schema_version':'m1.v1','id':str(row['id']),'tender_id':str(row['tender_id']),
            'input_revision':row['input_revision'],'status':row['status'],'attempt':row['attempt'],
            'completed_stages':json.loads(row['completed_stages']),'warnings':json.loads(row['warnings']),
            'error_code':row['error_code'],
            'output_version_id':str(row['output_version_id']) if row['output_version_id'] else None}


async def run_analysis_job(pool,storage,job_id,model=None):
    from app.config import get_settings
    if get_settings().qualification_workflow_enabled:
        async with pool.acquire() as c:
            await c.execute("UPDATE m1_app.jobs SET status='needs_input',error_code='BOUNDED_WORKFLOW_REQUIRED' WHERE id=$1 AND status IN ('queued','running')",job_id)
        return "needs_input"
    async with pool.acquire() as connection,connection.transaction():
        job = await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE id=$1 FOR UPDATE',job_id)
        if job is None or job['status'] in TERMINAL:
            return
        current = await connection.fetchval('SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2',job['workspace_id'],job['tender_id'])
        if current != job['input_revision']:
            await connection.execute("UPDATE m1_app.jobs SET status='non_current',error_code='STALE_INPUT' WHERE id=$1",job_id)
            return
        job = await connection.fetchrow("UPDATE m1_app.jobs SET status='running',attempt=attempt+1,deadline_at=coalesce(deadline_at,now()+interval '3600 seconds'),error_code=NULL WHERE id=$1 RETURNING *",job_id)
        await connection.execute("INSERT INTO m1_app.job_attempt_events(job_id,attempt,event) VALUES($1,$2,'started')",job_id,job['attempt'])
    manifest = json.loads(job['manifest'])
    results = []
    parsed_output = None
    failure = None
    retry = False
    assessment = None
    validation_errors = []
    model_started = False
    try:
        if job['attempt'] > 3:
            raise DomainError(422,'RETRY_LIMIT','The job exhausted its three permitted attempts.')
        remaining = (job['deadline_at']-datetime.now(timezone.utc)).total_seconds()
        async with asyncio.timeout(max(0,remaining)):
            for source in manifest['documents']:
                try:
                    data = await storage.get(source['storage_key'])
                    result = await parse_isolated(source,data,max(0.1,(job['deadline_at']-datetime.now(timezone.utc)).total_seconds()))
                    result['filename']=source['filename']
                    results.append(result)
                except DomainError as error:
                    if error.status_code == 503:
                        raise
                    results.append({'document_version_id':source['id'],'sha256':source['sha256'],
                        'source_role':source['role'],'filename':source['filename'],'status':'failed','error_code':error.code,'anchors':[],
                        'locations':[{'page':i,'status':'failed'} for i in range(1,source['page_count']+1)]})
            pack=build_source_set(results)
            async with pool.acquire() as connection,connection.transaction():
                current=await connection.fetchval('SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 FOR UPDATE',job['workspace_id'],job['tender_id'])
                latest=await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE id=$1 FOR UPDATE',job_id)
                allowed=current==job['input_revision'] and latest['status']=='running' and latest['attempt']==job['attempt']
                if allowed:
                    parsed_output=await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'parsed_sources',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",job['workspace_id'],job['tender_id'],job['input_revision'],job['manifest'],json.dumps(pack),job['created_by'])
                    await connection.execute("UPDATE m1_app.jobs SET output_version_id=$2,completed_stages='[\"source_manifest\",\"parsing\"]'::jsonb WHERE id=$1",job_id,parsed_output)
            readable=any(d['source_role'] in ('tender','addendum') and d['anchors'] for d in results)
            if allowed and readable and not pack['error_code'] and model is not None:
                from app.m1.analysis import analyse
                from app.m1.analysis_runtime import build_context,ModelLedger
                async def progress(done,total):
                    async with pool.acquire() as connection:
                        await connection.execute("UPDATE m1_app.jobs SET completed_stages=$4::jsonb WHERE id=$1 AND attempt=$2 AND status=$3",job_id,job['attempt'],'running',json.dumps(['source_manifest','parsing',f'analysis_parts:{done}/{total}']))
                model_started = True
                assessment=await analyse(build_context(job,pack),model,ModelLedger(pool,job_id,job['workspace_id'],expected_attempt=job['attempt']),progress=progress)
    except TimeoutError:
        failure = 'ANALYSIS_TIMEOUT' if model_started else 'PARSER_TIMEOUT'
    except DomainError as error:
        failure = error.code
        validation_errors = getattr(error,'errors',[])
        retry = error.status_code == 503 and job['attempt'] < 3
    except (ConnectionError,asyncpg.PostgresConnectionError):
        failure = 'DATABASE_UNAVAILABLE'
        retry = job['attempt'] < 3
    async with pool.acquire() as connection,connection.transaction():
        # Lock the tender before checking currency, serialising publication with uploads.
        current = await connection.fetchval('SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 FOR UPDATE',job['workspace_id'],job['tender_id'])
        latest = await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE id=$1 FOR UPDATE',job_id)
        if latest is None:
            return
        if latest['attempt'] != job['attempt'] or (latest['status'] in TERMINAL and latest['status'] != 'cancelled'):
            await connection.execute("INSERT INTO m1_app.job_attempt_events(job_id,attempt,event,error_code) VALUES($1,$2,'finished','ATTEMPT_SUPERSEDED')",job_id,job['attempt'])
            return latest['status']
        if parsed_output is None and latest['status']!='cancelled' and len(results)==len(manifest['documents']):
            parsed_output=await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'parsed_sources',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",job['workspace_id'],job['tender_id'],job['input_revision'],job['manifest'],json.dumps(build_source_set(results)),job['created_by'])
        if latest['status'] == 'cancelled':
            status,error,output,stages,warnings = 'cancelled','CANCELLED',None,[],[]
        elif failure:
            status,error,output,stages,warnings = ('queued' if retry else 'failed'),failure,parsed_output,['source_manifest'],[{'code':failure,'validation_errors':validation_errors}] if validation_errors else []
        else:
            pack = build_source_set(results)
            status = 'needs_input' if current == job['input_revision'] else 'non_current'
            error = ('PARSING_ONLY' if pack['complete'] else 'SOURCE_INCOMPLETE') if status=='needs_input' else 'STALE_INPUT'
            stages = ['source_manifest','parsing'] if pack['complete'] else ['source_manifest']
            warnings = [{'document_version_id':item['document_version_id'],'code':item['error_code']} for item in results if item['error_code']]
            if pack['error_code']:
                warnings.append({'code':pack['error_code']})
            output=parsed_output
            if assessment:
                output=await connection.fetchval("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING id",job['workspace_id'],job['tender_id'],job['input_revision'],job['manifest'],json.dumps(assessment),job['created_by'])
                stages+=['analysis','validation']
                status,error=('needs_input','SOURCE_INCOMPLETE') if not pack['complete'] else ('needs_input','RECONCILIATION_REQUIRED') if any(b['code']=='RECONCILIATION_REQUIRED' for b in assessment['blockers']) else ('completed',None)
        if current != job['input_revision'] and status != 'cancelled':
            status,error,retry = 'non_current','STALE_INPUT',False
        await connection.execute('UPDATE m1_app.jobs SET status=$2,error_code=$3,output_version_id=$4,completed_stages=$5::jsonb,warnings=$6::jsonb WHERE id=$1',job_id,status,error,output,json.dumps(stages),json.dumps(warnings))
        await connection.execute('INSERT INTO m1_app.job_attempt_events(job_id,attempt,event,error_code) VALUES($1,$2,$3,$4)',job_id,job['attempt'],'retry' if retry else 'finished',error)
    return status


async def execute_queued_job(pool,storage,queued,model=None):
    job_id = UUID(json.loads(queued.payload)['job_id'])
    availability_errors = (ConnectionError,TimeoutError,asyncpg.PostgresConnectionError,
                           asyncpg.CannotConnectNowError,asyncpg.TooManyConnectionsError)
    status = 'finalize_failure'
    if queued.attempts < 3:
        try:
            status = await run_analysis_job(pool,storage,job_id,model)
        except availability_errors:
            if queued.attempts < 2:
                raise RetryRequested(delay=timedelta(seconds=2),reason='Temporary business database failure') from None
    if status == 'finalize_failure':
        try:
            async with pool.acquire() as connection,connection.transaction():
                row = await connection.fetchrow("UPDATE m1_app.jobs SET status='failed',error_code=coalesce(error_code,'DATABASE_UNAVAILABLE') WHERE id=$1 AND status IN ('queued','running') RETURNING attempt,error_code",job_id)
                if row:
                    await connection.execute("INSERT INTO m1_app.job_attempt_events(job_id,attempt,event,error_code) VALUES($1,$2,'finished',$3)",job_id,row['attempt'],row['error_code'])
        except availability_errors:
            # Keep dispatch until terminal state is durable; never spend more parsing/model attempts here.
            raise RetryRequested(delay=timedelta(seconds=30),reason='Terminal job status could not yet be saved') from None
        return
    if status == 'queued':
        raise RetryRequested(delay=timedelta(seconds=2),reason='Temporary source service failure')


async def worker():
    from app.config import get_settings
    from app.db import create_pool
    from app.m1.storage import SourceStorage
    import httpx
    connection = await asyncpg.connect(get_settings().database_url.get_secret_value(),timeout=15)
    pool = await create_pool()
    try:
        async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
            storage = SourceStorage(client)
            from app.m1.analysis import OpenAIModel
            model=OpenAIModel()
            pgq = PgQueuer.from_asyncpg_connection(connection)

            @pgq.entrypoint('m1_analysis',concurrency_limit=1)
            async def execute(queued):
                await execute_queued_job(pool,storage,queued,model)

            @pgq.entrypoint('m1_screening',concurrency_limit=1)
            async def execute_screening(queued):
                from app.m1.screening_workflow import execute_screening_job
                job_id=UUID(json.loads(queued.payload)['job_id'])
                if not get_settings().qualification_workflow_enabled:
                    async with pool.acquire() as c:
                        await c.execute("UPDATE m1_app.jobs SET status='cancelled',error_code='WORKFLOW_DISABLED' WHERE id=$1 AND status IN ('queued','running')",job_id)
                    return
                try:
                    await execute_screening_job(pool,storage,job_id)
                except (ConnectionError,TimeoutError,asyncpg.PostgresConnectionError):
                    raise RetryRequested(delay=timedelta(seconds=2),reason='Recover screening state without redispatching an uncertain provider call') from None

            @pgq.entrypoint('m1_collect_notice',concurrency_limit=1)
            async def collect_notice(queued):
                if len(queued.payload)>4096:
                    raise DomainError(422,'INVALID_NOTICE_JOB','The notice job payload exceeds the supported size.')
                command=json.loads(queued.payload)
                if set(command)!={'source_job_key'}:
                    raise DomainError(422,'INVALID_NOTICE_JOB','A configured source job key is required.')
                await run_notice_collection(pool,command['source_job_key'],get_settings().notice_source_jobs)

            await pgq.run(batch_size=1,max_concurrent_tasks=2,heartbeat_timeout=timedelta(seconds=60),
                          shutdown_on_listener_failure=True)
    finally:
        await pool.close()
        await connection.close()


async def run_notice_collection(pool,source_job_key,configurations,transport=None):
    from app.m1.models import ActorContext
    from app.m1.notice_sources import SourcePolicy,collect_public_notice
    from app.m1.opportunities import Opportunities,MATCHING_POLICY
    configured=[c for c in configurations if c.key==source_job_key]
    if len(configured)!=1 or not configured[0].enabled:
        raise DomainError(403,"NOTICE_JOB_NOT_CONFIGURED","Only an enabled configured source job can collect notices.")
    config=configured[0]
    actor=ActorContext(user_id=config.intake_owner_user_id,workspace_id=config.workspace_id,roles=set())
    service=Opportunities(pool)
    async with pool.acquire() as c,c.transaction():
        await service.repository._member(c,actor,"bid_owner")
    try:
        notice=await collect_public_notice(config.source_url,SourcePolicy(enabled=True,approved_urls=[config.source_url]),
                                           transport=transport)
        result=await service.suggest_opportunity(actor,notice,MATCHING_POLICY)
        return {"status":"collected","suggestion":result}
    except DomainError as error:
        async with pool.acquire() as c,c.transaction():
            await service.repository._member(c,actor,"bid_owner")
            await c.execute("""INSERT INTO m1_app.audit_events(workspace_id,user_id,action,details)
                VALUES($1,$2,'notice_collection_failed',$3::jsonb)""",actor.workspace_id,actor.user_id,
                json.dumps({"source_job_key":config.key,"error_code":error.code,"status":"failed"}))
        return {"status":"failed","error_code":error.code}


if __name__ == '__main__':
    try:
        asyncio.run(worker())
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(json.dumps({'status':'failed','error_type':type(error).__name__}))
        raise SystemExit(1)
