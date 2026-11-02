"""Explicit paid T4 D1 task/answer/reassessment evaluation with fictional actors."""
import asyncio
import json

from evals.run_t3 import evaluate

if __name__=='__main__':
    try: asyncio.run(evaluate(review_workflow=True))
    except Exception as error:
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'code':getattr(error,'code',None)}))
        raise SystemExit(1)
