import asyncio
import hashlib

import asyncpg

from app.config import ROOT, get_settings


async def create_pool():
    return await asyncpg.create_pool(get_settings().database_url.get_secret_value(),
                                    min_size=1, max_size=4, timeout=15, command_timeout=20)


async def migrate():
    connection = await asyncpg.connect(get_settings().database_url.get_secret_value(), timeout=15)
    try:
        await connection.execute("SELECT pg_advisory_lock(hashtext('tender_m1_migrations'))")
        await connection.execute("""
            CREATE SCHEMA IF NOT EXISTS m1_app;
            CREATE TABLE IF NOT EXISTS m1_app.schema_migrations(
                name text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now());
        """)
        for path in sorted((ROOT / "supabase/migrations").glob("*_m1_*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            previous = await connection.fetchval("SELECT sha256 FROM m1_app.schema_migrations WHERE name=$1", path.name)
            if previous:
                if previous != digest:
                    raise RuntimeError("An applied migration was modified")
                continue
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute("INSERT INTO m1_app.schema_migrations(name,sha256) VALUES($1,$2)",path.name,digest)
        from app.m1.jobs import setup_queue
        await setup_queue(connection)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(migrate())
    print("M1 application migrations applied.")
