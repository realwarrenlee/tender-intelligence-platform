"""Explicit paid T5 D1 assistant/decision/export evaluation; fictional actors only."""
import asyncio
import json

from evals.run_t3 import evaluate

if __name__=='__main__':
    try: asyncio.run(evaluate(t5_workflow=True))
    except Exception as error:
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'code':getattr(error,'code',None)}))
        raise SystemExit(1)
