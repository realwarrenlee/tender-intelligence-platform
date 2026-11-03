"""Detailed source inventory stays authoritative without crowding the model input."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tenders.policy import DomainError
from app.tenders.screening_workflow import ScreeningReasoner
from test_screening import context,finding


def large_context():
    ctx = context()
    ctx["pins"]["source_index_version"] = str(uuid4())
    template = ctx["excerpts"][0]
    ctx["excerpts"] = [
        {**template, "anchor_id": f"doc-{i}-p1", "quote": "Source evidence passage. " * 180}
        for i in range(6)
    ]
    ctx["coverage"] = {
        "complete": False, "requires_wider_review": True, "deferred": ["appendix.pdf"],
        "gaps": [
            {"document_version_id": str(uuid4()), "location_label": "Unread region " + str(i),
             "error_code": "IMAGE_REQUIRES_REVIEW", "materiality": "unknown",
             "filename": "appendix-" + ("x" * 130) + str(i) + ".pdf"}
            for i in range(94)
        ],
    }
    return ctx


def test_reasoner_receives_gap_count_and_sample_without_clearing_full_inventory(monkeypatch):
    from app.tenders.usage_budget import PaidCall
    ctx = large_context()
    ctx["coverage"]["deferred"]=["source-"+str(i)+".pdf" for i in range(61)]
    original = deepcopy(ctx)
    captured = {}

    async def controlled_call(self, client, request, prices):
        captured.update(json.loads(request["input"]))
        return SimpleNamespace(status="completed", output_text='{"findings": []}')

    monkeypatch.setattr(PaidCall, "create_response", controlled_call)
    reasoner = ScreeningReasoner(None, None, {"id": uuid4(), "attempt": 1, "tender_id": uuid4()},
                                 {}, "controlled-model", object())
    asyncio.run(reasoner.interpret(ctx, []))
    assert captured["coverage"]["gap_count"] == 94
    assert captured["coverage"]["gaps_truncated"] is True
    assert captured["coverage"]["gaps"] == original["coverage"]["gaps"][:8]
    assert captured["coverage"]["complete"] is False
    assert captured["coverage"]["requires_wider_review"] is True
    assert captured["coverage"]["deferred"]==original["coverage"]["deferred"][:4]
    assert captured["coverage"]["deferred_count"]==61 and captured["coverage"]["deferred_truncated"] is True
    assert ctx == original


def test_gap_summary_does_not_remove_the_hard_input_limit():
    ctx = large_context()
    ctx["excerpts"][0]["quote"] = "x" * 50000
    reasoner = ScreeningReasoner(None, None, {}, {}, None)
    with pytest.raises(DomainError) as caught:
        asyncio.run(reasoner.interpret(ctx, []))
    assert caught.value.code == "SCREENING_INPUT_LIMIT"


def test_reassessment_keeps_prior_obligation_identity_without_repeating_draft_prose(monkeypatch):
    from app.tenders.usage_budget import PaidCall
    ctx=large_context()
    ctx['previous']={'pins':deepcopy(ctx['pins']),'findings':[
        finding('gate_'+str(i),statement='Earlier explanatory text. '*55,
            request_question='Confirm the earlier evidence. '*30) for i in range(12)]}
    original=deepcopy(ctx);captured={}
    async def controlled_call(self,client,request,prices):
        captured.update(json.loads(request['input']))
        assert len(request['input'].encode())<=49152
        return SimpleNamespace(status='completed',output_text='{"summary": null, "findings": []}')
    monkeypatch.setattr(PaidCall,'create_response',controlled_call)
    reasoner=ScreeningReasoner(None,None,{'id':uuid4(),'attempt':1,'tender_id':uuid4()},
        {},'controlled-model',object())
    asyncio.run(reasoner.interpret(ctx,[]))
    assert captured['previous_findings']==[
        {key:f.get(key) for key in ('id','kind','due_stage','critical','critical_basis','material_now','preparation_role','preparation_basis','tender_citations')}
        for f in original['previous']['findings']]
    assert captured['excerpts']==original['excerpts']
    assert ctx==original
