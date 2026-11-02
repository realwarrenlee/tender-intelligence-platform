"""Version-bound Markdown exports; model prose cannot label a snapshot approved."""
import json
import re

from app.m1.analysis_runtime import utc_now
from app.m1.decisions import current_decision,live_blockers,load_snapshot


def fenced(value):
    text=json.dumps(value,indent=2,ensure_ascii=False)
    fence='`'*max(3,max((len(m.group())+1 for m in re.finditer(r'`+',text)),default=3))
    return fence+'json\n'+text+'\n'+fence


async def export_qualification_brief(repository,actor,tender_id,assessment_id):
    async with repository.pool.acquire() as connection,connection.transaction(isolation='repeatable_read'):
        await repository._member(connection,actor)
        snapshot=await load_snapshot(repository,connection,actor,tender_id,assessment_id)
        now=utc_now()
        decision=await current_decision(connection,actor.workspace_id,snapshot['tender'],snapshot['latest'],snapshot['evidence_revision'],now,assessment_id)
        if not snapshot['is_current'] or (decision and not decision['is_current']): label='NON-CURRENT'
        elif decision: label='CURRENT HUMAN DECISION'
        else: label='DRAFT — NO HUMAN DECISION'
        payload=snapshot['payload']
        references=[]
        for key,anchor in payload['context']['source_anchors'].items():
            references.append({k:anchor.get(k) for k in ('document_version_id','source_role','page','paragraph','answer_id','actor_id')}|{'anchor_id':key})
        exact={key:payload.get(key) for key in ('candidate','requirements','reconciliation','manual_corrections','human_reason','run')}
        return '\n\n'.join(['# Qualification brief',label,
            fenced({'tender_id':str(tender_id),'assessment_version_id':str(assessment_id),'input_revision':snapshot['row']['input_revision'],
                    'generated_at':now.isoformat(),'assessment_is_current':snapshot['is_current']}),
            '## Human decision',fenced(decision) if decision else 'No human decision exists for this snapshot.',
            '## Outstanding conditions',fenced(live_blockers(payload,now)),
            '## Source references',fenced(references),
            '## Exact assessment snapshot',fenced(exact)])+'\n'
