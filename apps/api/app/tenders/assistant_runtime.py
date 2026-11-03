"""Durable assistant turn reservation, usage and replay; no locks held during provider calls."""
import asyncio
import json
from uuid import UUID,uuid4

from app.tenders.analysis_runtime import utc_now
from app.tenders.assistant import OpenAIAssistant,run_assistant
from app.tenders.decisions import live_blockers,load_snapshot
from app.tenders.policy import DomainError

STALE='This snapshot is no longer current. The explanation refers only to that historical assessment. '


def mark_currency(result,current):
    result={**result,'is_current':current}
    if not current and not result['answer'].startswith(STALE): result['answer']=STALE+result['answer']
    return result


class TurnLedger:
    def __init__(self,pool,run_id,workspace_id):
        self.pool,self.id,self.workspace=pool,run_id,workspace_id

    async def reserve(self):
        async with self.pool.acquire() as c,c.transaction():
            row=await c.fetchrow('SELECT * FROM m1_app.assistant_runs WHERE workspace_id=$1 AND id=$2 FOR UPDATE',self.workspace,self.id)
            calls=json.loads(row['calls'])
            if row['status']!='running' or row['deadline_at']<=utc_now() or len(calls)>=3:
                raise DomainError(422,'ASSISTANT_BUDGET_EXHAUSTED','The durable assistant request budget is exhausted.')
            calls.append({'state':'reserved'})
            await c.execute('UPDATE m1_app.assistant_runs SET calls=$3::jsonb WHERE workspace_id=$1 AND id=$2',self.workspace,self.id,json.dumps(calls))
            return len(calls)

    async def paid_call(self,sequence):
        from app.tenders.models import ActorContext
        from app.tenders.usage_budget import PaidCall
        async with self.pool.acquire() as c:
            run=await c.fetchrow('SELECT tender_id,actor_id FROM m1_app.assistant_runs WHERE workspace_id=$1 AND id=$2',self.workspace,self.id)
            if run is None:
                raise DomainError(404,'NOT_FOUND','Assistant run not found.')
        actor=ActorContext(workspace_id=self.workspace,user_id=run['actor_id'],roles=set())
        return PaidCall(self.pool,actor,run['tender_id'],f'assistant:{self.id}:{sequence}',assistant_run_id=self.id)

    async def finish(self,sequence,response,state):
        async with self.pool.acquire() as c,c.transaction():
            calls=json.loads(await c.fetchval('SELECT calls FROM m1_app.assistant_runs WHERE workspace_id=$1 AND id=$2 FOR UPDATE',self.workspace,self.id))
            calls[sequence-1]={'state':state,'result':response}
            await c.execute('UPDATE m1_app.assistant_runs SET calls=$3::jsonb WHERE workspace_id=$1 AND id=$2',self.workspace,self.id,json.dumps(calls))


async def answer_assessment_question(repository,actor,tender_id,command,model=None):
    operation='ask_assessment:'+str(tender_id)
    async with repository.pool.acquire() as c,c.transaction():
        await repository._member(c,actor)
        replay=await repository._claim(c,actor,operation,command)
        snapshot=await load_snapshot(repository,c,actor,tender_id,command.assessment_version_id,lock=True)
        if replay:
            if 'answer' in replay: return mark_currency(replay,snapshot['is_current'])
            row=await c.fetchrow('SELECT * FROM m1_app.assistant_runs WHERE workspace_id=$1 AND id=$2',actor.workspace_id,UUID(replay['assistant_run_id']))
            if row['status']=='completed': return mark_currency(json.loads(row['response']),snapshot['is_current'])
            if row['status']=='failed': raise DomainError(422,row['error_code'],'The prior assistant turn failed; use a new request identity to try again.')
            raise DomainError(409,'ASSISTANT_IN_PROGRESS','This assistant turn is running or has an unknown outcome; a conscious new turn needs a new request identity.')
        run_id=uuid4()
        await c.execute("INSERT INTO m1_app.assistant_runs(id,workspace_id,tender_id,assessment_version_id,actor_id,status) VALUES($1,$2,$3,$4,$5,'running')",run_id,actor.workspace_id,tender_id,command.assessment_version_id,actor.user_id)
        await c.execute('UPDATE m1_app.command_requests SET response=$4::jsonb WHERE workspace_id=$1 AND user_id=$2 AND request_id=$3',actor.workspace_id,actor.user_id,command.client_request_id,json.dumps({'assistant_run_id':str(run_id)}))
        from app.tenders.reviews import list_review_tasks
        tasks=await list_review_tasks(c,actor.workspace_id,tender_id,snapshot['tender']['input_revision'],snapshot['evidence_revision'])
        payload=snapshot['payload']
        context={'question':command.text,'assessment_version_id':str(command.assessment_version_id),'is_current':snapshot['is_current'],
            'assessment':{**{key:payload[key] for key in ('candidate','requirements','reconciliation')},'blockers':live_blockers(payload,utc_now())},
            'anchors':payload['context']['source_anchors'],'routing_roles':payload['context']['routing_roles'],'tasks':tasks}
    try:
        async with asyncio.timeout(360):
            result=await run_assistant(context,model or OpenAIAssistant(),str(run_id),TurnLedger(repository.pool,run_id,actor.workspace_id))
    except (DomainError,TimeoutError) as error:
        code=error.code if isinstance(error,DomainError) else 'ASSISTANT_TIMEOUT'
        async with repository.pool.acquire() as c:
            await c.execute("UPDATE m1_app.assistant_runs SET status='failed',error_code=$3 WHERE workspace_id=$1 AND id=$2",actor.workspace_id,run_id,code)
        if isinstance(error,TimeoutError): raise DomainError(422,code,'The bounded assistant turn timed out.') from None
        raise
    async with repository.pool.acquire() as c,c.transaction():
        await repository._member(c,actor)
        snapshot=await load_snapshot(repository,c,actor,tender_id,command.assessment_version_id,lock=True)
        row=await c.fetchrow('SELECT * FROM m1_app.assistant_runs WHERE workspace_id=$1 AND id=$2 FOR UPDATE',actor.workspace_id,run_id)
        if row['status']!='running' or row['deadline_at']<=utc_now():
            raise DomainError(422,'ASSISTANT_TIMEOUT','The assistant turn is no longer active.')
        result=mark_currency(result,snapshot['is_current'])
        await c.execute("UPDATE m1_app.assistant_runs SET status='completed',response=$3::jsonb WHERE workspace_id=$1 AND id=$2",actor.workspace_id,run_id,json.dumps(result))
        return await repository._finish(c,actor,operation,command,result)
