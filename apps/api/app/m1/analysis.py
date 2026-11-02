"""Strict candidate validation, conservative source identities and bounded model execution."""
import asyncio
from copy import deepcopy
from datetime import date,datetime
import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.config import ROOT
from app.m1.citations import citation_errors,normalise_quote
from app.m1.models import AnalysisCandidate
from app.m1.policy import DomainError,qualification_blockers
from app.m1.documents import PARSER_VERSION

SCHEMA=json.loads((ROOT/'contracts/qualification/analysis.schema.json').read_text())
PROMPT=Path(__file__).with_name('prompts')/'analysis-v1.txt'


class CandidateError(DomainError):
    def __init__(self,errors,run=None):
        super().__init__(422,'CANDIDATE_INVALID','The model output failed source or qualification validation.')
        self.errors=errors
        self.run=run or {}


def requirement_identity(requirement):
    clauses=sorted((cite['anchor_id'],normalise_quote(cite['quote'])) for cite in requirement['tender_citations'])
    return hashlib.sha256(json.dumps([requirement['kind'],clauses]).encode()).hexdigest()



def review_answer_errors(requirement,anchors):
    errors=[]
    for cite in requirement['company_citations']:
        answer=anchors.get(cite['anchor_id'],{})
        if answer.get('source_role')!='review_answer': continue
        kind,scope=answer.get('response_kind'),answer.get('requirement_ids')
        valid_scope=isinstance(scope,list) and 0<len(scope)<=20 and all(isinstance(key,str) and re.fullmatch(r'[0-9a-f]{64}',key) for key in scope)
        if kind not in ('confirmed','denied','unable_to_confirm') or not valid_scope:
            errors.append('Review evidence requires a valid response kind and bound requirement identities.')
            continue
        if requirement['status'] in ('met','unmet') and requirement_identity(requirement) not in scope:
            errors.append('Review evidence cannot confirm or deny a requirement outside its original scope.')
        if (requirement['status']=='met' and kind in ('denied','unable_to_confirm')) or (requirement['status']=='unmet' and kind=='unable_to_confirm'):
            errors.append('A nonconfirmation answer cannot support that definite finding.')
    return errors

def validate_candidate(candidate,context,human_correction=False):
    errors=['Schema: '+error.json_path for error in Draft202012Validator(SCHEMA).iter_errors(candidate)]
    try:
        candidate=AnalysisCandidate.model_validate(candidate).model_dump(mode='json')
    except ValidationError:
        errors.append('Candidate does not match the strict typed schema.')
    if errors: raise CandidateError(errors)
    anchors=context['source_anchors']
    refs=[r['local_ref'] for r in candidate['requirements']]
    drafts=[r['draft_ref'] for r in candidate['review_requests']]
    if len(refs)!=len(set(refs)) or len(drafts)!=len(set(drafts)): errors.append('Duplicate local requirement or draft reference.')
    if not candidate['requirements'] and not context.get('analysis_part'): errors.append('No requirements were extracted.')
    for name,fact in candidate['key_facts'].items():
        errors+=citation_errors(fact['citations'],anchors,{'tender','addendum'})
        if (fact['value'] is not None)!=bool(fact['citations']): errors.append('A fact needs a citation or an explicit null without citations.')
        if name=='closing_at' and fact['value']:
            try:
                if datetime.fromisoformat(fact['value']).utcoffset() is None: raise ValueError()
            except ValueError: errors.append('Closing timestamp needs a valid explicit UTC offset.')
        if name=='service_start_on' and fact['value']:
            try: date.fromisoformat(fact['value'])
            except ValueError: errors.append('Service start must be an ISO date.')
    for req in candidate['requirements']:
        errors+=citation_errors(req['tender_citations'],anchors,{'tender','addendum'})
        errors+=citation_errors(req['company_citations'],anchors,{'company_evidence','review_answer'})
        if req['mandatory'] and req['kind'] in ('eligibility','delivery') and req['status']=='not_assessed': errors.append('Mandatory qualification cannot be not_assessed.')
        if req['status'] in ('met','unmet') and not req['company_citations']: errors.append('Met/unmet requires supporting company evidence.')
        errors+=review_answer_errors(req,anchors)
        if req['status']=='unconfirmed' and not (req['missing_information'] or '').strip(): errors.append('Unconfirmed findings must specify missing information.')
    for draft in candidate['review_requests']:
        if not set(draft['requirement_refs'])<=set(refs): errors.append('Review draft references unknown requirements.')
        if draft['suggested_role'] not in context['routing_roles']: errors.append('Review draft invents a routing role.')
    if not set(candidate['recommendation']['condition_refs'])<=set(refs): errors.append('Recommendation references unknown requirements.')
    for warning in candidate['warnings']: errors+=citation_errors(warning['citations'],anchors)
    if errors: raise CandidateError(errors)
    previous=context.get('previous_assessment') or {}
    records=[{'id':requirement_identity(req),'requirement':req,'carried_forward':False} for req in candidate['requirements']]
    if len({r['id'] for r in records})!=len(records): raise CandidateError(['Duplicate source-clause requirement.'])
    by_id={r['id']:r for r in records}
    prior_ids={r['id'] for r in previous.get('requirements',[])}
    changes=deepcopy(previous.get('reconciliation',[]))
    def change(kind,requirement_id,old=None):
        if not any(c['kind']==kind and c.get('requirement_id')==requirement_id and not c.get('resolved') for c in changes):
            changes.append({'kind':kind,'requirement_id':requirement_id,'resolved':False,
                            **({'previous_requirement':deepcopy(old)} if old else {})})
    for old in previous.get('requirements',[]):
        current=by_id.get(old['id'])
        if not current:
            records.append({**deepcopy(old),'carried_forward':True})
            change('missing_or_changed',old['id'],old['requirement'])
        else:
            if current['requirement']['mandatory']!=old['requirement']['mandatory'] or normalise_quote(current['requirement']['text'])!=normalise_quote(old['requirement']['text']):
                change('changed',old['id'],old['requirement'])
            if not human_correction and old['requirement']['status'] in ('unconfirmed','unmet') and current['requirement']['status']=='met':
                prior_versions=set(previous.get('context',{}).get('company_evidence_version_ids',[])+previous.get('context',{}).get('review_answer_version_ids',[]))
                new_versions={anchors[c['anchor_id']]['document_version_id'] for c in current['requirement']['company_citations']}
                if not new_versions-prior_versions: errors.append('Previously unresolved qualification cannot become met from unchanged evidence.')
    if previous:
        for record in records:
            if record['id'] not in prior_ids: change('added',record['id'])
    corrections=deepcopy(previous.get('manual_corrections',[]))
    for correction in corrections:
        if correction['kind']=='requirement':
            record=next((r for r in records if r['id']==correction['id']),None)
            if record and record['requirement']!=correction['value']:
                preserved={**deepcopy(correction['value']),'local_ref':record['requirement']['local_ref']}
                if citation_errors(preserved['company_citations'],anchors,{'company_evidence','review_answer'}) or review_answer_errors(preserved,anchors):
                    preserved.update(status='unconfirmed',company_citations=[],missing_information='The human correction needs review against changed evidence.')
                record['requirement']=preserved
                for index,requirement in enumerate(candidate['requirements']):
                    if requirement_identity(requirement)==record['id']: candidate['requirements'][index]=deepcopy(preserved)
                change('manual_correction_conflict',record['id'])
        else:
            name=correction['id']
            if candidate['key_facts'][name]!=correction['value']:
                if not citation_errors(correction['value']['citations'],anchors,{'tender','addendum'}):
                    candidate['key_facts'][name]=deepcopy(correction['value'])
                if not any(c['kind']=='manual_correction_conflict' and c.get('fact_id')==name and not c.get('resolved') for c in changes):
                    changes.append({'kind':'manual_correction_conflict','requirement_id':None,'fact_id':name,'resolved':False})
    if errors: raise CandidateError(errors)
    result={'candidate':candidate,'requirements':records,'reconciliation':changes,'manual_corrections':corrections,
            'context':deepcopy(context)}
    # Do not recursively embed every earlier context in assessment history/model input.
    result['context']['previous_assessment']=None
    result['blockers']=qualification_blockers(result,datetime.fromisoformat(context['as_of']))
    if candidate['recommendation']['decision']=='pursue' and result['blockers']: raise CandidateError(['Pursue contradicts deterministic qualification/reconciliation blockers.'])
    if candidate['recommendation']['decision']=='decline' and not any(r['requirement']['mandatory'] and r['requirement']['kind'] in ('eligibility','delivery') and r['requirement']['status']=='unmet' for r in records):
        raise CandidateError(['Decline requires an evidenced mandatory qualification failure.'])
    return result


def provider_schema():
    def convert(value):
        if isinstance(value,dict): return {k:convert(v) for k,v in value.items() if k not in ('$schema','$id','uniqueItems')}
        if isinstance(value,list): return [convert(v) for v in value]
        return value
    return convert(SCHEMA)


async def analyse(context,model,ledger=None,progress=None):
    if not context.get('analysis_part'):
        from app.m1.pack_analysis import MAX_PART_CHARS,MAX_PART_ANCHORS,MAX_NARRATIVE_CHARS,analyse_pack
        narrative=sum(len(a['text']) for a in context['source_anchors'].values() if a['source_role'] not in ('company_evidence','review_answer') and not (a.get('filename') or '').lower().endswith('.xlsx'))
        if narrative>MAX_NARRATIVE_CHARS or sum(len(a['text']) for a in context['source_anchors'].values())>MAX_PART_CHARS or len(context['source_anchors'])>MAX_PART_ANCHORS:
            return await analyse_pack(context,model,ledger,progress)
    prompt=PROMPT.read_text(encoding='utf-8')
    settings_hashes={'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'schema_sha256':hashlib.sha256(json.dumps(SCHEMA,sort_keys=True).encode()).hexdigest(),'parser':PARSER_VERSION}
    settings_hashes.update(model.generation_identity() if hasattr(model,'generation_identity') else {'requested_model':type(model).__module__+'.'+type(model).__qualname__})
    if ledger and hasattr(ledger,'bind_context'): ledger.bind_context(context,settings_hashes)
    history=await ledger.history() if ledger else []
    run={'calls':sum(not h.get('cached_from') for h in history),'total_tokens':sum((h.get('result') or {}).get('usage',{}).get('total_tokens',0) for h in history if not h.get('cached_from')),
         'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'schema_sha256':hashlib.sha256(json.dumps(SCHEMA,sort_keys=True).encode()).hexdigest(),
         'parser':PARSER_VERSION,'model':None}
    run['requested_model']=settings_hashes['requested_model']
    config=settings_hashes
    if any(h['state']=='reserved' for h in history): raise CandidateError(['A prior model call has an unknown outcome; a conscious new analysis request is required.'],run)
    errors=[]
    repaired=0
    for item in history:
        if item['state']!='completed': continue
        if item.get('result'):
            if item['result'].get('failure_code'):
                error=DomainError(422,item['result']['failure_code'],'The model refused or did not finish its bounded response.')
                error.run=run
                raise error
            stored_config=item['result'].get('config')
            cache_compatible=item.get('cached_from') and isinstance(stored_config,dict) and all(stored_config.get(k)==config.get(k) for k in ('prompt_sha256','parser')) and stored_config.get('requested_model',item['result'].get('model'))==config['requested_model']
            if stored_config!=config and not cache_compatible: raise CandidateError(['The model configuration changed; request a new analysis explicitly.'],run)
            try:
                result=validate_candidate(item['result']['candidate'],context)
                run['model']=item['result']['model']
                if item.get('cached_from'): run['cached_from']={'job_id':item['cached_from'],'sequence':item['sequence']}
                return {**result,'run':run}
            except CandidateError as error:
                if item.get('cached_from'): continue
                errors=error.errors
                repaired+=int(item['purpose']=='repair')
    while run['calls']<3:
        purpose='repair' if errors else 'initial'
        if errors and repaired >= (2 if context.get('analysis_part') else 1): break
        if errors: repaired+=1
        sequence=await ledger.reserve(purpose) if ledger else run['calls']+1
        run['calls']+=1
        try:
            async with asyncio.timeout(300 if context.get('analysis_part') else 120):
                if isinstance(model,OpenAIModel):
                    if ledger is None:
                        raise DomainError(422,'USAGE_BUDGET_REQUIRED','Paid analysis requires a durable job ledger.')
                    response=await model.generate(context,provider_schema(),prompt,errors,paid_call=await ledger.paid_call(sequence))
                else:
                    response=await model.generate(context,provider_schema(),prompt,errors)
        except (TransientModelError,TimeoutError) as error:
            if ledger: await ledger.finish(sequence,{'transport_error':getattr(error,'kind','timeout')},'transient_failure')
            if run['calls']>=3: raise CandidateError(['Model transport retry budget exhausted.'],run) from None
            if purpose=='repair': repaired-=1
            if getattr(error,'kind',None)=='rate_limit': await asyncio.sleep(error.retry_after)
            continue
        except Exception:
            if ledger: await ledger.finish(sequence,None,'failed')
            raise
        response={**response,'config':config}
        if ledger: await ledger.finish(sequence,response,'completed')
        run['model']=response['model']
        run['total_tokens']+=response.get('usage',{}).get('total_tokens',0)
        if response.get('failure_code'):
            error=DomainError(422,response['failure_code'],'The model refused or did not finish its bounded response.')
            error.run=run
            raise error
        try:
            result=validate_candidate(response['candidate'],context)
            if ledger and hasattr(ledger,'mark_valid'): await ledger.mark_valid(sequence)
            return {**result,'run':run}
        except CandidateError as error: errors=error.errors
    raise CandidateError(errors or ['Model request budget exhausted.'],run)


class TransientModelError(Exception):
    def __init__(self,kind='transport',retry_after=60):
        self.kind,self.retry_after=kind,min(60,max(1,retry_after))


class OpenAIModel:
    def generation_identity(self):
        from app.config import get_settings
        return {'requested_model':get_settings().openai_model}

    async def generate(self,context,schema,prompt,errors,paid_call=None):
        if paid_call is None:
            raise DomainError(422,'USAGE_BUDGET_REQUIRED','Paid analysis requires an approved persistent budget.')
        from openai import AsyncOpenAI,APIConnectionError,APITimeoutError,RateLimitError,InternalServerError,APIStatusError
        from app.config import get_settings
        settings=get_settings()
        if not settings.openai_api_key or not settings.openai_model: raise DomainError(422,'MODEL_NOT_CONFIGURED','OpenAI server configuration is required.')
        data=deepcopy(context)
        prior=data.get('previous_assessment')
        if prior: data['previous_assessment']={k:prior.get(k) for k in ('requirements','manual_corrections')}
        try:
            async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),timeout=300 if context.get('analysis_part') else 120,max_retries=0) as client:
                response=await paid_call.create_response(client,dict(model=settings.openai_model,instructions=prompt,
                    input=json.dumps({'context':data,'validation_errors':errors}),text={'format':{'type':'json_schema','name':'m1_analysis','strict':True,'schema':schema}},
                    max_output_tokens=12000,store=False,truncation='disabled',service_tier='default'),settings.openai_prices)
        except RateLimitError as error:
            try: delay=float(error.response.headers.get('retry-after','60'))
            except (TypeError,ValueError): delay=60
            raise TransientModelError('rate_limit',delay) from None
        except (APIConnectionError,APITimeoutError,InternalServerError) as error: raise TransientModelError(type(error).__name__) from None
        except APIStatusError: raise DomainError(422,'MODEL_CONFIGURATION_ERROR','The model request was rejected; check server model access/configuration.') from None
        try: candidate=json.loads(response.output_text)
        except (ValueError,TypeError): candidate={}
        return {'candidate':candidate,'model':response.model,'response_id':response.id,
                'usage':response.usage.model_dump() if response.usage else {},'raw':response.model_dump(mode='json'),
                **({'failure_code':'MODEL_REFUSED'} if any(getattr(content,'type',None)=='refusal' for output in response.output for content in getattr(output,'content',[]))
                   else {'failure_code':'MODEL_INCOMPLETE'} if response.status!='completed' else {})}
