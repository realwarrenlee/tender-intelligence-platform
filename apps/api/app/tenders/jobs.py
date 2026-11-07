"""Durable screening and notice collection dispatch."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from uuid import UUID

import asyncpg

from app.tenders.policy import DomainError

# A fixed private installation, independent of the earlier disposable probe schemas.
os.environ['PGQUEUER_SCHEMA'] = 'm1_queue'
from pgqueuer import PgQueuer, Queries, RetryRequested

JOB_VIEW_COLUMNS = 'id,tender_id,input_revision,status,attempt,completed_stages,warnings,error_code,output_version_id'
logger = logging.getLogger(__name__)


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


async def worker():
    from app.config import get_settings
    from app.db import create_pool
    from app.tenders.storage import SourceStorage
    from app.tenders.notice_sources import LISTING_URL
    from app.tenders.opportunity_discovery import discovery_enabled
    import httpx
    connection = await asyncpg.connect(get_settings().database_url.get_secret_value(),timeout=15)
    pool = await create_pool()
    try:
        async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
            storage = SourceStorage(client)
            pgq = PgQueuer.from_asyncpg_connection(connection)

            @pgq.entrypoint('m1_screening',concurrency_limit=1)
            async def execute_screening(queued):
                from app.tenders.screening_workflow import execute_screening_job
                job_id=UUID(json.loads(queued.payload)['job_id'])
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
                settings=get_settings()
                await run_notice_collection(pool,command['source_job_key'],settings.notice_source_jobs)

            settings=get_settings()
            daily_jobs=[job for job in settings.notice_source_jobs if job.enabled and job.source_url==LISTING_URL]
            if daily_jobs:
                @pgq.schedule('m1_daily_gebiz_scan','0 0 * * *')  # UTC midnight is 08:00 in Singapore.
                async def enqueue_gebiz_scan(schedule):
                    async with pool.acquire() as c:
                        for job in daily_jobs:
                            if not await discovery_enabled(c,job.workspace_id):
                                continue
                            await queue_queries(c).enqueue(
                                'm1_collect_notice',json.dumps({'source_job_key':job.key}).encode(),
                                dedupe_key=f'gebiz:{job.key}:{datetime.now(timezone.utc).date()}',
                            )

            await pgq.run(batch_size=1,max_concurrent_tasks=2,heartbeat_timeout=timedelta(seconds=60),
                          shutdown_on_listener_failure=True)
    finally:
        await pool.close()
        await connection.close()


async def run_notice_collection(pool,source_job_key,configurations,transport=None):
    from app.tenders.models import ActorContext
    from app.tenders.notice_sources import LISTING_URL,SourcePolicy,collect_public_notice,list_public_tender_urls
    from app.tenders.opportunities import Opportunities,MATCHING_POLICY,match_notice
    from app.tenders.opportunity_discovery import discovery_enabled
    configured=[c for c in configurations if c.key==source_job_key]
    if len(configured)!=1 or not configured[0].enabled:
        raise DomainError(403,"NOTICE_JOB_NOT_CONFIGURED","Only an enabled configured source job can collect notices.")
    config=configured[0]
    actor=ActorContext(user_id=config.intake_owner_user_id,workspace_id=config.workspace_id,roles=set())
    service=Opportunities(pool)
    async with pool.acquire() as c,c.transaction():
        await service.repository._member(c,actor,"member")
        if config.source_url==LISTING_URL and not await discovery_enabled(c,actor.workspace_id):
            return {"status":"disabled"}
    try:
        if config.source_url==LISTING_URL:
            urls=await list_public_tender_urls(transport=transport)
            matched=failed=0
            for url in urls:
                try:
                    notice=await collect_public_notice(url,SourcePolicy(enabled=True,approved_urls=[url]),
                                                       transport=transport)
                except DomainError as error:
                    failed+=1
                    logger.warning("GeBIZ notice collection failed (%s): %s",error.code,url)
                    continue
                if notice.closing_at and notice.closing_at<=datetime.now(timezone.utc):
                    continue
                if match_notice(notice,MATCHING_POLICY)["relevant"]:
                    try:
                        await service.suggest_opportunity(actor,notice,MATCHING_POLICY)
                    except DomainError as error:
                        if error.code!="INTAKE_OWNER_REQUIRED":
                            raise
                        continue
                    matched+=1
            logger.info("GeBIZ scan %s: %d tenders checked, %d matches, %d fetch failures",
                        config.key,len(urls),matched,failed)
            return {"status":"partial" if failed else "collected","matched":matched,"failed":failed}
        notice=await collect_public_notice(config.source_url,SourcePolicy(enabled=True,approved_urls=[config.source_url]),
                                           transport=transport)
        result=await service.suggest_opportunity(actor,notice,MATCHING_POLICY)
        return {"status":"collected","suggestion":result}
    except DomainError as error:
        async with pool.acquire() as c,c.transaction():
            await service.repository._member(c,actor,"member")
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
