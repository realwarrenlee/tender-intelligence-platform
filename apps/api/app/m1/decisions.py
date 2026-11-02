"""Human decisions tied to exact assessment/evidence versions and live qualification checks."""
import json
from uuid import UUID

from app.m1.analysis import review_answer_errors
from app.m1.analysis_runtime import utc_now
from app.m1.assessments import assessment_view
from app.m1.citations import citation_errors
from app.m1.policy import DomainError,assert_current_input,qualification_blockers


def live_blockers(payload,now):
    blockers=qualification_blockers(payload,now)
    anchors=payload['context']['source_anchors']
    errors=[]
    for fact in payload['candidate']['key_facts'].values():
        errors+=citation_errors(fact['citations'],anchors,{'tender','addendum'})
    for record in payload['requirements']:
        req=record['requirement']
        errors+=citation_errors(req['tender_citations'],anchors,{'tender','addendum'})
        errors+=citation_errors(req['company_citations'],anchors,{'company_evidence','review_answer'})
        errors+=review_answer_errors(req,anchors)
    if errors: blockers.append({'code':'INVALID_SOURCE_SUPPORT','requirement_id':None})
    return blockers


async def load_snapshot(repository,connection,actor,tender_id,assessment_id=None,lock=False,expected_input_revision=None):
    evidence=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1'+(' FOR SHARE' if lock else ''),actor.workspace_id)
    tender=await repository._tender(connection,actor,tender_id,lock)
    if expected_input_revision is not None: assert_current_input(expected_input_revision,tender['input_revision'])
    latest=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,tender_id)
    row=latest
    if assessment_id is not None:
        row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND id=$3 AND kind='assessment'",actor.workspace_id,tender_id,assessment_id)
        if row is None: raise DomainError(404,'NOT_FOUND','Assessment not found.')
    if row is None: raise DomainError(422,'ASSESSMENT_NOT_READY','A validated assessment is required.')
    current=bool(latest and row['id']==latest['id'] and assessment_view(row,tender['input_revision'],evidence)['is_current'])
    return {'tender':tender,'row':row,'latest':latest,'evidence_revision':evidence,'is_current':current,
        'payload':json.loads(row['payload']),'manifest':json.loads(row['manifest'])}


def decision_view(row,tender,assessment,evidence_revision,now):
    if row is None: return None
    manifest=json.loads(row['manifest'])
    current=row['input_revision']==tender['input_revision'] and manifest.get('evidence_revision',0)==evidence_revision
    reason=None if current else 'INPUT_OR_EVIDENCE_CHANGED'
    if current and (not assessment or row['assessment_version_id']!=assessment['id']):
        current,reason=False,'ASSESSMENT_CHANGED'
    if current and row['decision']=='pursue' and live_blockers(json.loads(assessment['payload']),now):
        current,reason=False,'QUALIFICATION_OR_TIME_CHANGED'
    return {'schema_version':'m1.v1',**{key:str(row[key]) for key in ('id','tender_id','assessment_version_id','actor_id')},
        **{key:row[key] for key in ('input_revision','decision','reason','review_complete')},
        'created_at':row['created_at'].isoformat(),'manifest':manifest,'is_current':current,'currency_reason':reason}


async def read_decision_view(connection,row,tender,assessment,evidence_revision,now):
    # Load private source support only when a current pursue decision needs live validation.
    if (row and row['decision']=='pursue' and assessment
            and row['assessment_version_id']==assessment['id']
            and row['input_revision']==tender['input_revision']
            and json.loads(row['manifest']).get('evidence_revision',0)==evidence_revision):
        payload=await connection.fetchval(
            "SELECT payload #- '{context,previous_assessment}' FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2",
            tender['workspace_id'],assessment['id'])
        assessment={**assessment,'payload':payload}
    return decision_view(row,tender,assessment,evidence_revision,now)


async def current_decision(connection,workspace_id,tender,assessment,evidence_revision,now,assessment_id=None):
    sql="SELECT * FROM m1_app.decisions WHERE workspace_id=$1 AND tender_id=$2"
    args=[workspace_id,tender['id']]
    if assessment_id is not None:
        sql+=' AND assessment_version_id=$3'
        args.append(assessment_id)
    row=await connection.fetchrow(sql+' ORDER BY created_at DESC,id DESC LIMIT 1',*args)
    return await read_decision_view(connection,row,tender,assessment,evidence_revision,now)


async def record_decision(repository,actor,tender_id,command):
    operation='record_decision:'+str(tender_id)
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'approver')
        replay=await repository._claim(connection,actor,operation,command)
        snapshot=await load_snapshot(repository,connection,actor,tender_id,lock=True,expected_input_revision=command.expected_input_revision if not replay else None)
        if replay:
            row=await connection.fetchrow('SELECT * FROM m1_app.decisions WHERE workspace_id=$1 AND tender_id=$2 AND id=$3',actor.workspace_id,tender_id,UUID(replay['id']))
            result=decision_view(row,snapshot['tender'],snapshot['latest'],snapshot['evidence_revision'],utc_now())
            latest=await current_decision(connection,actor.workspace_id,snapshot['tender'],snapshot['latest'],snapshot['evidence_revision'],utc_now())
            if latest['id']!=result['id']: result.update(is_current=False,currency_reason='DECISION_SUPERSEDED')
            return result
        tender,assessment=snapshot['tender'],snapshot['row']
        if assessment['id']!=command.assessment_version_id or not snapshot['is_current']:
            raise DomainError(409,'STALE_ASSESSMENT','A current exact assessment version is required for a decision.')
        now=utc_now()
        if command.decision=='pursue':
            if not command.review_complete: raise DomainError(422,'REVIEW_REQUIRED','Attest that critical facts and mandatory requirements were reviewed.')
            if live_blockers(snapshot['payload'],now): raise DomainError(422,'QUALIFICATION_BLOCKED','Resolve the current qualification, source and time blockers before pursuing.')
        sources=snapshot['manifest']
        manifest={'assessment_version_id':str(assessment['id']),'input_revision':tender['input_revision'],
            'source_set_version_id':sources['source_set_version_id'],'evidence_revision':snapshot['evidence_revision'],
            'documents':[{key:d[key] for key in ('id','sha256','role')} for d in sources.get('documents',[])],
            'company_evidence_version_ids':sources.get('company_evidence_version_ids',[]),
            'review_answer_version_ids':[a['id'] for a in sources.get('review_answers',[])]}
        row=await connection.fetchrow("""INSERT INTO m1_app.decisions(workspace_id,tender_id,assessment_version_id,input_revision,
            manifest,decision,reason,review_complete,actor_id,created_at) VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10) RETURNING *""",
            actor.workspace_id,tender_id,assessment['id'],tender['input_revision'],json.dumps(manifest),command.decision,command.reason,command.review_complete,actor.user_id,now)
        return await repository._finish(connection,actor,operation,command,decision_view(row,tender,assessment,snapshot['evidence_revision'],utc_now()))
