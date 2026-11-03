"""Real ledger regressions for count drift; provider transport remains controlled."""
import asyncio
import hashlib
from decimal import Decimal
from functools import partial
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.tenders.policy import DomainError
from app.tenders.usage_budget import PaidCall
from test_stage_budget import budget_case,usage,reserve,limits


class CountDriftClient:
    def __init__(self,delta=1):
        self.responses=self;self.input_tokens=self;self.created=0;self.delta=delta

    async def count(self,**request): return SimpleNamespace(input_tokens=14778)

    async def create(self,**request):
        self.created+=1
        return SimpleNamespace(id='response-drift',model='controlled-model',status='incomplete',
            usage=SimpleNamespace(model_dump=lambda: usage(14778+self.delta,6000)))


def test_one_token_drift_is_reserved_in_advance_and_billed_even_for_incomplete_content(budget_case):
    c=budget_case;transport=CountDriftClient()
    paid=PaidCall(c.app.state.pool,c.actor,UUID(c.tender['id']),'drift')
    response=c.http.portal.call(paid.create_response,transport,
        {'model':'controlled-model','input':'Controlled','max_output_tokens':6000},c.prices)
    assert response.status=='incomplete'
    async def inspect():
        async with c.app.state.pool.acquire() as db:
            row=await db.fetchrow('SELECT * FROM m1_app.usage_reservations WHERE budget_id=$1',c.budget_id)
            assert row['counted_input_tokens']==14778 and row['max_input_tokens']==14810
            assert row['state']=='settled' and row['actual_cost']==Decimal('0.026779')
    c.http.portal.call(inspect)


def test_input_headroom_must_fit_the_existing_budget_before_dispatch(budget_case):
    c=budget_case;transport=CountDriftClient()
    async def restrict():
        async with c.app.state.pool.acquire() as db:
            await db.execute('UPDATE m1_app.stage_budgets SET max_input_tokens=14778 WHERE id=$1',c.budget_id)
    c.http.portal.call(restrict)
    paid=PaidCall(c.app.state.pool,c.actor,UUID(c.tender['id']),'too-close')
    with pytest.raises(DomainError) as error:
        c.http.portal.call(paid.create_response,transport,
            {'model':'controlled-model','input':'Controlled','max_output_tokens':6000},c.prices)
    assert error.value.code=='STAGE_INPUT_LIMIT' and transport.created==0


def test_drift_beyond_the_reserved_margin_still_pauses_and_holds(budget_case):
    c=budget_case;transport=CountDriftClient(delta=33)
    paid=PaidCall(c.app.state.pool,c.actor,UUID(c.tender['id']),'real-overage')
    with pytest.raises(DomainError) as error:
        c.http.portal.call(paid.create_response,transport,
            {'model':'controlled-model','input':'Controlled','max_output_tokens':6000},c.prices)
    assert error.value.code=='PROVIDER_USAGE_EXCEEDED'
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['reserved_usd']!='0'


def legacy_exception(c,delta=1,output_delta=0):
    original=reserve(c,'legacy-count','0.026778',limits(14778,6000))
    response={'id':'legacy-response','model':'controlled-model','status':'incomplete',
        'usage':usage(14778+delta,6000+output_delta)}
    recorded={**response['usage'],'response_id':response['id'],'model':response['model']}
    with pytest.raises(DomainError): c.http.portal.call(c.ledger.settle_call,original,recorded,'completed')
    return original,response


def reconcile(c,actor,reservation,response,apply=False,cap='0.15',reason='Confirmed one-token counter discrepancy'):
    return c.http.portal.call(partial(c.ledger.reconcile_call,actor,reservation['id'],response,Decimal(cap),
        'Recorded one-generation approval, maximum US$0.15',reason,apply=apply))


def test_reconciliation_preview_then_apply_keeps_original_limits_and_paused_state(budget_case,actors):
    c=budget_case;original,response=legacy_exception(c)
    preview=reconcile(c,actors['admin'],original,response)
    assert preview['state']=='preview' and preview['actual_cost_usd']=='0.026779'
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['reserved_usd']=='0.026778'
    result=reconcile(c,actors['admin'],original,response,apply=True)
    assert result['state']=='settled'
    summary=c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)
    assert summary['actual_cost_usd']=='0.026779' and summary['reserved_usd']=='0'
    assert summary['provider_requests']==1 and summary['blocked_reason']=='PROVIDER_USAGE_EXCEEDED'
    async def inspect():
        async with c.app.state.pool.acquire() as db:
            row=await db.fetchrow('SELECT * FROM m1_app.usage_reservations WHERE id=$1',original['id'])
            audit=await db.fetchrow('SELECT * FROM m1_app.usage_reconciliations WHERE reservation_id=$1',original['id'])
            assert row['maximum_cost']==Decimal('0.026778') and row['max_input_tokens']==14778
            assert row['actual_input_tokens']==14779 and row['reconciliation_id']==audit['id']
            assert json.loads(audit['original_reservation'])['state']=='unknown'
            assert json.loads(audit['provider_response'])==response
            assert audit['actor_id']==actors['admin'].user_id and audit['authorized_cost']==Decimal('0.15')
            assert await db.fetchval('SELECT paused FROM m1_app.workspace_spending_policies WHERE workspace_id=$1',c.actor.workspace_id)
            assert not await db.fetchval("SELECT has_table_privilege('authenticated','m1_app.usage_reconciliations','SELECT')")
    c.http.portal.call(inspect)


def test_reconciliation_replay_is_exactly_once_and_conflicting_replay_is_rejected(budget_case,actors):
    c=budget_case;original,response=legacy_exception(c)
    first=reconcile(c,actors['admin'],original,response,apply=True)
    second=reconcile(c,actors['admin'],original,response,apply=True)
    assert first['reconciliation_id']==second['reconciliation_id']
    with pytest.raises(DomainError) as error:
        reconcile(c,actors['admin'],original,response,apply=True,reason='Different authorization claim')
    assert error.value.code=='DUPLICATE_CONFLICT'
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['actual_cost_usd']=='0.026779'


@pytest.mark.parametrize('actor',['owner','viewer','other'])
def test_reconciliation_requires_current_workspace_admin(budget_case,actors,actor):
    c=budget_case;original,response=legacy_exception(c)
    with pytest.raises(DomainError): reconcile(c,actors[actor],original,response,apply=True)
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['reserved_usd']=='0.026778'


@pytest.mark.parametrize('change',['identity','usage','nonterminal','cap','stage','daily','tokens','blank_reason'])
def test_unverified_or_unauthorized_receipt_cannot_be_reconciled(budget_case,actors,change):
    c=budget_case;original,response=legacy_exception(c);cap='0.15';reason='Confirmed discrepancy'
    if change=='identity': response['id']='another-response'
    if change=='usage': response['usage']['input_tokens']+=1
    if change=='nonterminal': response['status']='in_progress'
    if change=='cap': cap='0.02'
    if change=='blank_reason': reason=' '
    if change in {'stage','daily','tokens'}:
        async def restrict():
            async with c.app.state.pool.acquire() as db:
                if change=='stage': await db.execute('UPDATE m1_app.stage_budgets SET limit_usd=0.026778 WHERE id=$1',c.budget_id)
                if change=='daily': await db.execute('UPDATE m1_app.workspace_spending_policies SET daily_limit_usd=0.026778 WHERE workspace_id=$1',c.actor.workspace_id)
                if change=='tokens': await db.execute('UPDATE m1_app.stage_budgets SET max_input_tokens=14778 WHERE id=$1',c.budget_id)
        c.http.portal.call(restrict)
    with pytest.raises(DomainError): reconcile(c,actors['admin'],original,response,apply=True,cap=cap,reason=reason)
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['reserved_usd']=='0.026778'


@pytest.mark.parametrize('delta,output_delta',[(33,0),(1,1)])
def test_reconciliation_cannot_waive_output_or_large_input_overruns(budget_case,actors,delta,output_delta):
    c=budget_case;original,response=legacy_exception(c,delta,output_delta)
    with pytest.raises(DomainError): reconcile(c,actors['admin'],original,response,apply=True)


def test_unknown_transport_without_a_recorded_receipt_stays_held(budget_case,actors):
    c=budget_case;original=reserve(c,'unknown','0.026778',limits(14778,6000))
    c.http.portal.call(c.ledger.settle_call,original,None,'unknown')
    response={'id':'unverified','model':'controlled-model','status':'completed','usage':usage(14779,6000)}
    with pytest.raises(DomainError): reconcile(c,actors['admin'],original,response,apply=True)


def test_concurrent_reconciliation_records_one_charge(budget_case,actors):
    c=budget_case;original,response=legacy_exception(c)
    async def both():
        return await asyncio.gather(*[c.ledger.reconcile_call(actors['admin'],original['id'],response,Decimal('0.15'),
            'Recorded one-generation approval, maximum US$0.15','Confirmed one-token counter discrepancy',apply=True)
            for _ in range(2)])
    first,second=c.http.portal.call(both)
    assert first['reconciliation_id']==second['reconciliation_id']
    assert c.http.portal.call(c.ledger.summary,c.budget_id,c.actor)['actual_cost_usd']=='0.026779'


def test_revoked_admin_claim_cannot_reconcile(budget_case,actors):
    c=budget_case;original,response=legacy_exception(c)
    async def revoke():
        async with c.app.state.pool.acquire() as db:
            await db.execute("UPDATE m1_app.memberships SET roles=ARRAY['viewer'] WHERE workspace_id=$1 AND user_id=$2",
                actors['admin'].workspace_id,actors['admin'].user_id)
    c.http.portal.call(revoke)
    with pytest.raises(DomainError) as error: reconcile(c,actors['admin'],original,response,apply=True)
    assert error.value.code=='FORBIDDEN'


def test_existing_reservation_fingerprint_without_count_metadata_replays_without_dispatch(budget_case):
    c=budget_case;original=reserve(c,'legacy-fingerprint')
    old_limits=limits().model_dump(mode='json');old_limits.pop('counted_input_tokens',None)
    old_hash=hashlib.sha256(json.dumps({'limits':old_limits,'maximum_cost':'0.30',
        'price':c.prices['controlled-model'].model_dump(mode='json'),'actor_id':str(c.actor.user_id)},sort_keys=True).encode()).hexdigest()
    async def previous_version():
        async with c.app.state.pool.acquire() as db:
            await db.execute('UPDATE m1_app.usage_reservations SET request_hash=$2 WHERE id=$1',original['id'],old_hash)
    c.http.portal.call(previous_version)
    replay=reserve(c,'legacy-fingerprint')
    assert replay['id']==original['id'] and replay['dispatch'] is False
