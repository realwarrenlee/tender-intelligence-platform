"""Task 6 evidence-delivery metrics must not masquerade as model-quality scores."""
import importlib.util
from pathlib import Path

import pytest


def audit_module():
    path = Path(__file__).resolve().parents[4] / "evals/run_pub_source_audit.py"
    spec = importlib.util.spec_from_file_location("pub_source_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expectation(**changes):
    return {"id": "gate", "critical_now": True, "source": {
        "source_index_version": "index", "document_version_id": "document",
        "anchor_id": "page-1", "quote": "Must hold FM01 registration."
    }, **changes}


@pytest.mark.parametrize("change", [
    {"quote": "Unrelated text from the same page."},
    {"anchor_id": "page-2"},
    {"document_version_id": "other"},
    {"source_index_version": "old-index"},
])
def test_delivery_requires_exact_quote_and_every_source_identity(change):
    item = expectation()
    excerpt = {**item["source"], **change}
    result = audit_module().audit_delivery([item], [excerpt])
    assert result["delivered_items"] == result["delivered_critical_items"] == 0
    assert result["critical_evidence_delivery_rate"] == 0
    assert result["items"][0]["evidence_delivered"] is False


def test_a_delivered_quote_is_evidence_input_not_a_model_finding():
    item = expectation()
    result = audit_module().audit_delivery([item], [
        {**item["source"], "quote": "Context. Must hold FM01 registration. More context."}
    ])
    assert result["delivered_items"] == result["delivered_critical_items"] == 1
    assert result["critical_evidence_delivery_rate"] == 1
    assert result["model_critical_gate_recall"] is None
    assert result["model_accuracy"] is None
    assert result["unsupported_model_assertions"] is None


def test_noncritical_delivery_does_not_hide_a_missed_gate():
    gate = expectation()
    ordinary = expectation(id="future", critical_now=False, source={
        **gate["source"], "quote": "Supply staffing after award."
    })
    result = audit_module().audit_delivery([gate, ordinary], [ordinary["source"]])
    assert result["expected_items"] == 2 and result["delivered_items"] == 1
    assert result["expected_critical_items"] == 1 and result["delivered_critical_items"] == 0
    assert result["critical_evidence_delivery_rate"] == 0


def test_no_critical_items_has_no_recall_denominator():
    result = audit_module().audit_delivery([expectation(critical_now=False)], [])
    assert result["critical_evidence_delivery_rate"] is None
