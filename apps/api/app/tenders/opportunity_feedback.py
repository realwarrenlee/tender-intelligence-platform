"""Private, notice-specific feedback requests and replies."""
import json
from uuid import UUID

from app.tenders.policy import DomainError, assert_current_input
from app.tenders.repository import Repository

SELECT_FEEDBACK = """SELECT f.*,v.payload FROM m1_app.opportunity_feedback f
    JOIN m1_app.notice_versions v ON (v.workspace_id,v.id)=(f.workspace_id,f.notice_version_id)"""


def feedback_view(row):
    return {
        "id":str(row["id"]),"sender_id":str(row["sender_id"]),"recipient_id":str(row["recipient_id"]),
        "question":row["question"],"answer":row["answer"],"notice":json.loads(row["payload"]),
        "created_at":row["created_at"].isoformat(),
        "answered_at":row["answered_at"].isoformat() if row["answered_at"] else None,
    }


class OpportunityFeedback(Repository):
    async def _feedback_row(self,c,actor,feedback_id):
        row=await c.fetchrow(SELECT_FEEDBACK+"""
            WHERE f.workspace_id=$1 AND f.id=$2 AND $3 IN (f.sender_id,f.recipient_id)""",
            actor.workspace_id,feedback_id,actor.user_id)
        if row is None:
            raise DomainError(404,"NOT_FOUND","Feedback request not found.")
        return row

    async def list_feedback(self,actor,after,limit):
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            await self._member(c,actor)
            cursor=await self._feedback_row(c,actor,after) if after else None
            rows=await c.fetch(SELECT_FEEDBACK+"""
                WHERE f.workspace_id=$1 AND $2 IN (f.sender_id,f.recipient_id)
                AND ($3::timestamptz IS NULL OR (f.created_at,f.id)<($3,$4))
                ORDER BY f.created_at DESC,f.id DESC LIMIT $5""",
                actor.workspace_id,actor.user_id,cursor["created_at"] if cursor else None,after,limit+1)
            return {"items":[feedback_view(row) for row in rows[:limit]],
                    "next_cursor":str(rows[limit-1]["id"]) if len(rows)>limit else None}

    async def request_feedback(self,actor,suggestion_id,command):
        async with self.pool.acquire() as c,c.transaction():
            await self._member(c,actor,"member")
            operation="request_opportunity_feedback:"+str(suggestion_id)
            replay=await self._claim(c,actor,operation,command)
            if replay is not None:
                return feedback_view(await self._feedback_row(c,actor,UUID(replay["id"])))
            suggestion=await c.fetchrow("""SELECT * FROM m1_app.opportunity_suggestions
                WHERE workspace_id=$1 AND id=$2 AND intake_owner_user_id=$3 FOR UPDATE""",
                actor.workspace_id,suggestion_id,actor.user_id)
            if suggestion is None:
                raise DomainError(404,"NOT_FOUND","Suggestion not found.")
            assert_current_input(command.expected_revision,suggestion["revision"])
            if suggestion["tender_id"]:
                raise DomainError(409,"ASSESSMENT_ALREADY_STARTED","Use the linked tender to request feedback.")
            recipient=await c.fetchval("""SELECT user_id FROM m1_app.memberships
                WHERE workspace_id=$1 AND user_id=$2 AND user_id<>$3 FOR SHARE""",
                actor.workspace_id,command.recipient_id,actor.user_id)
            if recipient is None:
                raise DomainError(422,"INVALID_RECIPIENT","Choose another member of your workspace.")
            feedback_id=await c.fetchval("""INSERT INTO m1_app.opportunity_feedback
                (workspace_id,suggestion_id,notice_version_id,sender_id,recipient_id,question)
                VALUES($1,$2,$3,$4,$5,$6) RETURNING id""",actor.workspace_id,suggestion_id,
                suggestion["current_notice_version_id"],actor.user_id,recipient,command.question.strip())
            await self._finish(c,actor,operation,command,{"id":str(feedback_id)})
            return feedback_view(await self._feedback_row(c,actor,feedback_id))

    async def answer_feedback(self,actor,feedback_id,command):
        async with self.pool.acquire() as c,c.transaction():
            await self._member(c,actor)
            operation="answer_opportunity_feedback:"+str(feedback_id)
            replay=await self._claim(c,actor,operation,command)
            row=await self._feedback_row(c,actor,feedback_id)
            if row["recipient_id"]!=actor.user_id:
                raise DomainError(404,"NOT_FOUND","Feedback request not found.")
            if replay is None:
                updated=await c.fetchval("""UPDATE m1_app.opportunity_feedback
                    SET answer=$3,answered_at=clock_timestamp()
                    WHERE workspace_id=$1 AND id=$2 AND answered_at IS NULL RETURNING id""",
                    actor.workspace_id,feedback_id,command.answer.strip())
                if updated is None:
                    raise DomainError(409,"FEEDBACK_ALREADY_ANSWERED","This request already has a reply.")
                await self._finish(c,actor,operation,command,{"id":str(feedback_id)})
                row=await self._feedback_row(c,actor,feedback_id)
            return feedback_view(row)
