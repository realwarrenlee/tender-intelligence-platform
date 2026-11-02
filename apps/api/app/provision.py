"""Explicit local development account provisioning; never an HTTP/test-login endpoint."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
from uuid import UUID,uuid4

import httpx

from app.config import ROOT,get_settings
from app.db import create_pool


def admin_headers():
    key=get_settings().supabase_secret_key.get_secret_value()
    return {'apikey':key,'Authorization':'Bearer '+key}


async def create_auth_user(http,email,password):
    response=await http.post(get_settings().supabase_url.rstrip('/')+'/auth/v1/admin/users',
        headers=admin_headers(),json={'email':email,'password':password,'email_confirm':True})
    if response.status_code not in (200,201):
        raise RuntimeError('Account creation failed; check the address or existing Supabase Auth account. No password reset was attempted.')
    return response.json()['id']


def save_record(output,record,exclusive=False):
    target=output if exclusive else output.with_name(output.name+'.pending-'+secrets.token_hex(8))
    try:
        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
            stream.write(json.dumps(record,indent=2)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        if not exclusive:
            os.replace(target,output)
    finally:
        if not exclusive:
            target.unlink(missing_ok=True)


async def sign_in(http,record):
    response=await http.post(get_settings().supabase_url.rstrip('/')+'/auth/v1/token?grant_type=password',
        headers=admin_headers(),json={'email':record['email'],'password':record['password']})
    if response.status_code!=200:
        raise RuntimeError('Saved account could not sign in. Recovery credentials remain in the output file; no existing account was changed.')
    user=response.json()['user']['id']
    if record.get('user_id') and user!=record['user_id']:
        raise RuntimeError('Saved account identity does not match. No membership was changed.')
    return user


async def provision(email,output):
    # Preflight DB and persist credentials before Auth, including the ambiguous HTTP-outcome window.
    pool=await create_pool()
    try:
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists():
            record=json.loads(output.read_text())
            if record.get('email')!=email or record.get('status') not in ('prepared','auth_created','ready'):
                raise ValueError('Output already exists. Use its documented recovery record or a new output path; no account was changed.')
        else:
            record={'email':email,'password':secrets.token_urlsafe(30),'workspace_id':str(uuid4()),
                    'url':'http://127.0.0.1:3000/sign-in','status':'prepared'}
            save_record(output,record,exclusive=True)
        async with httpx.AsyncClient(timeout=30) as http:
            if record.get('user_id'):
                user=await sign_in(http,record)
            else:
                # On a retry after a lost Auth response, recover only using this generated password.
                try:
                    user=await sign_in(http,record)
                except RuntimeError:
                    user=await create_auth_user(http,email,record['password'])
            record.update(user_id=user,status='auth_created')
            save_record(output,record)
            async with pool.acquire() as c,c.transaction():
                await c.execute('INSERT INTO m1_app.workspaces(id,name) VALUES($1,$2) ON CONFLICT(id) DO NOTHING',
                                UUID(record['workspace_id']),'Development workspace')
                await c.execute('INSERT INTO m1_app.memberships(workspace_id,user_id,roles,display_name) VALUES($1,$2,$3,$4) ON CONFLICT(workspace_id,user_id) DO NOTHING',
                    UUID(record['workspace_id']),UUID(user),['bid_owner','service_reviewer','approver','admin'],email)
            await sign_in(http,record)
            record['status']='ready'
            save_record(output,record)
            print('Development account provisioned and real sign-in verified. Credentials saved locally; no email sent.')
    finally:
        await pool.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email',required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'evals/runs/local/development-sign-in.json')
    args=parser.parse_args()
    asyncio.run(provision(args.email,args.output))
