from copy import deepcopy
import json

import pytest

from app.tenders.policy import DomainError
from app.tenders.screening import Interpretation,ScreeningArtifact,validate_interpretation
from test_screening import candidate,context,finding,run


def summary_context():
    ctx=context()
    ctx["excerpts"].append({"anchor_id":"overview-p1","document_version_id":"overview",
        "source_index_version":"index","source_role":"tender","quote":
        "Buyer: Fictional Agency. Reference: FM-2026. Scope: Integrated facilities maintenance. "
        "Contract period: Three years with an optional two-year extension. Sites: North and South campuses."})
    return ctx


def summary():
    return {key:{"value":value,"citations":[{"anchor_id":"overview-p1","quote":quote}]}
        for key,value,quote in [
            ("buyer","Fictional Agency","Buyer: Fictional Agency."),
            ("reference","FM-2026","Reference: FM-2026."),
            ("scope","Integrated facilities maintenance","Scope: Integrated facilities maintenance."),
            ("contract_period","Three years with an optional two-year extension",
                "Contract period: Three years with an optional two-year extension."),
            ("sites","North and South campuses","Sites: North and South campuses.")]}


def with_summary(value):
    return {**candidate(finding()),"summary":value}


@pytest.mark.parametrize("role",["tender","addendum"])
def test_exact_overview_extracts_survive_without_changing_qualification(role):
    ctx=summary_context();ctx["excerpts"][-1]["source_role"]=role
    result=run(ctx,with_summary(summary()))
    assert result["summary"]==summary()
    assert result["recommendation"]=="promising"
    assert result["approval_blockers"]==[]
    assert result["findings"]==[finding()]


@pytest.mark.parametrize("mutation",["foreign","company","role","missing_role","index","quote","paraphrase","blank",
    "uncited","null_cited","injected","missing_field"])
def test_overview_requires_exact_pinned_tender_support(mutation):
    ctx=summary_context();value=summary();fact=value["scope"]
    if mutation=="foreign": fact["citations"][0]["anchor_id"]="foreign-p1"
    if mutation=="company":
        fact.update(value="Fictional Ltd",citations=[ctx["company_excerpts"][0]])
    if mutation=="role": ctx["excerpts"][-1]["source_role"]="company"
    if mutation=="missing_role": del ctx["excerpts"][-1]["source_role"]
    if mutation=="index": ctx["excerpts"][-1]["source_index_version"]="older-index"
    if mutation=="quote": fact["citations"][0]["quote"]="Scope: Invented services."
    if mutation=="paraphrase": fact["value"]="Comprehensive facilities services"
    if mutation=="blank": fact["value"]="  "
    if mutation=="uncited": fact["citations"]=[]
    if mutation=="null_cited": fact["value"]=None
    if mutation=="injected": fact["assignee_id"]="model-selected-user"
    if mutation=="missing_field": del value["sites"]
    with pytest.raises(DomainError) as error: validate_interpretation(with_summary(value),ctx)
    assert error.value.code=="SCREENING_INVALID"


def test_new_producer_must_explicitly_supply_summary_even_when_unknown():
    raw=with_summary(None);del raw["summary"]
    with pytest.raises(DomainError): validate_interpretation(raw,context())
    assert run(context(),with_summary(None))["summary"] is None


@pytest.mark.parametrize("value",[None,{**summary(),"scope":{"value":None,"citations":[]}}])
def test_scoped_reassessment_does_not_restore_previous_overview(value):
    ctx=summary_context();previous=run(ctx,with_summary(summary()))
    ctx.update(previous=deepcopy(previous),affected_ids=["registration"])
    assert run(ctx,with_summary(value))["summary"]==value
    assert previous["summary"]==summary()


def test_changed_pinned_excerpts_cannot_validate_an_older_summary():
    ctx=summary_context();ctx["pins"]["source_signature"]="amended"
    ctx["excerpts"][-1]["quote"]="Scope: Revised services."
    with pytest.raises(DomainError): validate_interpretation(with_summary(summary()),ctx)


def test_bounded_fallback_never_resurrects_previous_summary():
    ctx=summary_context();ctx["previous"]=run(ctx,with_summary(summary()))
    ctx["affected_ids"]=["registration"]
    result=run(ctx,{**with_summary(summary()),"findings":[]})
    assert result["attention"]=="SCREENING_DEPENDENCY_WIDER_REQUIRED"
    assert result["findings"]==ctx["previous"]["findings"]
    assert result["summary"] is None


def test_reported_summary_conflict_retains_wider_review_without_establishing_a_fact():
    value={**summary(),"contract_period":{"value":None,"citations":[]}}
    result=run(summary_context(),{**with_summary(value),"needs_wider_review":True,
        "wider_review_reason":"The tender and addendum specify conflicting contract periods."})
    assert result["summary"]["contract_period"]=={"value":None,"citations":[]}
    assert result["coverage"]["requires_wider_review"]
    assert result["wider_review_reason"]=="The tender and addendum specify conflicting contract periods."
    assert "CRITICAL_COVERAGE_UNKNOWN" in result["approval_blockers"]


def test_old_persisted_screening_without_summary_remains_readable():
    from app.config import ROOT
    from jsonschema import validate
    artifact=run(context(),with_summary(None));del artifact["summary"]
    assert ScreeningArtifact.model_validate(artifact).summary is None
    validate(artifact,json.loads((ROOT/'contracts/qualification/screening.schema.json').read_text()))


def test_provider_schema_requires_nullable_summary_and_strict_nested_fields():
    schema=Interpretation.model_json_schema()
    assert "summary" in schema["required"]
    assert {option.get("type") for option in schema["properties"]["summary"]["anyOf"]}>={None,"null"}
    for name in ("SummaryFact","QualificationSummary"):
        definition=schema["$defs"][name]
        assert definition["additionalProperties"] is False
        assert set(definition["required"])==set(definition["properties"])


def test_exported_screening_schema_preserves_its_public_identity_and_dialect():
    from app.config import ROOT
    from jsonschema import Draft202012Validator
    schema=json.loads((ROOT/'contracts/qualification/screening.schema.json').read_text())
    assert schema['$id']=='urn:tender-intelligence:m1:screening:v1'
    assert schema['$schema']=='https://json-schema.org/draft/2020-12/schema'
    Draft202012Validator.check_schema(schema)
