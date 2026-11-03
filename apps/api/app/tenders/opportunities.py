"""Source-backed suggestions share one tender and its existing screening budget."""
import json

from app.tenders.notice_sources import imported_snapshot
from app.tenders.policy import DomainError,assert_current_input
from app.tenders.repository import Repository

MATCHING_POLICY={"categories":["facilities management"],"terms":["integrated facilities management"]}


def match_notice(notice,policy):
    reasons=[]
    category=(notice.category or "").casefold()
    for term in policy["categories"]:
        if term.casefold() in category: reasons.append({"field":"category","term":term,"quote":notice.category})
    for term in policy["terms"]:
        if term.casefold() in notice.title.casefold(): reasons.append({"field":"title","term":term,"quote":notice.title})
    return {"method":"configured_text_rules.v1","relevant":bool(reasons),"reasons":reasons,
            "limits":["Notice relevance does not establish eligibility, attachment access or approval."]}


class Opportunities:
    def __init__(self,pool):
        self.pool=pool
        self.repository=Repository(pool)

    async def _view(self,c,row):
        notice=await c.fetchrow("SELECT * FROM m1_app.notice_versions WHERE workspace_id=$1 AND id=$2",
                               row["workspace_id"],row["current_notice_version_id"])
        budget=await c.fetchrow("""SELECT b.*,p.paused FROM m1_app.stage_budgets b
            LEFT JOIN m1_app.workspace_spending_policies p ON p.workspace_id=b.workspace_id
            WHERE b.workspace_id=$1 AND b.stage='screening' AND b.scope_key=$2""",
            row["workspace_id"],"opportunity:"+str(row["id"]))
        status="not_approved" if budget is None else "blocked" if (
            budget["paused"] is not False or budget["blocked_reason"] or budget["tender_id"]!=row["tender_id"]) else "available"
        return {"schema_version":"m1.opportunity.v1","id":str(row["id"]),"revision":row["revision"],
            "source_identity":row["source_identity"],"intake_owner_user_id":str(row["intake_owner_user_id"]),
            "state":row["state"],"notice_version_id":str(notice["id"]),"notice_version":notice["version"],
            "notice":json.loads(notice["payload"]),"match":json.loads(row["match"]),
            "tender_id":str(row["tender_id"]) if row["tender_id"] else None,
            "budget_id":str(budget["id"]) if budget else None,"budget_status":status,
            "created_at":row["created_at"].isoformat(),"last_checked_at":row["last_checked_at"].isoformat()}

    async def _suggest(self,c,actor,notice,matching_policy):
        match=match_notice(notice,matching_policy)
        await c.execute("""INSERT INTO m1_app.opportunity_suggestions
            (workspace_id,source_identity,intake_owner_user_id,match)
            VALUES($1,$2,$3,$4::jsonb) ON CONFLICT(workspace_id,source_identity) DO NOTHING""",
            actor.workspace_id,notice.source_identity,actor.user_id,json.dumps(match))
        row=await c.fetchrow("""SELECT * FROM m1_app.opportunity_suggestions
            WHERE workspace_id=$1 AND source_identity=$2 FOR UPDATE""",actor.workspace_id,notice.source_identity)
        if row["intake_owner_user_id"]!=actor.user_id:
            raise DomainError(403,"INTAKE_OWNER_REQUIRED","This source already has a different configured intake owner.")
        previous=await c.fetchrow("SELECT * FROM m1_app.notice_versions WHERE workspace_id=$1 AND id=$2",
                                 actor.workspace_id,row["current_notice_version_id"]) if row["current_notice_version_id"] else None
        if previous is None or previous["content_sha256"]!=notice.content_sha256:
            version=await c.fetchval("""INSERT INTO m1_app.notice_versions(workspace_id,suggestion_id,version,content_sha256,payload)
                VALUES($1,$2,$3,$4,$5::jsonb) RETURNING id""",actor.workspace_id,row["id"],
                previous["version"]+1 if previous else 1,notice.content_sha256,notice.model_dump_json())
            if previous and row["tender_id"]:
                tender=await c.fetchrow("SELECT * FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 FOR UPDATE",
                                       actor.workspace_id,row["tender_id"])
                if tender["deleted_at"] is None:
                    await c.execute("UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE workspace_id=$1 AND id=$2",
                                    actor.workspace_id,tender["id"])
            row=await c.fetchrow("""UPDATE m1_app.opportunity_suggestions SET current_notice_version_id=$3,
                revision=revision+$4,match=$5::jsonb,last_checked_at=clock_timestamp()
                WHERE workspace_id=$1 AND id=$2 RETURNING *""",actor.workspace_id,row["id"],version,
                1 if previous else 0,json.dumps(match))
        else:
            row=await c.fetchrow("""UPDATE m1_app.opportunity_suggestions SET last_checked_at=clock_timestamp()
                WHERE workspace_id=$1 AND id=$2 RETURNING *""",actor.workspace_id,row["id"])
        return await self._view(c,row)

    async def suggest_opportunity(self,actor_scope,notice_snapshot,matching_policy):
        async with self.pool.acquire() as c,c.transaction():
            await self.repository._member(c,actor_scope,"member")
            return await self._suggest(c,actor_scope,notice_snapshot,matching_policy)

    async def import_notice(self,actor,command):
        async with self.pool.acquire() as c,c.transaction():
            await self.repository._member(c,actor,"member")
            replay=await self.repository._claim(c,actor,"import_opportunity",command)
            if replay is not None: return replay
            result=await self._suggest(c,actor,imported_snapshot(command),MATCHING_POLICY)
            return await self.repository._finish(c,actor,"import_opportunity",command,result)

    async def list_suggestions(self,actor,state="suggested",after=None,limit=50):
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            await self.repository._member(c,actor)
            cursor=None
            if after:
                cursor=await c.fetchrow("""SELECT created_at,id FROM m1_app.opportunity_suggestions
                    WHERE workspace_id=$1 AND intake_owner_user_id=$2 AND id=$3""",actor.workspace_id,actor.user_id,after)
                if cursor is None: raise DomainError(404,"NOT_FOUND","Suggestion cursor not found.")
            rows=await c.fetch("""SELECT * FROM m1_app.opportunity_suggestions
                WHERE workspace_id=$1 AND intake_owner_user_id=$2 AND state=$3
                  AND (match->>'relevant')::boolean
                  AND ($4::timestamptz IS NULL OR (created_at,id)>($4,$5))
                ORDER BY created_at,id LIMIT $6""",actor.workspace_id,actor.user_id,state,
                cursor["created_at"] if cursor else None,cursor["id"] if cursor else None,limit+1)
            return {"schema_version":"m1.opportunity.v1","items":[await self._view(c,r) for r in rows[:limit]],
                    "next_cursor":str(rows[limit-1]["id"]) if len(rows)>limit else None}

    async def triage_suggestion(self,actor,suggestion_id,command):
        async with self.pool.acquire() as c,c.transaction():
            await self.repository._member(c,actor,"member")
            operation="triage_opportunity:"+str(suggestion_id)
            replay=await self.repository._claim(c,actor,operation,command)
            if replay is not None: return replay
            row=await c.fetchrow("""SELECT * FROM m1_app.opportunity_suggestions
                WHERE workspace_id=$1 AND id=$2 AND intake_owner_user_id=$3 FOR UPDATE""",
                actor.workspace_id,suggestion_id,actor.user_id)
            if row is None: raise DomainError(404,"NOT_FOUND","Suggestion not found.")
            if row["tender_id"]:
                tender=await self.repository._tender(c,actor,row["tender_id"],lock=True)
                if command.action!="start_assessment":
                    raise DomainError(409,"ASSESSMENT_ALREADY_STARTED","Use the linked tender to continue the active case.")
                result=await self._view(c,row)
                return await self.repository._finish(c,actor,operation,command,result)
            assert_current_input(command.expected_revision,row["revision"])
            tender_id=None
            if command.action=="start_assessment":
                notice=json.loads(await c.fetchval("SELECT payload FROM m1_app.notice_versions WHERE workspace_id=$1 AND id=$2",
                                                  actor.workspace_id,row["current_notice_version_id"]))
                tender_id=await c.fetchval("""INSERT INTO m1_app.tenders(workspace_id,title,source_label,owner_user_id)
                    VALUES($1,$2,$3,$4) RETURNING id""",actor.workspace_id,notice["title"],notice["origin"],actor.user_id)
                await c.execute("""UPDATE m1_app.stage_budgets SET tender_id=$3
                    WHERE workspace_id=$1 AND scope_key=$2 AND stage='screening' AND tender_id IS NULL""",
                    actor.workspace_id,"opportunity:"+str(row["id"]),tender_id)
            state={"start_assessment":"activated","dismiss":"dismissed"}[command.action]
            row=await c.fetchrow("""UPDATE m1_app.opportunity_suggestions SET state=$3,tender_id=$4,revision=revision+1
                WHERE workspace_id=$1 AND id=$2 RETURNING *""",actor.workspace_id,row["id"],state,tender_id)
            await c.execute("""INSERT INTO m1_app.opportunity_triage_events
                (workspace_id,suggestion_id,actor_id,action,revision,notice_version_id,tender_id)
                VALUES($1,$2,$3,$4,$5,$6,$7)""",actor.workspace_id,row["id"],actor.user_id,command.action,
                row["revision"],row["current_notice_version_id"],tender_id)
            result=await self._view(c,row)
            return await self.repository._finish(c,actor,operation,command,result)

    async def notice_for_tender(self,c,actor,tender_id):
        row=await c.fetchrow("""SELECT s.id,s.current_notice_version_id,v.version,v.payload
            FROM m1_app.opportunity_suggestions s JOIN m1_app.notice_versions v
            ON v.workspace_id=s.workspace_id AND v.id=s.current_notice_version_id
            WHERE s.workspace_id=$1 AND s.tender_id=$2 ORDER BY s.created_at,s.id LIMIT 1""",
            actor.workspace_id,tender_id)
        return {"suggestion_id":str(row["id"]),"notice_version_id":str(row["current_notice_version_id"]),
                "notice_version":row["version"],"notice":json.loads(row["payload"])} if row else None
