"""Explicit real-Auth fictional UI accounts; cleanup is scoped to the saved run IDs."""
import asyncio
import json
import secrets
import sys
from uuid import UUID,uuid4

import httpx

from app.config import ROOT,get_settings
from app.db import create_pool
from app.provision import create_auth_user,admin_headers,save_record
from app.m1.storage import SourceStorage

PATH=ROOT/'evals/runs/local/t6-ui-accounts.json'


async def run(mode):
    pool=await create_pool()
    try:
        async with httpx.AsyncClient(timeout=60) as http,pool.acquire() as c:
            if mode=='prepare':
                if PATH.exists() or (ROOT/'evals/runs/local/t6-ui-state.json').exists():
                    raise RuntimeError('Run records already exist; clean the run and archive both accounts and UI-state files locally first.')
                assert await c.fetchval('SELECT count(*) FROM m1_queue.pgqueuer')==0,'Test queue is not empty.'
                tag=uuid4().hex[:10]
                record={'fixture_run':True,'tag':tag,'workspaces':[str(uuid4()),str(uuid4())],'accounts':{}}
                PATH.parent.mkdir(parents=True,exist_ok=True)
                save_record(PATH,record,exclusive=True)
                for role,roles in [('owner',['bid_owner','admin']),('reviewer',['service_reviewer']),('approver',['approver']),('foreign',['viewer'])]:
                    account={'email':role+'.t6.'+tag+'@example.com','password':secrets.token_urlsafe(30),
                             'workspace_id':record['workspaces'][1 if role=='foreign' else 0]}
                    record['accounts'][role]=account
                    save_record(PATH,record)
                    account['user_id']=await create_auth_user(http,account['email'],account['password'])
                    save_record(PATH,record)
                async with c.transaction():
                    for workspace in record['workspaces']:
                        await c.execute('INSERT INTO m1_app.workspaces(id,name) VALUES($1,$2)',UUID(workspace),'Fictional T6 browser qualification')
                    for role,account in record['accounts'].items():
                        roles={'owner':['bid_owner','admin'],'reviewer':['service_reviewer'],'approver':['approver'],'foreign':['viewer']}[role]
                        await c.execute('INSERT INTO m1_app.memberships(workspace_id,user_id,roles,display_name) VALUES($1,$2,$3,$4)',
                                        UUID(account['workspace_id']),UUID(account['user_id']),roles,'Fictional '+role)
                print('Four real Auth accounts and two fictional workspaces prepared; credentials stay local.')
            else:
                record=json.loads(PATH.read_text())
                assert record['fixture_run'] is True
                workspaces=[UUID(x) for x in record['workspaces']]
                if mode=='inspect':
                    report={'workspaces':record['workspaces'],'jobs':[]}
                    rows=await c.fetch('SELECT id,tender_id,status,error_code,input_revision,completed_stages FROM m1_app.jobs WHERE workspace_id=ANY($1::uuid[]) ORDER BY created_at',workspaces)
                    for row in rows:
                        calls=await c.fetch('SELECT sequence,purpose,state,result FROM m1_app.analysis_model_calls WHERE job_id=$1 ORDER BY sequence',row['id'])
                        report['jobs'].append({**{k:str(v) if isinstance(v,UUID) else v for k,v in dict(row).items()},
                            'provider_calls':[{'sequence':r['sequence'],'state':r['state'],'purpose':r['purpose'],'usage':json.loads(r['result']).get('usage',{}) if r['result'] else {}} for r in calls]})
                    documents=await c.fetch('SELECT filename,sha256,role,byte_size FROM m1_app.document_versions WHERE workspace_id=ANY($1::uuid[])',workspaces)
                    report['documents']=[dict(r) for r in documents]
                    profile=await c.fetch("SELECT payload->'document' AS document FROM m1_app.artifact_versions WHERE workspace_id=ANY($1::uuid[]) AND kind='company_evidence'",workspaces)
                    report['company_evidence']=[{k:json.loads(r['document'])[k] for k in ('filename','sha256','byte_size')} for r in profile]
                    (ROOT/'evals/runs/m1-t6-live-ledger.json').write_text(json.dumps(report,indent=2)+'\n')
                    print('Scoped live usage and input hashes recorded.')
                elif mode=='cleanup':
                    for workspace in workspaces:
                        keys=await c.fetch("SELECT storage_key FROM m1_app.document_versions WHERE workspace_id=$1 UNION SELECT payload->'document'->>'storage_key' FROM m1_app.artifact_versions WHERE workspace_id=$1 AND kind='company_evidence'",workspace)
                        owned=[r['storage_key'] for r in keys if r['storage_key'].startswith(str(workspace)+'/')]
                        if owned:
                            response=await SourceStorage(http).request('DELETE','/object/m1-sources-v1',json={'prefixes':owned})
                            assert response.status_code==200,'Scoped source cleanup failed.'
                        async with c.transaction():
                            await c.execute('DELETE FROM m1_queue.pgqueuer WHERE dedupe_key IN (SELECT id::text FROM m1_app.jobs WHERE workspace_id=$1)',workspace)
                            for table in ('assistant_runs','decisions','review_tasks'):
                                await c.execute('DELETE FROM m1_app.'+table+' WHERE workspace_id=$1',workspace)
                            await c.execute('DELETE FROM m1_app.workspaces WHERE id=$1',workspace)
                    for account in record['accounts'].values():
                        if account.get('user_id'):
                            response=await http.delete(get_settings().supabase_url.rstrip('/')+'/auth/v1/admin/users/'+account['user_id'],headers=admin_headers())
                            assert response.status_code==200,'Scoped Auth cleanup failed.'
                    record['cleaned']=True
                    save_record(PATH,record)
                    print('Only saved fictional workspace objects, jobs and Auth users removed.')
    finally:
        await pool.close()


if __name__=='__main__':
    asyncio.run(run(sys.argv[1]))
