"""Test-only worker: interrupt after a real business commit, before queue acknowledgement."""
import asyncio
from datetime import timedelta
import json
import os
import sys
from uuid import UUID

import asyncpg
import httpx

from app.config import get_settings
from app.db import create_pool
from app.m1.jobs import PgQueuer,execute_queued_job
from app.m1.storage import SourceStorage


async def main(entrypoint,crash):
    connection = await asyncpg.connect(get_settings().database_url.get_secret_value(),timeout=15)
    pool = await create_pool()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            pgq = PgQueuer.from_asyncpg_connection(connection)
            @pgq.entrypoint(entrypoint,concurrency_limit=1)
            async def execute(queued):
                await execute_queued_job(pool,SourceStorage(client),queued)
                if crash:
                    os._exit(23)
                pgq.shutdown.set()
            await asyncio.wait_for(pgq.run(batch_size=1,max_concurrent_tasks=2,
                dequeue_timeout=timedelta(milliseconds=200),heartbeat_timeout=timedelta(seconds=2),
                log_aggregation_interval=timedelta(0),shutdown_on_listener_failure=True),timeout=120)
    finally:
        await pool.close()
        await connection.close()


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1],sys.argv[2]=='crash'))
