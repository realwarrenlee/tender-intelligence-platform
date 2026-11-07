"""Durable assistant turn reservation, usage and replay; no locks held during provider calls."""
import json

from app.tenders.analysis_runtime import utc_now
from app.tenders.policy import DomainError

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
