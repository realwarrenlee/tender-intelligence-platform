"""Authenticated browser views; no provider calls or business mutations."""
import json
from datetime import datetime
from uuid import UUID
from app.m1.policy import DomainError

from app.m1.analysis_runtime import utc_now
from app.m1.decisions import decision_view,read_decision_view


async def members(repository,actor):
    async with repository.pool.acquire() as c,c.transaction():
        await repository._member(c,actor)
        rows=await c.fetch('SELECT user_id,display_name,roles FROM m1_app.memberships WHERE workspace_id=$1 ORDER BY display_name NULLS LAST,user_id',actor.workspace_id)
        return {'schema_version':'m1.v1','items':[{'user_id':str(r['user_id']),'display_name':r['display_name'] or str(r['user_id']),'roles':r['roles']} for r in rows]}


async def sources(repository,actor,assessment_id):
    async with repository.pool.acquire() as c,c.transaction(isolation='repeatable_read'):
        await repository._member(c,actor)
        row=await c.fetchrow("""SELECT kind,tender_id,payload#>'{context,source_anchors}' AS anchors,
            payload->'findings' AS findings,payload#>'{facts,closing_at,citations}' AS closing_citations,
            manifest->>'source_index_version' AS index_id
            FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind IN ('assessment','screening')""",
            actor.workspace_id,assessment_id)
        if row is None:
            from app.m1.policy import DomainError
            raise DomainError(404,'NOT_FOUND','Assessment not found.')
        await repository._tender(c,actor,row['tender_id'])
        if row["kind"]=="assessment": anchors=list(json.loads(row["anchors"]).values())
        else:
            findings=json.loads(row["findings"])
            cited=sorted({cite["anchor_id"] for f in findings for kind in ("tender_citations","company_citations") for cite in f[kind]}
                | {cite["anchor_id"] for cite in json.loads(row["closing_citations"] or "[]")})
            native=await c.fetch("""SELECT anchor AS value FROM m1_app.source_index_versions i
                JOIN m1_app.artifact_versions p ON p.workspace_id=i.workspace_id AND p.id=i.parsed_sources_version_id,
                LATERAL jsonb_array_elements(p.payload->'documents') doc,
                LATERAL jsonb_array_elements(doc->'anchors') anchor
                WHERE i.workspace_id=$1 AND i.id=$2 AND i.tender_id=$3 AND anchor->>'anchor_id'=ANY($4::text[])""",
                actor.workspace_id,UUID(row["index_id"]) if row["index_id"] else None,row["tender_id"],cited)
            anchors=[json.loads(r["value"]) for r in native]
            answer_ids=sorted({UUID(key) for f in findings for key in f["answer_ids"]})
            answers=await c.fetch("""SELECT v.id,v.payload,a.id answer_id,a.actor_id FROM m1_app.artifact_versions v
                JOIN m1_app.review_answers a ON a.workspace_id=v.workspace_id AND a.evidence_version_id=v.id
                WHERE v.workspace_id=$1 AND v.tender_id=$2 AND v.kind='review_answer' AND v.id=ANY($3::uuid[])""",
                actor.workspace_id,row["tender_id"],answer_ids)
            for answer in answers:
                data=json.loads(answer["payload"])
                anchors.append({"anchor_id":str(answer["id"])+"-answer","document_version_id":str(answer["id"]),
                    "source_role":"review_answer","text":data["text"],"actor_id":str(answer["actor_id"]),
                    "answer_id":str(answer["answer_id"]),"question":data["question"],"response_kind":data["response_kind"],
                    "basis":data["basis"],"requirement_ids":data["finding_ids"],"source_manifest":data["source_manifest"]})
        return {'schema_version':'m1.v1','assessment_version_id':str(assessment_id),'anchors':anchors}


async def history(repository,actor,tender_id):
    async with repository.pool.acquire() as c,c.transaction(isolation='repeatable_read'):
        await repository._member(c,actor)
        tender=await repository._tender(c,actor,tender_id)
        evidence=await c.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1',actor.workspace_id)
        assessments=await c.fetch("""SELECT id,input_revision,created_at,created_by,
            jsonb_build_object('evidence_revision',coalesce(manifest->'evidence_revision','0'::jsonb)) AS manifest
            FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment'
            ORDER BY input_revision DESC,created_at DESC,id DESC""",actor.workspace_id,tender_id)
        latest=assessments[0] if assessments else None
        decisions=await c.fetch('SELECT * FROM m1_app.decisions WHERE workspace_id=$1 AND tender_id=$2 ORDER BY created_at DESC,id DESC',actor.workspace_id,tender_id)
        views=[]
        for index,row in enumerate(decisions):
            view=await read_decision_view(c,row,tender,latest,evidence,utc_now()) if not index else decision_view(row,tender,None,evidence,utc_now())
            if index: view.update(is_current=False,currency_reason='DECISION_SUPERSEDED')
            views.append(view)
        return {'schema_version':'m1.v1','assessments':[{
            'id':str(row['id']),'input_revision':row['input_revision'],'created_at':row['created_at'].isoformat(),
            'created_by':str(row['created_by']),'is_current':row['id']==latest['id']
                and row['input_revision']==tender['input_revision']
                and json.loads(row['manifest']).get('evidence_revision',0)==evidence} for row in assessments],
            'decisions':views}


def preparation_view(row,tender,evidence_revision,screening):
    if row is None: return None
    current=(row["input_revision"]==tender["input_revision"] and row["evidence_revision"]==evidence_revision
             and screening is not None and screening.get("is_current",True) and str(row["screening_version_id"])==str(screening["id"])
             and (not screening.get("approval_task_id") or str(row["approval_task_id"])==str(screening["approval_task_id"])))
    if current and row["outcome"]=="approve_preparation":
        payload=json.loads(screening["payload"]) if isinstance(screening["payload"],str) else screening["payload"]
        closing=payload.get("closing_at")
        current=bool(closing and datetime.fromisoformat(closing)>utc_now() and not payload.get("approval_blockers"))
    budget=row["preparation_budget"];conditions=row["conditions"]
    return {"id":str(row["id"]),"screening_version_id":str(row["screening_version_id"]),
        "approval_task_id":str(row["approval_task_id"]),"actor_id":str(row["actor_id"]),"outcome":row["outcome"],
        "reason":row["reason"],"preparation_scope":row["preparation_scope"],
        "preparation_budget":json.loads(budget) if isinstance(budget,str) else budget,
        "conditions":json.loads(conditions) if isinstance(conditions,str) else conditions,
        "created_at":row["created_at"].isoformat() if isinstance(row["created_at"],datetime) else row["created_at"],
        "is_current":current,"currency_reason":None if current else "INPUT_EVIDENCE_SCREENING_OR_TIME_CHANGED"}


async def _review_rows(repository,c,actor,tender_id=None,after=None,limit=50):
    cursor=None
    if after:
        cursor=await c.fetchrow("SELECT id,created_at FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 AND deleted_at IS NULL",
                               actor.workspace_id,after)
        if cursor is None: raise DomainError(404,"NOT_FOUND","Review cursor not found.")
    return await c.fetch("""
        SELECT t.*,w.evidence_revision,s.id screening_id,s.input_revision screening_revision,s.manifest screening_manifest,
        jsonb_build_object('title',s.payload->'title','closing_at',s.payload->'closing_at',
            'recommendation',s.payload->'recommendation','approval_blockers',s.payload->'approval_blockers',
            'attention',s.payload->'attention') screening_summary,
        to_jsonb(d) preparation_row,a.id current_approval_id,coalesce(q.inputs,0) open_inputs,coalesce(q.approvals,0) open_approvals,
        q.next_actor,q.can_answer,q.can_decide,j.id job_id,j.status job_status,j.error_code job_error
        FROM m1_app.tenders t JOIN m1_app.workspaces w ON w.id=t.workspace_id
        LEFT JOIN LATERAL (SELECT id,input_revision,manifest,payload FROM m1_app.artifact_versions
            WHERE workspace_id=t.workspace_id AND tender_id=t.id AND kind='screening'
            ORDER BY created_at DESC,id DESC LIMIT 1) s ON true
        LEFT JOIN LATERAL (SELECT * FROM m1_app.preparation_decisions WHERE workspace_id=t.workspace_id
            AND tender_id=t.id ORDER BY created_at DESC,id DESC LIMIT 1) d ON true
        LEFT JOIN LATERAL (SELECT id FROM m1_app.review_tasks WHERE workspace_id=t.workspace_id AND tender_id=t.id
            AND assessment_version_id=s.id AND purpose='preparation_approval'
            ORDER BY created_at DESC,id DESC LIMIT 1) a ON true
        LEFT JOIN LATERAL (SELECT count(*) FILTER(WHERE purpose!='preparation_approval') inputs,
            count(*) FILTER(WHERE purpose='preparation_approval') approvals,
            (array_agg(assignee_id ORDER BY (purpose='preparation_approval'),created_at,id))[1] next_actor,
            bool_or(assignee_id=$2 AND purpose!='preparation_approval') can_answer,
            bool_or(assignee_id=$2 AND purpose='preparation_approval') can_decide
            FROM m1_app.review_tasks WHERE workspace_id=t.workspace_id AND tender_id=t.id AND status='open'
                AND manifest->>'workflow'='screening.v1'
                AND manifest->>'source_signature'=s.manifest->>'source_signature'
                AND (manifest->>'evidence_revision')::int=w.evidence_revision
                AND (purpose!='preparation_approval' OR assessment_version_id=s.id)) q ON true
        LEFT JOIN LATERAL (SELECT id,status,error_code FROM m1_app.jobs WHERE workspace_id=t.workspace_id
            AND tender_id=t.id AND job_kind='screening' ORDER BY created_at DESC,id DESC LIMIT 1) j ON true
        WHERE t.workspace_id=$1 AND t.deleted_at IS NULL AND ($3::uuid IS NULL OR t.id=$3)
            AND ($4::timestamptz IS NULL OR (t.created_at,t.id)>($4,$5))
        ORDER BY t.created_at,t.id LIMIT $6""",actor.workspace_id,actor.user_id,tender_id,
        cursor["created_at"] if cursor else None,cursor["id"] if cursor else None,limit)


def _review_view(row,actor,roles):
    summary=json.loads(row["screening_summary"]);manifest=json.loads(row["screening_manifest"]) if row["screening_manifest"] else {}
    current=bool(row["screening_id"] and row["screening_revision"]==row["input_revision"] and manifest["evidence_revision"]==row["evidence_revision"] and str(row["job_id"])==manifest.get("screening_job_id"))
    prior=json.loads(row["preparation_row"]) if row["preparation_row"] else None
    decision=preparation_view(prior,row,row["evidence_revision"],{"id":row["screening_id"],"payload":summary,"is_current":current,"approval_task_id":str(row["current_approval_id"]) if row["current_approval_id"] else None}) if prior else None
    if row["screening_id"] and (not current or decision and not decision["is_current"]): state="Needs reassessment"
    elif decision and decision["is_current"] and decision["outcome"] in {"approve_preparation","decline"}: state="Completed"
    elif row["open_inputs"]: state="Waiting for input"
    elif current and not summary["approval_blockers"]: state="Ready for decision"
    elif row["open_approvals"]: state="Waiting for input"
    else: state="In progress"
    actions=[]
    if "bid_owner" in roles and row["owner_user_id"]==actor.user_id: actions+=["start_screening","confirm_requests"]
    if row["can_answer"] and set(roles)&{"bid_owner","service_reviewer"}: actions.append("answer_assigned_request")
    if row["can_decide"] and "approver" in roles and current: actions.append("record_preparation_decision")
    return {"schema_version":"qualification.v1","tender_id":str(row["id"]),"title":summary["title"] or row["title"],
        "owner_user_id":str(row["owner_user_id"]),"input_revision":row["input_revision"],"evidence_revision":row["evidence_revision"],
        "screening_version_id":str(row["screening_id"]) if row["screening_id"] else None,"screening_is_current":current,
        "state":state,"tender_stage":"preparing_bid" if state=="Completed" and decision["outcome"]=="approve_preparation"
            else "closed" if state=="Completed" else "assessing",
        "next_actor_id":str(row["next_actor"] or row["owner_user_id"]) if state!="Completed" else None,
        "open_inputs":row["open_inputs"],"open_approvals":row["open_approvals"],
        "recommendation":summary["recommendation"],"attention":summary["attention"] or row["job_error"],
        "closing_at":summary["closing_at"],"job_status":row["job_status"],"permitted_actions":actions,
        "preparation_decision":decision,"screening":None}


async def list_review_cases(repository,actor,after=None,limit=50):
    async with repository.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
        await repository._member(c,actor)
        roles=await c.fetchval("SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2",actor.workspace_id,actor.user_id)
        rows=await _review_rows(repository,c,actor,after=after,limit=limit+1)
        return {"schema_version":"qualification.v1","items":[_review_view(r,actor,roles) for r in rows[:limit]],
                "next_cursor":str(rows[limit-1]["id"]) if len(rows)>limit else None}


async def get_review_case(repository,actor,tender_id):
    async with repository.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
        await repository._member(c,actor)
        rows=await _review_rows(repository,c,actor,tender_id=tender_id,limit=1)
        if not rows: raise DomainError(404,"NOT_FOUND","Review case not found.")
        roles=await c.fetchval("SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2",actor.workspace_id,actor.user_id)
        result=_review_view(rows[0],actor,roles)
        if result["screening_version_id"]:
            artifact=await c.fetchrow("SELECT id,input_revision,payload FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2",
                                     actor.workspace_id,UUID(result["screening_version_id"]))
            result["screening"]={"id":str(artifact["id"]),"input_revision":artifact["input_revision"],
                "is_current":result["screening_is_current"],"artifact":json.loads(artifact["payload"])}
        return result


async def list_inbox_actions(repository,actor,after=None,limit=50):
    async with repository.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
        await repository._member(c,actor)
        roles=await c.fetchval("SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2",actor.workspace_id,actor.user_id)
        cursor=None
        if after:
            cursor=await c.fetchrow("SELECT id,created_at FROM m1_app.review_tasks WHERE workspace_id=$1 AND assignee_id=$2 AND id=$3",
                                   actor.workspace_id,actor.user_id,after)
            if cursor is None: raise DomainError(404,"NOT_FOUND","Inbox cursor not found.")
        rows=await c.fetch("""SELECT r.*,t.input_revision,w.evidence_revision,s.id latest_screening_id,
            s.input_revision screening_revision,s.manifest screening_manifest,j.id latest_job_id
            FROM m1_app.review_tasks r JOIN m1_app.tenders t ON t.workspace_id=r.workspace_id AND t.id=r.tender_id
            JOIN m1_app.workspaces w ON w.id=t.workspace_id
            LEFT JOIN LATERAL (SELECT id,input_revision,manifest FROM m1_app.artifact_versions WHERE workspace_id=t.workspace_id
                AND tender_id=t.id AND kind='screening' ORDER BY created_at DESC,id DESC LIMIT 1) s ON true
            LEFT JOIN LATERAL (SELECT id FROM m1_app.jobs WHERE workspace_id=t.workspace_id AND tender_id=t.id
                AND job_kind='screening' ORDER BY created_at DESC,id DESC LIMIT 1) j ON true
            WHERE r.workspace_id=$1 AND r.assignee_id=$2 AND r.status='open' AND t.deleted_at IS NULL
                AND r.manifest->>'workflow'='screening.v1'
                AND ($3::timestamptz IS NULL OR (r.created_at,r.id)>($3,$4))
            ORDER BY r.created_at,r.id LIMIT $5""",actor.workspace_id,actor.user_id,
            cursor["created_at"] if cursor else None,cursor["id"] if cursor else None,limit+1)
        items=[]
        for row in rows[:limit]:
            original=json.loads(row["manifest"]);latest=json.loads(row["screening_manifest"]) if row["screening_manifest"] else {}
            current=(original.get("source_signature")==latest.get("source_signature") and original["evidence_revision"]==row["evidence_revision"])
            approval=row["purpose"]=="preparation_approval"
            if approval: current&=row["assessment_version_id"]==row["latest_screening_id"] and row["screening_revision"]==row["input_revision"] and str(row["latest_job_id"])==latest.get("screening_job_id")
            authorised=bool(set(roles)&({"approver"} if approval else {"bid_owner","service_reviewer"}))
            items.append({"task_id":str(row["id"]),"tender_id":str(row["tender_id"]),"tab":"human","kind":row["purpose"],
                "screening_version_id":str(row["assessment_version_id"]),"question":row["question"],"due_at":row["due_at"].isoformat(),
                "task_revision":row["revision"],"is_current":bool(current),"can_act":bool(current and authorised)})
        return {"schema_version":"qualification.v1","items":items,
                "next_cursor":str(rows[limit-1]["id"]) if len(rows)>limit else None}
