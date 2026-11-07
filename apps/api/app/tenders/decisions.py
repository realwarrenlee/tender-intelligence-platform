"""Human decisions tied to exact assessment/evidence versions and live qualification checks."""
import json

from app.tenders.analysis import review_answer_errors
from app.tenders.citations import citation_errors
from app.tenders.policy import qualification_blockers


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
