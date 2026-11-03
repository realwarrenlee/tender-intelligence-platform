"""Bounded read/draft tool loop; business authority is deliberately absent."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.tenders.analysis import TransientModelError
from app.tenders.citations import citation_errors,normalise_quote
from app.tenders.models import GetAssessmentInput,SearchEvidenceInput,ReviewDraftInput,AssistantText
from app.tenders.policy import DomainError

PROMPT=Path(__file__).with_name('prompts')/'assistant-v1.txt'
INPUTS={'get_assessment':GetAssessmentInput,'search_evidence':SearchEvidenceInput,'prepare_review_request':ReviewDraftInput}


def strict_schema(value):
    if isinstance(value,list): return [strict_schema(v) for v in value]
    if not isinstance(value,dict): return value
    result={k:strict_schema(v) for k,v in value.items() if k not in ('default','title')}
    if result.get('type')=='object':
        result['required']=list(result.get('properties',{}))
        result['additionalProperties']=False
    return result


def tool_definitions():
    return [{'type':'function','name':name,'description':{
        'get_assessment':'Read the pinned assessment, current indicator, blockers and tasks.',
        'search_evidence':'Search only permitted pinned source anchors; quote evidence exactly.',
        'prepare_review_request':'Validate a draft question for human confirmation; creates no task.'}[name],
        'strict':True,'parameters':strict_schema(model.model_json_schema())} for name,model in INPUTS.items()]


def search_evidence(context,arguments):
    args=SearchEvidenceInput.model_validate(arguments)
    query=normalise_quote(args.query).casefold()
    if not query: raise ValueError('Search needs a nonblank query.')
    roles={'tender':{'tender','addendum'},'company':{'company_evidence'},'review_answer':{'review_answer'}}
    found=[]
    for anchor in context['anchors'].values():
        if args.source_kind!='all' and anchor['source_role'] not in roles[args.source_kind]: continue
        text=anchor['text']
        if query not in normalise_quote(text).casefold(): continue
        # Keep an exact source excerpt; normalization is used only for matching.
        index=text.casefold().find(query)
        start=max(0,index-400) if index>=0 else 0
        found.append({**{key:anchor.get(key) for key in ('anchor_id','document_version_id','source_role','page','paragraph','answer_id','actor_id','response_kind','requirement_ids','question','assessment_version_id','source_manifest','basis')},
                      'text':text[start:start+2000]})
        if len(found)>=args.limit: break
    return found


def prepare_review_request(context,arguments):
    args=ReviewDraftInput.model_validate(arguments)
    by_ref={r['local_ref']:r for r in context['assessment']['candidate']['requirements']}
    if len(set(args.requirement_refs))!=len(args.requirement_refs) or not set(args.requirement_refs)<=set(by_ref):
        raise ValueError('Draft references unknown or duplicate current requirements.')
    if args.suggested_role not in context['routing_roles']: raise ValueError('Draft must use a configured routing role.')
    if not args.question.strip() or not args.rationale.strip(): raise ValueError('Draft question and rationale cannot be blank.')
    if not any(by_ref[key]['kind'] in ('eligibility','delivery') and by_ref[key]['status'] in ('unconfirmed','unmet') for key in args.requirement_refs):
        raise ValueError('Draft must concern an unresolved qualification finding.')
    return args.model_dump(mode='json')


async def run_assistant(context,model,run_id=None,ledger=None):
    run_id=run_id or str(uuid4())
    prompt=PROMPT.read_text()
    tools=tool_definitions()
    run={'calls':0,'tool_calls':0,'total_tokens':0,'model':None,
         'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
         'tools_sha256':hashlib.sha256(json.dumps(tools,sort_keys=True).encode()).hexdigest()}
    messages=[{'role':'user','content':json.dumps({'question':context.get('question','Explain the qualification assessment.'),
        'assessment_version_id':context['assessment_version_id'],'snapshot_is_current':context['is_current']})}]
    cache,drafts={},[]
    repaired=False
    try:
        while run['calls']<3:
            sequence=await ledger.reserve() if ledger else run['calls']+1
            run['calls']+=1
            try:
                async with asyncio.timeout(120):
                    if isinstance(model,OpenAIAssistant):
                        if ledger is None:
                            raise DomainError(422,'USAGE_BUDGET_REQUIRED','Paid assistance requires a durable turn ledger.')
                        response=await model.generate(messages,tools,strict_schema(AssistantText.model_json_schema()),prompt,paid_call=await ledger.paid_call(sequence))
                    else:
                        response=await model.generate(messages,tools,strict_schema(AssistantText.model_json_schema()),prompt)
            except (TransientModelError,TimeoutError):
                if ledger: await ledger.finish(sequence,None,'transient_failure')
                continue
            except Exception:
                if ledger: await ledger.finish(sequence,None,'failed')
                raise
            if ledger: await ledger.finish(sequence,response,'completed')
            run['model']=response['model']
            run['total_tokens']+=response.get('usage',{}).get('total_tokens',0)
            if response.get('failure_code'): raise DomainError(422,response['failure_code'],'The assistant refused or did not finish its bounded response.')
            try:
                calls=response.get('calls',[])
                if not isinstance(calls,list): raise ValueError('Malformed tool response.')
                if calls and response.get('answer') is not None: raise ValueError('Return tool calls or a final answer, not both.')
                if calls:
                    if run['tool_calls']+len(calls)>6: raise DomainError(422,'ASSISTANT_TOOL_LIMIT','The six-tool-call budget is exhausted.')
                    output=response.get('output') or [{'type':'function_call','call_id':c['id'],'name':c['name'],'arguments':json.dumps(c['arguments'])} for c in calls]
                    messages+=output
                    invalid=False
                    for call in calls:
                        run['tool_calls']+=1
                        try:
                            name=call['name']
                            if name not in INPUTS: raise ValueError('Only allowlisted read/draft tools are permitted.')
                            arguments=INPUTS[name].model_validate(call['arguments']).model_dump(mode='json')
                            key=json.dumps([name,arguments],sort_keys=True)
                            if key not in cache:
                                if name=='get_assessment':
                                    value={**deepcopy(context['assessment']),'assessment_version_id':context['assessment_version_id'],
                                           'is_current':context['is_current'],'open_tasks':[t for t in context['tasks'] if t['status']=='open']}
                                elif name=='search_evidence': value=search_evidence(context,arguments)
                                else:
                                    value={**prepare_review_request(context,arguments),'draft_ref':f'assistant-{run_id}-{len(drafts)+1}'}
                                    drafts.append(value)
                                cache[key]=value
                            value=cache[key]
                        except (ValidationError,ValueError,KeyError,TypeError):
                            invalid=True
                            value={'error':'INVALID_TOOL_ARGUMENTS','message':'Use only the allowlisted read/draft tools with valid pinned arguments.'}
                        messages.append({'type':'function_call_output','call_id':call['id'],'output':json.dumps(value)})
                    if invalid: raise ValueError('Tool validation failed.')
                    continue
                answer=AssistantText.model_validate(response.get('answer')).model_dump(mode='json')
                if answer['out_of_scope']:
                    answer.update(answer='That action is outside this assistant. I can explain the pinned assessment and prepare review questions for human confirmation.',citations=[])
                    drafts=[]
                elif not answer['citations'] or citation_errors(answer['citations'],context['anchors']):
                    raise ValueError('In-scope answers require valid exact quotes from the pinned source anchors.')
                return {**answer,'schema_version':'m1.v1','review_request_drafts':drafts,'run':run,
                        'run_id':run_id,'assessment_version_id':context['assessment_version_id'],'is_current':context['is_current']}
            except (ValidationError,ValueError,KeyError,TypeError):
                if repaired: raise DomainError(422,'ASSISTANT_INVALID','The assistant failed bounded tool or source validation.') from None
                repaired=True
                messages.append({'role':'developer','content':'Validation failed. Use only valid allowlisted arguments and exact pinned source quotes; repair once or return an out-of-scope explanation.'})
        raise DomainError(422,'ASSISTANT_BUDGET_EXHAUSTED','The three-model-request budget is exhausted.')
    except DomainError as error:
        error.run=run
        raise


class OpenAIAssistant:
    async def generate(self,messages,tools,schema,prompt,paid_call=None):
        if paid_call is None:
            raise DomainError(422,'USAGE_BUDGET_REQUIRED','Paid assistance requires an approved persistent budget.')
        from openai import AsyncOpenAI,APIConnectionError,APITimeoutError,RateLimitError,InternalServerError,APIStatusError
        from app.config import get_settings
        settings=get_settings()
        if not settings.openai_api_key or not settings.openai_model: raise DomainError(422,'MODEL_NOT_CONFIGURED','OpenAI server configuration is required.')
        try:
            async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),timeout=120,max_retries=0) as client:
                response=await paid_call.create_response(client,dict(model=settings.openai_model,instructions=prompt,input=messages,
                    tools=tools,parallel_tool_calls=True,text={'format':{'type':'json_schema','name':'assessment_answer','strict':True,'schema':schema}},
                    max_output_tokens=12000,store=False,include=['reasoning.encrypted_content'],truncation='disabled',service_tier='default'),settings.openai_prices)
        except (APIConnectionError,APITimeoutError,RateLimitError,InternalServerError): raise TransientModelError() from None
        except APIStatusError: raise DomainError(422,'MODEL_CONFIGURATION_ERROR','The assistant request was rejected; check server model access/configuration.') from None
        raw=response.model_dump(mode='json',by_alias=True,exclude_none=True)
        calls=[]
        for item in raw['output']:
            if item['type']=='function_call':
                try: arguments=json.loads(item['arguments'])
                except (ValueError,TypeError): arguments=None
                calls.append({'id':item['call_id'],'name':item['name'],'arguments':arguments})
        try: answer=json.loads(response.output_text) if response.output_text else None
        except (ValueError,TypeError): answer=None
        refused=any(content.get('type')=='refusal' for item in raw['output'] for content in item.get('content',[]))
        return {'model':response.model,'response_id':response.id,'calls':calls,'answer':answer,'output':raw['output'],
            'raw':raw,'usage':response.usage.model_dump() if response.usage else {},
            **({'failure_code':'MODEL_REFUSED'} if refused else {'failure_code':'MODEL_INCOMPLETE'} if response.status!='completed' else {})}
