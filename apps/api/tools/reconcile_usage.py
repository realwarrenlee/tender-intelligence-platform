"""Preview or apply one explicitly authorized count-drift reconciliation; no provider calls."""
import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID

from app.db import create_pool
from app.tenders.models import ActorContext
from app.tenders.usage_budget import UsageBudget


async def reconcile(args):
    response=json.loads(Path(args.receipt).read_text(encoding='utf-8'))
    pool=await create_pool()
    try:
        actor=ActorContext(workspace_id=args.workspace,user_id=args.actor,roles=set())
        return await UsageBudget(pool,{}).reconcile_call(actor,args.reservation,response,args.authorized_cost,
            args.authorization_reference,args.reason,apply=args.apply)
    finally:
        await pool.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','actor','reservation'): parser.add_argument('--'+name,type=UUID,required=True)
    parser.add_argument('--receipt',required=True,help='Original confirmed provider response JSON; never truncated or edited.')
    parser.add_argument('--authorized-cost',type=Decimal,required=True)
    parser.add_argument('--authorization-reference',required=True)
    parser.add_argument('--reason',required=True)
    parser.add_argument('--apply',action='store_true',help='Apply the audited settlement; default is a read-only preview.')
    print(json.dumps(asyncio.run(reconcile(parser.parse_args())),indent=2))


if __name__=='__main__': main()
