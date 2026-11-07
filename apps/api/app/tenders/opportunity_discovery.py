"""Workspace control over the fixed daily GeBIZ scan."""
from app.tenders.notice_sources import LISTING_URL
from app.tenders.policy import DomainError


async def discovery_enabled(connection, workspace_id):
    value=await connection.fetchval("""SELECT enabled FROM m1_app.opportunity_discovery_preferences
        WHERE workspace_id=$1""",workspace_id)
    return value is not False


async def discovery_settings(repository,actor,settings,command=None):
    jobs=[job for job in settings.notice_source_jobs if job.enabled and
          job.workspace_id==actor.workspace_id and job.source_url==LISTING_URL]
    configured=bool(jobs)
    async with repository.pool.acquire() as c,c.transaction():
        await repository._member(c,actor)
        roles=await c.fetchval("""SELECT roles FROM m1_app.memberships
            WHERE workspace_id=$1 AND user_id=$2""",actor.workspace_id,actor.user_id)
        can_edit=configured and ("admin" in roles or
            ("member" in roles and any(job.intake_owner_user_id==actor.user_id for job in jobs)))
        if command is not None:
            if not can_edit:
                raise DomainError(403,"FORBIDDEN","Only the intake owner or a workspace admin can change the scan.")
            await c.execute("""INSERT INTO m1_app.opportunity_discovery_preferences(workspace_id,enabled,updated_by)
                VALUES($1,$2,$3) ON CONFLICT(workspace_id) DO UPDATE
                SET enabled=EXCLUDED.enabled,updated_by=EXCLUDED.updated_by,updated_at=clock_timestamp()""",
                actor.workspace_id,command.enabled,actor.user_id)
        return {"configured":configured,"enabled":configured and await discovery_enabled(c,actor.workspace_id),
                "can_edit":can_edit}
