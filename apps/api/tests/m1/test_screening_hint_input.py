"""Classifier metadata must not duplicate evidence or money records in the brief input."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

from app.m1.screening_workflow import ScreeningReasoner
from test_screening_input import large_context


def test_reasoner_uses_attributed_labels_without_repeating_sources_or_billing(monkeypatch):
    from app.m1.usage_budget import PaidCall
    ctx = large_context()
    ctx["coverage"]["deferred"] = ["deferred-" + ("x" * 80) + str(i) + ".pdf" for i in range(60)]
    hints = [{
        "source": excerpt, "rubric_version": "screening-v1",
        "answers": [{"name": "kind", "label": "eligibility", "status": "classified",
                     "confidence": 0.9, "probabilities": []}],
        "usage_receipt": {"id": str(uuid4()), "actual_cost": "0.0001",
                          "provider_usage": {"input_tokens": 1000, "output_tokens": 0}},
    } for excerpt in ctx["excerpts"][:4]]
    original = deepcopy(hints)
    captured = {}

    async def controlled_call(self, client, request, prices):
        captured.update(json.loads(request["input"]))
        return SimpleNamespace(status="completed", output_text='{"findings": []}')

    monkeypatch.setattr(PaidCall, "create_response", controlled_call)
    reasoner = ScreeningReasoner(None, None, {"id": uuid4(), "attempt": 1, "tender_id": uuid4()},
                                 {}, "controlled-model", object())
    asyncio.run(reasoner.interpret(ctx, hints))
    assert captured["excerpts"] == ctx["excerpts"]
    assert captured["classification_hints"] == [{
        "source_anchor_id": h["source"]["anchor_id"], "rubric_version": "screening-v1",
        "answers": h["answers"],
    } for h in original]
    assert hints == original
