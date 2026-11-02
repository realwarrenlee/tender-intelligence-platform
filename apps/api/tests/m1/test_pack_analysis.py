import asyncio
from copy import deepcopy
import pytest
from test_analysis import fixture


def test_parts_cover_every_character_repeat_company_and_preserve_parser_coverage():
    from app.m1.pack_analysis import partition_context
    _, context = fixture()
    context['source_anchors'] = {
        'company': {'anchor_id':'company','source_role':'company_evidence','text':'shared'},
        'large': {'anchor_id':'large','source_role':'tender','text':'ABCDEFGHIJK','page':1},
        'last': {'anchor_id':'last','source_role':'tender','text':'LMNOP','page':2},
    }
    parts = partition_context(context, max_chars=12)
    assert ''.join(a['text'] for p in parts for k,a in p['source_anchors'].items() if k!='company') == 'ABCDEFGHIJKLMNOP'
    assert all(p['source_anchors']['company']['text']=='shared' for p in parts)
    assert all(sum(len(a['text']) for a in p['source_anchors'].values())<=12 for p in parts)
    assert all(p['source_complete']==context['source_complete'] for p in parts)
    assert [p['analysis_part']['index'] for p in parts] == list(range(len(parts)))


def test_part_limit_fails_instead_of_dropping_text():
    from app.m1.pack_analysis import partition_context
    from app.m1.policy import DomainError
    _,context=fixture()
    context['source_anchors']={'a':{'anchor_id':'a','source_role':'tender','text':'x'*100}}
    with pytest.raises(DomainError) as error:
        partition_context(context,max_chars=2,max_parts=2)
    assert error.value.code=='ANALYSIS_PART_LIMIT'


def test_merge_deduplicates_source_identity_and_remaps_question_refs():
    from app.m1.pack_analysis import merge_candidates
    from app.m1.analysis import validate_candidate
    candidate,context=fixture()
    merged=merge_candidates([candidate,deepcopy(candidate)],context)
    result=validate_candidate(merged,context)
    assert len(result['requirements'])==len(candidate['requirements'])
    assert len({r['local_ref'] for r in merged['requirements']})==len(merged['requirements'])
    refs={r['local_ref'] for r in merged['requirements']}
    assert all(set(q['requirement_refs'])<=refs for q in merged['review_requests'])


def test_conflicting_part_facts_remain_unknown_and_block_pursuit():
    from app.m1.pack_analysis import merge_candidates
    candidate,context=fixture()
    second=deepcopy(candidate)
    second['key_facts']['closing_at']['value']='2026-12-20T16:00:00+08:00'
    merged=merge_candidates([candidate,second],context)
    assert merged['key_facts']['closing_at']['value'] is None
    assert any(w['code']=='conflicting_dates' for w in merged['warnings'])
    assert merged['recommendation']['decision']=='hold'


def test_empty_schedule_part_is_allowed_but_empty_final_assessment_is_not():
    from app.m1.analysis import validate_candidate,CandidateError
    candidate,context=fixture()
    candidate.update(requirements=[],review_requests=[])
    candidate['recommendation']['condition_refs']=[]
    context['analysis_part']={'index':0,'total':2}
    validate_candidate(candidate,context)
    context.pop('analysis_part')
    with pytest.raises(CandidateError):
        validate_candidate(candidate,context)


def test_partial_pack_can_produce_useful_assessment_with_deterministic_blocker():
    from app.m1.analysis import analyse
    candidate,context=fixture()
    context['source_complete']=False
    class Model:
        async def generate(self,*args):
            return {'candidate':candidate,'model':'controlled','usage':{}}
    result=asyncio.run(analyse(context,Model()))
    assert result['requirements']
    assert {'code':'SOURCE_INCOMPLETE','requirement_id':None} in result['blockers']
    assert result['candidate']['recommendation']['decision']=='hold'


def test_merge_never_weakens_mandatory_obligation_from_another_part():
    from app.m1.pack_analysis import merge_candidates
    candidate,context=fixture()
    first=deepcopy(candidate)
    second=deepcopy(candidate)
    first['requirements'][3]['mandatory']=False
    second['requirements'][3]['mandatory']=True
    merged=merge_candidates([first,second],context)
    target=next(r for r in merged['requirements'] if r['text']==second['requirements'][3]['text'])
    assert target['mandatory'] is True and target['status']=='unconfirmed'


def test_rate_limit_waits_within_the_existing_three_call_budget(monkeypatch):
    from app.m1 import analysis
    _,context=fixture()
    delays=[]
    async def pause(seconds):delays.append(seconds)
    monkeypatch.setattr(analysis.asyncio,'sleep',pause)
    class Model:
        calls=0
        async def generate(self,*args):
            self.calls+=1
            raise analysis.TransientModelError('rate_limit',1)
    model=Model()
    with pytest.raises(analysis.CandidateError):
        asyncio.run(analysis.analyse(context,model))
    assert model.calls==3 and delays==[1,1]


def test_transient_telemetry_is_not_replayed_as_a_completed_candidate():
    from app.m1.analysis import analyse
    candidate,context=fixture()
    class Ledger:
        async def history(self):
            return [{'state':'transient_failure','purpose':'initial','result':{'transport_error':'timeout'}}]
        async def reserve(self,purpose):return 2
        async def finish(self,*args):pass
    class Model:
        async def generate(self,*args):return {'candidate':candidate,'model':'controlled','usage':{}}
    result=asyncio.run(analyse(context,Model(),Ledger()))
    assert result['run']['calls']==2


def test_large_section_can_use_its_third_final_call_for_a_second_exact_quote_repair():
    from app.m1.analysis import analyse
    candidate,context=fixture()
    context['analysis_part']={'index':0,'total':2}
    bad=deepcopy(candidate)
    bad['requirements'][0]['tender_citations'][0]['quote']='Invented quote'
    class Model:
        calls=0
        async def generate(self,*args):
            self.calls+=1
            return {'candidate':bad if self.calls<3 else candidate,'model':'controlled','usage':{}}
    model=Model()
    result=asyncio.run(analyse(context,model))
    assert model.calls==3 and result['run']['calls']==3


def test_requested_model_is_part_of_the_checkpoint_identity(monkeypatch):
    from types import SimpleNamespace
    from app import config
    from app.m1.analysis import OpenAIModel,analyse
    from app.m1.analysis_runtime import ModelLedger
    candidate,context=fixture()
    seen=[]
    class Ledger:
        def bind_context(self,ctx,settings):
            inner=ModelLedger(None,'job','workspace')
            inner.bind_context(ctx,settings)
            seen.append((settings['requested_model'],inner.input_sha256))
        async def history(self):return []
        async def reserve(self,purpose):return 1
        async def finish(self,*args):pass
        async def paid_call(self,sequence):return None
    class Controlled(OpenAIModel):
        async def generate(self,*args,**kwargs):return {'candidate':candidate,'model':'controlled','usage':{}}
    for name in ('requested-one','requested-two'):
        monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(openai_model=name))
        asyncio.run(analyse(context,Controlled(),Ledger()))
    assert seen[0][0]=='requested-one' and seen[1][0]=='requested-two'
    assert seen[0][1]!=seen[1][1]


def test_large_pack_preserves_more_than_one_hundred_question_drafts():
    from app.m1.pack_analysis import merge_candidates
    from app.m1.analysis import validate_candidate
    candidate,context=fixture()
    base=deepcopy(candidate['review_requests'][0])
    candidate['review_requests']=[{**base,'draft_ref':f'Q{i}','question':f'Confirm capability evidence item {i}.'} for i in range(150)]
    merged=merge_candidates([candidate],context)
    assert len(merged['review_requests'])==150
    validate_candidate(merged,context)


def test_schema_compatible_checkpoint_is_revalidated_without_another_model_call():
    from app.m1.analysis import analyse
    candidate,context=fixture()
    class Model:
        async def generate(self,*args):raise AssertionError('Cache should avoid generation')
    class Ledger:
        def bind_context(self,ctx,settings):self.settings=settings
        async def history(self):
            return [{'sequence':1,'purpose':'initial','state':'completed','cached_from':'prior-job','result':{'candidate':candidate,'model':self.settings['requested_model'],'config':{**self.settings,'schema_sha256':'older-validation-bound'},'usage':{'total_tokens':99}}}]
    result=asyncio.run(analyse(context,Model(),Ledger()))
    assert result['run']['calls']==0 and result['run']['total_tokens']==0
    assert result['run']['cached_from']['job_id']=='prior-job'
