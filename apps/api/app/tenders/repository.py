from app.tenders.documents import MAX_FILES,MAX_PAGES,MAX_PACK
import hashlib
import json

from app.tenders.models import TenderView
from app.tenders.policy import DomainError, assert_current_input
from app.tenders.analysis_runtime import utc_now


class Repository:
    def __init__(self, pool):
        self.pool = pool

    async def _member(self, connection, actor, role=None):
        roles = await connection.fetchval(
            "SELECT roles FROM m1_app.memberships WHERE workspace_id=$1 AND user_id=$2 FOR SHARE",
            actor.workspace_id, actor.user_id,
        )
        if roles is None or (role and role not in roles and not (role == "member" and "admin" in roles)):
            raise DomainError(403, "FORBIDDEN", "Your workspace membership does not permit this action.")

    async def _tender(self, connection, actor, tender_id, lock=False):
        row = await connection.fetchrow(
            "SELECT * FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 AND deleted_at IS NULL" + (" FOR UPDATE" if lock else ""),
            actor.workspace_id, tender_id,
        )
        if row is None:
            raise DomainError(404, "NOT_FOUND", "Tender not found.")
        return row

    async def _claim(self, connection, actor, operation, command):
        digest = hashlib.sha256((operation + command.model_dump_json()).encode()).hexdigest()
        inserted = await connection.fetchval("""
            INSERT INTO m1_app.command_requests(workspace_id,user_id,request_id,request_hash)
            VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING request_id
        """, actor.workspace_id, actor.user_id, command.client_request_id, digest)
        if inserted:
            return None
        previous = await connection.fetchrow("""
            SELECT request_hash,response FROM m1_app.command_requests
            WHERE workspace_id=$1 AND user_id=$2 AND request_id=$3
        """,actor.workspace_id,actor.user_id,command.client_request_id)
        if previous["request_hash"] != digest:
            raise DomainError(409, "DUPLICATE_CONFLICT", "This request ID was used with different content.")
        return json.loads(previous["response"])

    async def _finish(self, connection, actor, operation, command, result):
        await connection.execute("""
            UPDATE m1_app.command_requests SET response=$4::jsonb
            WHERE workspace_id=$1 AND user_id=$2 AND request_id=$3
        """,actor.workspace_id,actor.user_id,command.client_request_id,json.dumps(result))
        await connection.execute("""
            INSERT INTO m1_app.audit_events(workspace_id,user_id,action,details)
            VALUES($1,$2,$3,$4::jsonb)
        """,actor.workspace_id,actor.user_id,operation,json.dumps(result))
        return result

    async def create_tender(self, actor, command):
        async with self.pool.acquire() as connection, connection.transaction():
            await self._member(connection, actor, "member")
            replay = await self._claim(connection, actor, "create_tender", command)
            if replay is not None:
                return replay
            row = await connection.fetchrow("""
                INSERT INTO m1_app.tenders(workspace_id,title,source_label,owner_user_id)
                VALUES($1,$2,$3,$4) RETURNING *
            """,actor.workspace_id,command.title,command.source_label,actor.user_id)
            result = TenderView.model_validate({key: row[key] for key in TenderView.model_fields if key in row}).model_dump(mode="json")
            return await self._finish(connection, actor, "create_tender", command, result)

    async def delete_tender(self, actor, tender_id, command):
        async with self.pool.acquire() as connection, connection.transaction():
            await self._member(connection, actor, "member")
            operation = "delete_tender:" + str(tender_id)
            replay = await self._claim(connection, actor, operation, command)
            if replay is not None:
                return replay
            tender = await self._tender(connection, actor, tender_id, lock=True)
            assert_current_input(command.expected_input_revision, tender["input_revision"])
            await connection.execute(
                "UPDATE m1_app.tenders SET deleted_at=now(),input_revision=input_revision+1 WHERE workspace_id=$1 AND id=$2",
                actor.workspace_id, tender_id,
            )
            await connection.execute(
                "UPDATE m1_app.jobs SET status='cancelled',error_code='CANCELLED' WHERE workspace_id=$1 AND tender_id=$2 AND status IN ('queued','running')",
                actor.workspace_id, tender_id,
            )
            result = {"schema_version": "m1.v1", "id": str(tender_id), "deleted": True}
            return await self._finish(connection, actor, "delete_tender", command, result)

    async def list_tenders(self,actor):
        from app.tenders.decisions import read_decision_view
        async with self.pool.acquire() as c,c.transaction(isolation='repeatable_read'):
            await self._member(c,actor)
            rows=await c.fetch("SELECT * FROM m1_app.tenders WHERE workspace_id=$1 AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100",actor.workspace_id)
            assessments=await c.fetch("""SELECT DISTINCT ON (tender_id) id,tender_id,input_revision,
                jsonb_build_object('evidence_revision',coalesce(manifest->'evidence_revision','0'::jsonb)) AS manifest,
                jsonb_build_object('candidate',(payload->'candidate') - 'requirements' - 'review_requests',
                    'blockers',payload->'blockers') AS payload
                FROM m1_app.artifact_versions WHERE workspace_id=$1 AND kind='assessment'
                ORDER BY tender_id,input_revision DESC,created_at DESC,id DESC""",actor.workspace_id)
            decisions=await c.fetch("SELECT DISTINCT ON (tender_id) * FROM m1_app.decisions WHERE workspace_id=$1 ORDER BY tender_id,created_at DESC,id DESC",actor.workspace_id)
            revision=await c.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1',actor.workspace_id)
            notice_rows=await c.fetch("""SELECT DISTINCT ON (s.tender_id) s.tender_id,
                v.payload->>'buyer' AS buyer,v.payload->>'closing_at' AS closing_at
                FROM m1_app.opportunity_suggestions s JOIN m1_app.notice_versions v
                ON v.workspace_id=s.workspace_id AND v.id=s.current_notice_version_id
                WHERE s.workspace_id=$1 AND s.tender_id=ANY($2::uuid[])
                ORDER BY s.tender_id,s.created_at,s.id""",actor.workspace_id,[r['id'] for r in rows])
            notice_facts={r['tender_id']:dict(r) for r in notice_rows}
            by_id={r['tender_id']:r for r in assessments}
            by_decision={r['tender_id']:r for r in decisions}
            items=[]
            for row in rows:
                assessment=by_id.get(row['id'])
                payload=json.loads(assessment['payload']) if assessment else None
                current=bool(assessment and assessment['input_revision']==row['input_revision'] and json.loads(assessment['manifest']).get('evidence_revision',0)==revision)
                decision=await read_decision_view(c,by_decision.get(row['id']),row,assessment,revision,utc_now())
                status='current' if current else 'non_current' if assessment else 'not_ready'
                items.append({**TenderView.model_validate({key: row[key] for key in TenderView.model_fields if key in row}).model_dump(mode='json'),
                    'title':(payload['candidate']['key_facts']['title']['value'] if payload else None) or row['title'],
                    'buyer':(payload['candidate']['key_facts']['buyer']['value'] if payload else None) or notice_facts.get(row['id'],{}).get('buyer'),
                    'closing_at':(payload['candidate']['key_facts']['closing_at']['value'] if payload else None) or notice_facts.get(row['id'],{}).get('closing_at'),
                    'recommendation':payload['candidate']['recommendation']['decision'] if payload else None,
                    'assessment_status':status,'decision':decision,
                    'next_action':'Analyse current inputs' if not current else 'Resolve qualification questions' if payload['blockers'] else 'Review and record a decision'})
            return {'schema_version':'m1.v1','items':items}

    async def get_tender(self, actor, tender_id):
        async with self.pool.acquire() as connection, connection.transaction(isolation="repeatable_read"):
            await self._member(connection, actor)
            tender = await self._tender(connection, actor, tender_id)
            documents = await connection.fetch("""
                SELECT id,filename,sha256,role,content_type,byte_size,page_count,amends_version_id,created_at FROM m1_app.document_versions
                WHERE workspace_id=$1 AND tender_id=$2 ORDER BY created_at,id
            """,actor.workspace_id,tender_id)
            from app.tenders.assessments import assessment_view,ASSESSMENT_VIEW_COLUMNS
            evidence_revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1',actor.workspace_id)
            assessment=await connection.fetchrow(f"SELECT {ASSESSMENT_VIEW_COLUMNS} FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,tender_id)
            view=assessment_view(assessment,tender['input_revision'],evidence_revision)
            from app.tenders.reviews import list_review_tasks
            from app.tenders.decisions import current_decision
            decision=await current_decision(connection,actor.workspace_id,tender,assessment,evidence_revision,utc_now())
            tasks=await list_review_tasks(connection,actor.workspace_id,tender_id,tender['input_revision'],evidence_revision)
            from app.tenders.jobs import job_view,JOB_VIEW_COLUMNS
            jobs=await connection.fetch(f'SELECT {JOB_VIEW_COLUMNS} FROM m1_app.jobs WHERE workspace_id=$1 AND tender_id=$2 ORDER BY created_at DESC,id DESC LIMIT 10',actor.workspace_id,tender_id)
            source_set=await connection.fetchval("SELECT id FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='source_set' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,tender_id)
            from app.tenders.opportunities import Opportunities
            opportunity=await Opportunities(self.pool).notice_for_tender(connection,actor,tender_id)
            bounded=opportunity is not None or await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM m1_app.jobs WHERE workspace_id=$1 AND tender_id=$2 AND job_kind='screening')",
                actor.workspace_id,tender_id)
            return {**TenderView.model_validate({key: tender[key] for key in TenderView.model_fields if key in tender}).model_dump(mode="json"),
                    "opportunity":opportunity,"workflow":"screening" if bounded else "legacy",
                    "title":(view['candidate']['key_facts']['title']['value'] if view else None) or tender['title'],
                    "documents":[dict(row) for row in documents], "source_set_version_id":str(source_set) if source_set else None, "jobs":[job_view(row) for row in jobs], "source_coverage":await self._source_coverage(connection,actor.workspace_id,tender_id,tender["input_revision"],documents), "assessment":view,
                    "assessment_status":('current' if view['is_current'] else 'non_current') if view else 'not_ready', "review_tasks":tasks, "decision":decision}

    async def _source_coverage(self,connection,workspace_id,tender_id,revision,documents):
        value=await connection.fetchval("""
            SELECT jsonb_build_object('complete',payload->'complete','documents',
                (SELECT jsonb_agg(doc - 'anchors') FROM jsonb_array_elements(payload->'documents') doc))
            FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2
                AND kind='parsed_sources' AND input_revision=$3 ORDER BY created_at DESC,id DESC LIMIT 1
        """,workspace_id,tender_id,revision)
        parsed=json.loads(value) if value else {'complete':False,'documents':[]}
        by_id={d['document_version_id']:d for d in parsed['documents']}
        rows=[{**by_id.pop(str(d['id']),{'document_version_id':str(d['id']),'status':'pending','error_code':None,'locations':[]}),
               'filename':d['filename'],'role':d['role']} for d in documents]
        rows+=list(by_id.values())
        return {'complete':bool(rows) and parsed['complete'],'documents':rows,'total_files':len(rows),
                'parsed_files':sum(d['status']!='pending' for d in rows),
                'pending_files':sum(d['status']=='pending' for d in rows),
                'issues':sum(d['status'] not in ('complete','pending') for d in rows)}

    async def register_sources(self, actor, command, uploads=None, storage=None):
        async with self.pool.acquire() as connection, connection.transaction():
            await self._member(connection, actor, "member")
            replay = await self._claim(connection, actor, "register_sources", command)
            if replay is not None:
                return replay
            tender = await self._tender(connection, actor, command.tender_id, lock=True)
            assert_current_input(command.expected_input_revision,tender["input_revision"])
            if any(source.role == "company_evidence" for source in command.sources):
                raise DomainError(403,"COMPANY_EVIDENCE_REQUIRES_ADMIN","Company evidence must use the administrator acceptance workflow.")
            existing = await connection.fetch('SELECT id,role,byte_size,page_count FROM m1_app.document_versions WHERE workspace_id=$1 AND tender_id=$2',actor.workspace_id,command.tender_id)
            if len(existing)+len(command.sources)>MAX_FILES or sum(row['byte_size'] for row in existing)+sum(s.byte_size for s in command.sources)>MAX_PACK:
                raise DomainError(422,'PACK_LIMIT','A source set allows 100 files and 100 MiB in total.')
            if sum(row['page_count'] for row in existing)+sum(s.page_count for s in command.sources)>MAX_PAGES:
                raise DomainError(422,'PAGE_LIMIT','The source set must contain at most 2000 PDF pages.')
            targets = {row['id'] for row in existing if row['role'] in ('tender','addendum')}
            for source in command.sources:
                if (source.role == 'addendum' and source.amends_version_id not in targets) or (source.role != 'addendum' and source.amends_version_id is not None):
                    raise DomainError(422,'INVALID_AMENDMENT','An addendum must identify an existing tender or addendum version in this tender.')
            if uploads is not None:
                # shortcut: rollback can leave an unreferenced object; add reconciliation before pilot retention/deletion.
                for source,data in zip(command.sources,uploads,strict=True):
                    await storage.put(source.storage_key,data,source.content_type)
            ids = []
            for source in command.sources:
                version_id = await connection.fetchval("""
                    INSERT INTO m1_app.document_versions(workspace_id,tender_id,filename,sha256,storage_key,role,content_type,byte_size,page_count,amends_version_id)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
                """,actor.workspace_id,command.tender_id,source.filename,source.sha256,source.storage_key,source.role,
                    source.content_type,source.byte_size,source.page_count,source.amends_version_id)
                ids.append(str(version_id))
            revision = await connection.fetchval("UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE workspace_id=$1 AND id=$2 RETURNING input_revision",actor.workspace_id,command.tender_id)
            current_documents = await connection.fetch("SELECT id,sha256,role FROM m1_app.document_versions WHERE workspace_id=$1 AND tender_id=$2 ORDER BY created_at,id",actor.workspace_id,command.tender_id)
            manifest = {"document_version_ids":[str(row["id"]) for row in current_documents],
                        "documents":[{"id":str(row["id"]),"sha256":row["sha256"],"role":row["role"]} for row in current_documents]}
            source_set_id = await connection.fetchval("""
                INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
                VALUES($1,$2,'source_set',$3,$4::jsonb,'{}'::jsonb,$5) RETURNING id
            """,actor.workspace_id,command.tender_id,revision,json.dumps(manifest),actor.user_id)
            result = {"schema_version":"m1.v1","document_version_ids":ids,"input_revision":revision,
                      "source_set_version_id":str(source_set_id)}
            return await self._finish(connection, actor, "register_sources", command, result)

    async def get_job(self,actor,job_id):
        from app.tenders.jobs import job_view,JOB_VIEW_COLUMNS
        async with self.pool.acquire() as connection,connection.transaction():
            await self._member(connection,actor)
            row = await connection.fetchrow(f'SELECT {JOB_VIEW_COLUMNS} FROM m1_app.jobs WHERE workspace_id=$1 AND id=$2',actor.workspace_id,job_id)
            if row is None:
                raise DomainError(404,'NOT_FOUND','Job not found.')
            await self._tender(connection,actor,row['tender_id'])
            return job_view(row)

    async def cancel_job(self,actor,job_id,command):
        from app.tenders.jobs import job_view
        async with self.pool.acquire() as connection,connection.transaction():
            await self._member(connection,actor,'member')
            replay = await self._claim(connection,actor,'cancel_job:'+str(job_id),command)
            if replay is not None:
                return replay
            row = await connection.fetchrow('SELECT * FROM m1_app.jobs WHERE workspace_id=$1 AND id=$2 FOR UPDATE',actor.workspace_id,job_id)
            if row is None:
                raise DomainError(404,'NOT_FOUND','Job not found.')
            assert_current_input(command.expected_input_revision,row['input_revision'])
            if row['status'] in ('queued','running'):
                row = await connection.fetchrow("UPDATE m1_app.jobs SET status='cancelled',error_code='CANCELLED' WHERE id=$1 RETURNING *",job_id)
            return await self._finish(connection,actor,'cancel_job',command,job_view(row))

    async def get_source(self,actor,version_id):
        async with self.pool.acquire() as connection,connection.transaction():
            await self._member(connection,actor)
            row = await connection.fetchrow('SELECT * FROM m1_app.document_versions WHERE workspace_id=$1 AND id=$2',actor.workspace_id,version_id)
            if row is None:
                payload=await connection.fetchval("SELECT payload FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind='company_evidence'",actor.workspace_id,version_id)
                if payload: return json.loads(payload)['document']
                raise DomainError(404,'NOT_FOUND','Source not found.')
            await self._tender(connection,actor,row['tender_id'])
            return dict(row)

    async def get_source_text(self,actor,version_id):
        async with self.pool.acquire() as connection,connection.transaction():
            await self._member(connection,actor)
            company=await connection.fetchval("SELECT payload FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind='company_evidence'",actor.workspace_id,version_id)
            if company: return {'schema_version':'m1.v1',**json.loads(company)['parsed']}
            rows = await connection.fetch("SELECT payload FROM m1_app.artifact_versions WHERE workspace_id=$1 AND kind='parsed_sources' AND payload @> $2::jsonb ORDER BY created_at DESC",actor.workspace_id,json.dumps({'documents':[{'document_version_id':str(version_id)}]}))
            latest,usable = None,None
            for row in rows:
                for document in json.loads(row['payload'])['documents']:
                    if document['document_version_id'] == str(version_id):
                        latest = latest or document
                        if document['status'] == 'complete' and document['anchors']:
                            return {'schema_version':'m1.v1',**document}
                        if document['anchors'] and usable is None:
                            usable = document
            if latest:
                return {'schema_version':'m1.v1',**(usable or latest)}
            raise DomainError(409,'SOURCE_NOT_PARSED','The source text view is not available until parsing finishes.')
