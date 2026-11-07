"""Provider facts are exact source extracts; display values and citations are server-owned."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

from jsonschema import Draft202012Validator
import pytest

from app.tenders.policy import DomainError
from app.tenders.screening import validate_interpretation
from app.tenders.screening_workflow import ScreeningReasoner
from app.tenders.usage_budget import PaidCall
from test_screening import candidate,finding
from test_screening_summary import summary_context
from test_screening_retrieval import retrieval_case,context as native_context


def produce(monkeypatch,extracts,mutation=None):
    ctx=summary_context();index=str(uuid4());ctx['pins']['source_index_version']=index
    for excerpt in ctx['excerpts']: excerpt['source_index_version']=index
    if mutation: mutation(ctx)
    raw={**candidate(finding()),'summary':deepcopy(extracts)};captured={}
    async def provider(self,client,request,prices):
        captured.update(request)
        return SimpleNamespace(status='completed',output_text=json.dumps(raw))
    monkeypatch.setattr(PaidCall,'create_response',provider)
    reasoner=ScreeningReasoner(None,None,{'id':uuid4(),'attempt':1,'tender_id':uuid4()}, {},'controlled',object())
    return asyncio.run(reasoner.interpret(ctx,[])),ctx,captured,raw


def extracts():
    return {key:([{'anchor_id':'overview-p1','quote':'North and South campuses'}] if key=='sites' else None)
        for key in ('buyer','reference','scope','contract_period','sites')}


def test_provider_quote_becomes_the_display_value_and_its_own_exact_citation(monkeypatch):
    model=extracts();before=deepcopy(model)
    result,ctx,request,raw=produce(monkeypatch,model)
    expected={'value':'North and South campuses','citations':model['sites']}
    assert result['summary']['sites']==expected
    assert result['summary']['buyer']=={'value':None,'citations':[]}
    assert validate_interpretation(result,ctx)['summary']['sites']==expected
    assert model==before and raw['summary']==before
    assert request['max_output_tokens']==6000


def test_actual_provider_schema_has_no_populated_fact_without_a_source_quote(monkeypatch):
    _,_,request,_=produce(monkeypatch,None)
    schema=request['text']['format']['schema']
    validator=Draft202012Validator(schema)
    raw={**candidate(finding()),'summary':extracts()}
    validator.validate(raw)
    for invalid in ({'value':'Named sites','citations':[]},[],[{'quote':'Named sites'}],[{'anchor_id':'overview-p1'}]):
        value=deepcopy(raw);value['summary']['sites']=invalid
        assert list(validator.iter_errors(value))
    assert 'no separate value or citations' in request['instructions']


@pytest.mark.parametrize('mutation',['quote','anchor','role','index'])
def test_extract_normalisation_keeps_pinned_source_validation(monkeypatch,mutation):
    model=extracts()
    if mutation=='quote': model['sites'][0]['quote']='Paraphrased sites'
    if mutation=='anchor': model['sites'][0]['anchor_id']='foreign-p1'
    def change(ctx):
        if mutation=='role': ctx['excerpts'][-1]['source_role']='company_evidence'
        if mutation=='index': ctx['excerpts'][-1]['source_index_version']='old-index'
    result,ctx,_,_=produce(monkeypatch,model,change)
    with pytest.raises(DomainError) as invalid: validate_interpretation(result,ctx)
    assert invalid.value.code=='SCREENING_INVALID'


def test_unknown_summary_remains_unknown(monkeypatch):
    result,ctx,_,_=produce(monkeypatch,None)
    assert validate_interpretation(result,ctx)['summary'] is None


def test_qualifier_quotes_remain_cited_without_joining_them_into_a_display_fact(monkeypatch):
    model=extracts();qualifier={'anchor_id':'overview-p1','quote':'South Campus may commence later.'}
    model['sites'].append(qualifier)
    def append(ctx): ctx['excerpts'][-1]['quote']+=' '+qualifier['quote']
    result,ctx,_,_=produce(monkeypatch,model,append)
    assert result['summary']['sites']=={'value':'North and South campuses','citations':model['sites']}
    assert validate_interpretation(result,ctx)['summary']['sites']['citations'][1]==qualifier


def test_uncited_thousand_character_site_value_is_rejected_at_the_producer_boundary(monkeypatch):
    model=extracts();model['sites']={'value':'s'*1000,'citations':[]}
    with pytest.raises(DomainError) as invalid: produce(monkeypatch,model)
    assert invalid.value.code=='SCREENING_INVALID'


def test_quoted_provider_result_publishes_to_existing_app_and_source_reader(retrieval_case,monkeypatch):
    from app.tenders.screening_workflow import execute_screening_job
    from test_opportunities import db
    case=retrieval_case
    _,job=native_context(case,[{'filename':'instructions.pdf','text':'Critical registration is required before submission.'},
        {'filename':'overview.pdf','text':'Buyer: Fictional Agency.\nTender reference: FM-2099.\nSites: North Campus and South Campus.'}])
    payload={};requests=[]
    async def provider(self,client,request,prices):
        requests.append(request)
        return SimpleNamespace(status='completed',output_text=json.dumps(payload['raw']))
    monkeypatch.setattr(PaidCall,'create_response',provider)
    class Classifier:
        async def classify_excerpt(self,excerpt,*args):
            return {'source':excerpt,'rubric_version':'screening-v1','answers':[{'name':'kind','label':'unknown'}]}
    class Reasoner:
        async def interpret(self,ctx,hints):
            gate=next(e for e in ctx['excerpts'] if 'Critical registration' in e['quote'])
            overview=next(e for e in ctx['overview_excerpts'] if 'Fictional Agency' in e['quote'])
            facts={key:None for key in ('buyer','reference','scope','contract_period','sites')}
            for key,quote in [('buyer','Fictional Agency'),('reference','FM-2099'),('sites','North Campus and South Campus')]:
                facts[key]=[{'anchor_id':overview['anchor_id'],'quote':quote}]
            payload['raw']={**candidate(finding(status='unconfirmed',company_citations=[],
                tender_citations=[{'anchor_id':gate['anchor_id'],'quote':'Critical registration is required before submission.'}])),
                'summary':facts}
            async with case.app.state.pool.acquire() as conn:
                current_job=await conn.fetchrow('SELECT * FROM m1_app.jobs WHERE id=$1',job['id'])
            return await ScreeningReasoner(case.app.state.pool,case.actor,current_job,{},'controlled',object()).interpret(ctx,hints)
    case.http.portal.call(execute_screening_job,case.app.state.pool,case.app.state.storage,job['id'],Classifier(),Reasoner())
    review=case.http.get('/api/v1/review-cases/'+case.tender['id']).json()
    saved=review['screening']['artifact']
    assert saved['attention'] is None and saved['summary']['buyer']['value']=='Fictional Agency'
    assert saved['summary']['sites']=={'value':'North Campus and South Campus',
        'citations':payload['raw']['summary']['sites']}
    assert 'CRITICAL_CONDITION_UNRESOLVED' in saved['approval_blockers'] and len(requests)==1
    sources=case.http.get('/api/v1/assessments/'+review['screening']['id']+'/sources')
    assert sources.status_code==200 and any('North Campus' in a['text'] for a in sources.json()['anchors'])
    assert not db(case.http,case.app,'SELECT id FROM m1_app.review_tasks WHERE tender_id=$1',job['tender_id'])
