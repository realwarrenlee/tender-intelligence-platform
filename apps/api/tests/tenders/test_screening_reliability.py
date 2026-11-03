"""Offline regressions for the two failures observed in the authorised screening."""
import asyncio
import json
from types import SimpleNamespace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.tenders.policy import DomainError
from app.tenders.screening import validate_interpretation
from app.tenders.screening_workflow import ScreeningReasoner
from app.tenders.usage_budget import PaidCall
from test_screening import candidate, context, finding
from test_screening_input import large_context
from test_stage_budget import ControlledClient, budget_case, usage


class BackgroundClient(ControlledClient):
    def __init__(self, outcomes, inspect_receipt):
        super().__init__()
        self.outcomes = iter(outcomes)
        self.inspect_receipt = inspect_receipt
        self.reads = []

    async def create(self, **request):
        self.requests.append(request)
        return self.response("queued")

    def response(self, status, response_id="resp_controlled"):
        return SimpleNamespace(
            id=response_id, model="controlled-model", status=status, output_text="{}",
            usage=SimpleNamespace(model_dump=lambda: usage(1000, 100)) if status == "completed" else None,
        )

    async def retrieve(self, response_id):
        self.reads.append(response_id)
        await self.inspect_receipt()
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return self.response(*outcome)


def background_call(case, outcomes):
    scope = PaidCall(case.app.state.pool, case.actor, UUID(case.tender["id"]), "background-screening")

    async def inspect():
        async with case.app.state.pool.acquire() as db:
            row = await db.fetchrow(
                "SELECT state,actual_cost,provider_usage FROM m1_app.usage_reservations WHERE budget_id=$1",
                case.budget_id,
            )
            assert row["state"] == "unknown" and row["actual_cost"] is None
            assert json.loads(row["provider_usage"])["response_id"] == "resp_controlled"

    client = BackgroundClient(outcomes, inspect)
    request = {"model": "controlled-model", "input": "Fictional evidence", "max_output_tokens": 12000,
               "background": True, "store": True}
    return scope, client, request


def test_background_screening_checkpoints_id_before_polling_and_settles_once(budget_case):
    c = budget_case
    scope, client, request = background_call(c, [("in_progress",), ("completed",)])
    result = c.http.portal.call(scope.create_response, client, request, c.prices)
    assert result.id == "resp_controlled" and result.status == "completed"
    assert len(client.requests) == 1 and client.reads == ["resp_controlled", "resp_controlled"]

    async def inspect():
        async with c.app.state.pool.acquire() as db:
            rows = await db.fetch("SELECT state,actual_cost,provider_usage FROM m1_app.usage_reservations WHERE budget_id=$1", c.budget_id)
            assert len(rows) == 1 and rows[0]["state"] == "settled"
            assert rows[0]["actual_cost"] == Decimal("0.0012")
            assert json.loads(rows[0]["provider_usage"])["response_id"] == result.id
    c.http.portal.call(inspect)


@pytest.mark.parametrize("failure", [TimeoutError("controlled retrieval timeout"), asyncio.CancelledError()])
def test_background_interruption_keeps_id_and_cost_without_redispatch(budget_case, failure):
    c = budget_case
    scope, client, request = background_call(c, [failure])
    async def interrupted():
        with pytest.raises(type(failure)):
            await scope.create_response(client, request, c.prices)
    c.http.portal.call(interrupted)
    with pytest.raises(DomainError) as error:
        c.http.portal.call(scope.create_response, client, request, c.prices)
    assert error.value.code == "MODEL_OUTCOME_UNKNOWN"
    assert len(client.requests) == 1 and client.reads == ["resp_controlled"]
    c.http.portal.call(client.inspect_receipt)


def test_background_retrieval_cannot_switch_response_identity(budget_case):
    c = budget_case
    scope, client, request = background_call(c, [("completed", "resp_other")])
    with pytest.raises(DomainError) as error:
        c.http.portal.call(scope.create_response, client, request, c.prices)
    assert error.value.code == "MODEL_OUTCOME_UNKNOWN"
    assert len(client.requests) == 1
    c.http.portal.call(client.inspect_receipt)


def test_screening_producer_specifies_exact_critical_basis_and_early_response_id(monkeypatch):
    recorded = {}

    async def capture(self, client, request, prices):
        recorded.update(request)
        return SimpleNamespace(status="completed", output_text='{"findings": []}')

    monkeypatch.setattr(PaidCall, "create_response", capture)
    reasoner = ScreeningReasoner(None, None, {"id": uuid4(), "attempt": 1, "tender_id": uuid4()},
                                 {}, "controlled-model", object())
    asyncio.run(reasoner.interpret(large_context(), []))
    schema = recorded["text"]["format"]["schema"]
    variants=[schema["$defs"][variant["$ref"].rsplit("/",1)[-1]]
        for variant in schema["properties"]["findings"]["items"]["anyOf"]]
    finding_schema=next(variant for variant in variants if "critical_basis" in variant["properties"])
    description = finding_schema["properties"]["critical_basis"].get("description", "")
    assert "verbatim" in description and "tender_citations" in description
    assert "critical_basis" in recorded["instructions"] and "statement" in recorded["instructions"]
    assert recorded.get("background") is True and recorded.get("store") is True


def test_critical_basis_paraphrase_stays_invalid_and_literal_source_passes():
    ctx = context()
    with pytest.raises(DomainError) as error:
        validate_interpretation(candidate(finding(critical_basis="Registration is a prerequisite.")), ctx)
    assert error.value.code == "SCREENING_INVALID"
    assert validate_interpretation(candidate(finding()), ctx)["findings"][0]["critical"]


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_noncompleted_response_never_becomes_a_screening_candidate(monkeypatch, status):
    async def capture(self, client, request, prices):
        return SimpleNamespace(status=status, output_text=json.dumps(candidate()))

    monkeypatch.setattr(PaidCall, "create_response", capture)
    reasoner = ScreeningReasoner(None, None, {"id": uuid4(), "attempt": 1, "tender_id": uuid4()},
                                 {}, "controlled-model", object())
    with pytest.raises(DomainError) as error:
        asyncio.run(reasoner.interpret(large_context(), []))
    assert error.value.code == "SCREENING_INVALID"


def test_cancellation_during_acknowledgement_save_keeps_the_known_response_id(budget_case, monkeypatch):
    from app.tenders.usage_budget import UsageBudget
    c = budget_case
    scope, client, request = background_call(c, [])
    settle = UsageBudget.settle_call
    interrupted = False

    async def cancel_first_save(self, reservation, provider_usage, outcome):
        nonlocal interrupted
        if not interrupted and provider_usage and provider_usage.get("response_id"):
            interrupted = True
            raise asyncio.CancelledError()
        return await settle(self, reservation, provider_usage, outcome)

    monkeypatch.setattr(UsageBudget, "settle_call", cancel_first_save)

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            await scope.create_response(client, request, c.prices)
        async with c.app.state.pool.acquire() as db:
            row = await db.fetchrow(
                "SELECT state,actual_cost,provider_usage FROM m1_app.usage_reservations WHERE budget_id=$1",
                c.budget_id,
            )
            assert row["state"] == "unknown" and row["actual_cost"] is None
            assert row["provider_usage"] is not None
            assert json.loads(row["provider_usage"])["response_id"] == "resp_controlled"
    c.http.portal.call(exercise)
    assert len(client.requests) == 1 and client.reads == []
