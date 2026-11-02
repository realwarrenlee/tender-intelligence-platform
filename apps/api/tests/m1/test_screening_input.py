"""Detailed source inventory stays authoritative without crowding the model input."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.m1.policy import DomainError
from app.m1.screening_workflow import ScreeningReasoner
from test_screening import context


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
    from app.m1.usage_budget import PaidCall
    ctx = large_context()
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
    assert ctx == original


def test_gap_summary_does_not_remove_the_hard_input_limit():
    ctx = large_context()
    ctx["excerpts"][0]["quote"] = "x" * 50000
    reasoner = ScreeningReasoner(None, None, {}, {}, None)
    with pytest.raises(DomainError) as caught:
        asyncio.run(reasoner.interpret(ctx, []))
    assert caught.value.code == "SCREENING_INPUT_LIMIT"
