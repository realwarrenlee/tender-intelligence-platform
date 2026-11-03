import asyncio
from uuid import UUID,uuid4
import pytest
from test_documents import create,upload,PDF
from test_jobs import enqueue
from test_assessment_records import accept,FixtureModel,process


def test_mixed_pack_capacity_and_pending_inventory_are_visible(client):
    http,_,_=client
    tender=create(http)
    response=upload(http,tender,files=[(f'source{i}.pdf',PDF.read_bytes(),'application/pdf') for i in range(11)])
    assert response.status_code==201,response.text
    coverage=http.get(f"/api/v1/tenders/{tender['id']}").json()['source_coverage']
    assert coverage['total_files']==11 and coverage['pending_files']==11
    assert not coverage['complete']


def test_partial_native_text_runs_assessment_but_cannot_hide_coverage_gap(client,actors,monkeypatch):
    from app.tenders import jobs
    http,current,app=client
    current[0]=actors['admin']
    assert accept(http).status_code==201
    current[0]=actors['owner']
    tender=create(http)
    assert upload(http,tender).status_code==201
    original=jobs.parse_isolated
    async def partial(source,*args):
        result=await original(source,*args)
        if source['role']=='tender':
            result.update(status='partial',error_code='SOURCE_INCOMPLETE')
            result['locations'][0].update(status='partial',error_code='IMAGE_REQUIRES_REVIEW')
        return result
    monkeypatch.setattr(jobs,'parse_isolated',partial)
    job=enqueue(http,tender).json()
    model=FixtureModel()
    process(http,app,job['id'],model)
    detail=http.get(f"/api/v1/tenders/{tender['id']}").json()
    assert model.calls==1 and detail['assessment']['is_current']
    assert detail['source_coverage']['issues']==1
    assert detail['source_coverage']['total_files']==2
    assert detail['assessment']['candidate']['recommendation']['decision']=='hold'
    assert {'code':'SOURCE_INCOMPLETE','requirement_id':None} in detail['assessment']['blockers']
    assert http.get('/api/v1/jobs/'+job['id']).json()['error_code']=='SOURCE_INCOMPLETE'


def test_durable_part_reservations_are_independent_bounded_and_stale_safe(client):
    from app.tenders.analysis_runtime import ModelLedger
    from app.tenders.policy import DomainError
    http,current,app=client
    tender=create(http)
    assert upload(http,tender).status_code==201
    job=enqueue(http,tender).json()
    async def check():
        ledger=ModelLedger(app.state.pool,UUID(job['id']),current[0].workspace_id)
        one,two=ledger.for_part(1),ledger.for_part(2)
        # Different parts may run concurrently; the same unknown outcome cannot retry.
        first,second=await asyncio.gather(one.reserve('initial'),two.reserve('initial'))
        assert first!=second
        with pytest.raises(DomainError) as error:
            await one.reserve('initial')
        assert error.value.code=='MODEL_OUTCOME_UNKNOWN'
        await one.finish(first,{'candidate':{}},'completed')
        await two.finish(second,{'candidate':{}},'completed')
        for _ in range(2):
            sequence=await one.reserve('initial')
            await one.finish(sequence,None,'transient_failure')
        with pytest.raises(DomainError) as error:
            await one.reserve('initial')
        assert error.value.code=='MODEL_BUDGET_EXHAUSTED'
        assert len(await two.history())==1 and len(await one.history())==3
        async with app.state.pool.acquire() as connection:
            await connection.execute('UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1',UUID(tender['id']))
        with pytest.raises(DomainError) as error:
            await two.reserve('initial')
        assert error.value.code=='STALE_ANALYSIS'
    http.portal.call(check)


def test_only_validated_identical_section_inputs_are_reused(client):
    from app.tenders.analysis_runtime import ModelLedger
    from test_analysis import fixture
    import json
    http,current,app=client
    tender=create(http)
    assert upload(http,tender).status_code==201
    first=enqueue(http,tender).json()
    candidate,context=fixture()
    context.update(workspace_id=str(current[0].workspace_id),tender_id=tender['id'])
    config={'prompt_sha256':'prompt','schema_sha256':'schema','parser':'native-office-v2','requested_model':'controlled'}
    async def store():
        ledger=ModelLedger(app.state.pool,UUID(first['id']),current[0].workspace_id).for_part(1)
        ledger.bind_context(context,config)
        sequence=await ledger.reserve('initial')
        await ledger.finish(sequence,{'candidate':candidate,'config':config,'model':'controlled'},'completed')
        async with app.state.pool.acquire() as connection:
            await connection.execute("UPDATE m1_app.jobs SET status='failed' WHERE id=$1",UUID(first['id']))
        return ledger,sequence
    ledger,sequence=http.portal.call(store)
    second=enqueue(http,tender).json()
    async def inspect():
        other=ModelLedger(app.state.pool,UUID(second['id']),current[0].workspace_id).for_part(1)
        other.bind_context({**context,'run_id':'different-job'},config)
        assert await other.history()==[]  # Completed is not enough: validation must have succeeded.
        await ledger.mark_valid(sequence)
        cached=await other.history()
        assert cached[0]['cached_from']==first['id']
        other.bind_context(context,{**config,'schema_sha256':'broader-schema'})
        assert (await other.history())[0]['cached_from']==first['id']
        other.bind_context(context,{**config,'requested_model':'different-model'})
        assert await other.history()==[]
        changed={**context,'source_anchors':{**context['source_anchors'],'extra':{'text':'New obligation'}}}
        other.bind_context(changed,config)
        assert await other.history()==[]
        other.bind_context(context,{**config,'prompt_sha256':'changed'})
        assert await other.history()==[]
    http.portal.call(inspect)
