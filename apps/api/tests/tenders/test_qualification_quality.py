"""Decision quality: bounded evidence, conservative gates and human conditions."""
from copy import deepcopy

import pytest

from app.tenders.policy import DomainError
from app.tenders.screening import Interpretation,ScreeningArtifact,validate_interpretation
from test_screening import candidate,context,finding,run


def quality_case(role="preparation_work",**changes):
    ctx=context()
    text="Submit the completed pricing schedule with the tender submission."
    if role=="future_duty": text="The contractor shall provide the performance security after award."
    ctx["excerpts"].append({"anchor_id":"work-p1","document_version_id":"work",
        "source_index_version":"index","source_role":"tender","quote":text})
    row=finding("work",kind="bid_artifact" if role=="preparation_work" else "delivery_commitment",
        due_stage="submission" if role=="preparation_work" else "award",material_now=False,
        status="unconfirmed",critical_basis=text,tender_citations=[{"anchor_id":"work-p1","quote":text}],
        company_citations=[],preparation_role=role,preparation_basis=text,**changes)
    return ctx,row


def raw(*rows):
    return {**candidate(*rows),"overview_issues":[]}


@pytest.mark.parametrize("role",["preparation_work","future_duty"])
def test_unfinished_work_can_be_conditioned_without_claiming_compliance(role):
    ctx,row=quality_case(role)
    result=run(ctx,raw(row))
    assert result["findings"][0]["status"]=="unconfirmed"
    assert "CRITICAL_CONDITION_UNRESOLVED" not in result["approval_blockers"]
    assert result["preparation_condition_ids"]==["work"]
    assert not any(d["draft_ref"]=="finding:work" for d in result["request_drafts"])


@pytest.mark.parametrize("changes",[
    {"kind":"eligibility"},{"kind":"scored_criterion"},{"due_stage":"unknown"},
    {"material_now":True},{"material_now":None},{"status":"evidenced_failure"},
    {"preparation_basis":None},{"preparation_basis":"Not in the source"},
])
def test_roles_cannot_waive_present_gates_risks_or_missing_timing_support(changes):
    ctx,row=quality_case();row.update(changes)
    with pytest.raises(DomainError): validate_interpretation(raw(row),ctx)


def test_exclusion_wording_cannot_be_waived_by_producer_labels():
    ctx,row=quality_case()
    text="Submit pricing with the tender submission; otherwise the tender will be disqualified."
    ctx["excerpts"][-1]["quote"]=text
    row.update(critical_basis=text,preparation_basis=text,tender_citations=[{"anchor_id":"work-p1","quote":text}])
    with pytest.raises(DomainError): validate_interpretation(raw(row),ctx)


def test_a_registration_gate_cannot_be_disguised_as_an_unfinished_bid_artifact():
    ctx=context();row=finding(kind="bid_artifact",material_now=False,status="unconfirmed",company_citations=[],
        preparation_role="preparation_work",preparation_basis="Critical registration is required before submission.")
    with pytest.raises(DomainError): validate_interpretation(raw(row),ctx)


def test_legacy_unclassified_critical_work_keeps_the_existing_blocker():
    ctx,row=quality_case();row.pop("preparation_role");row.pop("preparation_basis")
    # New producer requires an explicit role, while old stored artifacts remain readable.
    with pytest.raises(DomainError): validate_interpretation(raw(row),ctx)
    row.update(preparation_role=None,preparation_basis=None)
    result=run(ctx,raw(row))
    assert "CRITICAL_CONDITION_UNRESOLVED" in result["approval_blockers"]
    result["findings"][0].pop("preparation_role");result["findings"][0].pop("preparation_basis")
    result.pop("preparation_condition_ids");result.pop("overview_issues")
    assert ScreeningArtifact.model_validate(result).findings[0].preparation_role is None


def test_scoped_answer_cannot_downgrade_a_known_gate_or_change_materiality():
    ctx,row=quality_case();row.update(preparation_role=None,preparation_basis=None,material_now=True)
    ctx.update(previous={"pins":ctx["pins"],"findings":[deepcopy(row)]},affected_ids=["work"])
    row.update(preparation_role="preparation_work",preparation_basis=row["critical_basis"],material_now=False)
    result=run(ctx,raw(row))
    assert result["attention"]=="SCREENING_DEPENDENCY_WIDER_REQUIRED"
    assert result["findings"]==ctx["previous"]["findings"]


def issue_case():
    ctx=context()
    ctx["overview_excerpts"]=[{"anchor_id":"terms-p1","source_role":"tender","source_index_version":"index",
        "quote":"Contract period: 72 months."},
        {"anchor_id":"terms-p1","source_role":"tender","source_index_version":"index",
        "quote":"Store services: 60 months plus optional 36 months."}]
    issue={"field":"contract_period","kind":"conflicting","question":"Confirm the applicable periods for the overall contract and store services.",
        "citations":[{"anchor_id":e["anchor_id"],"quote":e["quote"]} for e in ctx["overview_excerpts"]]}
    return ctx,issue


def test_two_native_windows_support_a_conflict_and_an_assignable_question():
    ctx,issue=issue_case()
    result=run(ctx,{**raw(finding(preparation_role=None,preparation_basis=None)),"overview_issues":[issue]})
    assert issue in result["overview_issues"]
    assert "CRITICAL_COVERAGE_UNKNOWN" in result["approval_blockers"]
    draft=next(d for d in result["request_drafts"] if d["draft_ref"]=="overview:contract_period")
    assert draft["question"]==issue["question"] and draft["finding_ids"]==[]
    assert draft["overview_field"]=="contract_period" and "assignee_id" not in draft


@pytest.mark.parametrize("mutation",["bridge","foreign","duplicate","nested","one","wrong_role","wrong_index","known"])
def test_conflict_support_cannot_invent_or_join_source_windows(mutation):
    ctx,issue=issue_case();payload=raw(finding(preparation_role=None,preparation_basis=None))
    if mutation=="bridge": issue["citations"][0]["quote"]="72 months. Store services: 60 months"
    if mutation=="foreign": issue["citations"][0]["anchor_id"]="foreign"
    if mutation=="duplicate": issue["citations"][1]=deepcopy(issue["citations"][0])
    if mutation=="nested": issue["citations"][1]={"anchor_id":"terms-p1","quote":"72 months"}
    if mutation=="one": issue["citations"]=issue["citations"][:1]
    if mutation=="wrong_role": ctx["overview_excerpts"][0]["source_role"]="company"
    if mutation=="wrong_index": ctx["overview_excerpts"][0]["source_index_version"]="old"
    if mutation=="known":
        payload["summary"]={k:{"value":None,"citations":[]} for k in ("buyer","reference","scope","contract_period","sites")}
        payload["summary"]["contract_period"]={"value":"72 months","citations":[issue["citations"][0]]}
    payload["overview_issues"]=[issue]
    with pytest.raises(DomainError): validate_interpretation(payload,ctx)


def test_closing_conflict_cannot_restore_the_previous_closing_time():
    ctx,issue=issue_case();issue["field"]="closing_at"
    result=run(ctx,{**raw(finding(preparation_role=None,preparation_basis=None)),"overview_issues":[issue]})
    assert result["closing_at"] is None and result["facts"]["closing_at"]["citations"]==[]
    assert "CLOSING_UNKNOWN" in result["approval_blockers"]


def test_tender_deadline_conflicting_with_notice_stays_unknown_until_sources_change():
    ctx=context();quote="Closing submission deadline: 2099-02-01T16:00:00+08:00."
    ctx["pins"]["tender_source_signature"]="tender-same"
    ctx["excerpts"].append({"anchor_id":"deadline-p1","source_role":"tender","source_index_version":"index","quote":quote})
    result=run(ctx,{**raw(finding()),"closing_at":"2099-02-01T16:00:00+08:00",
        "closing_citations":[{"anchor_id":"deadline-p1","quote":quote}]})
    assert result["closing_at"] is None and "CLOSING_UNKNOWN" in result["approval_blockers"]
    assert any(i["field"]=="closing_at" and i["citations"] for i in result["overview_issues"])
    ctx["previous"]=result
    assert run(ctx,raw(finding()))["closing_at"] is None
    ctx["pins"]={**ctx["pins"],"source_signature":"amended","tender_source_signature":"tender-amended"}
    assert run(ctx,raw(finding()))["closing_at"]==ctx["closing_at"]


@pytest.mark.parametrize("legacy",[False,True])
def test_company_only_changes_cannot_erase_tender_or_notice_conflicts(legacy):
    ctx,issue=issue_case()
    ctx["pins"]["tender_source_signature"]="tender-same"
    original=run(ctx,{**raw(finding()),"overview_issues":[issue]})
    if legacy: original["pins"].pop("tender_source_signature")
    ctx["previous"]=deepcopy(original)
    ctx["pins"]={**ctx["pins"],"source_signature":"company-amended","company_version_id":"new-company",
        "tender_source_signature":"tender-same"}
    result=run(ctx,raw(finding()))
    assert issue in result["overview_issues"] and "CRITICAL_COVERAGE_UNKNOWN" in result["approval_blockers"]
    # A real tender/notice amendment can trigger fresh interpretation when both identities are known.
    if not legacy:
        ctx["pins"]["tender_source_signature"]="tender-amended"
        assert "CRITICAL_COVERAGE_UNKNOWN" not in run(ctx,raw(finding()))["approval_blockers"]

    ctx=context();ctx["pins"]["tender_source_signature"]="tender-same"
    quote="Closing submission deadline: 2099-02-01T16:00:00+08:00."
    ctx["excerpts"].append({"anchor_id":"deadline-p1","source_role":"tender","source_index_version":"index","quote":quote})
    old=run(ctx,{**raw(finding()),"closing_at":"2099-02-01T16:00:00+08:00",
        "closing_citations":[{"anchor_id":"deadline-p1","quote":quote}]})
    if legacy: old["pins"].pop("tender_source_signature")
    ctx["previous"]=deepcopy(old)
    ctx["pins"]={**ctx["pins"],"source_signature":"company-amended","company_version_id":"new-company",
        "tender_source_signature":"tender-same"}
    result=run(ctx,raw(finding()))
    assert result["closing_at"] is None and "CLOSING_UNKNOWN" in result["approval_blockers"]


def test_overview_answer_has_no_authority_to_change_any_findings():
    ctx=context();prior=finding(preparation_role=None,preparation_basis=None)
    ctx.update(previous={"pins":ctx["pins"],"findings":[prior]},affected_ids=[])
    result=run(ctx,raw(prior))
    assert result["attention"]=="SCREENING_DEPENDENCY_WIDER_REQUIRED"
    assert result["findings"]==[prior]


def test_an_unrelated_answer_cannot_erase_a_known_source_conflict():
    ctx,issue=issue_case();row=finding()
    ctx["previous"]=run(ctx,{**raw(row),"overview_issues":[issue]})
    ctx["affected_ids"]=[row["id"]]
    result=run(ctx,raw(row))
    assert result["attention"]=="SCREENING_DEPENDENCY_WIDER_REQUIRED"
    assert issue in result["overview_issues"]


def test_missing_closing_issue_cannot_contradict_a_known_notice_deadline():
    ctx=context()
    issue={"field":"closing_at","kind":"not_established","question":"Confirm the deadline.","citations":[]}
    with pytest.raises(DomainError): validate_interpretation({**raw(finding()),"overview_issues":[issue]},ctx)


def test_new_producer_contract_requires_explicit_roles_and_issues():
    schema=Interpretation.model_json_schema()
    assert "overview_issues" in schema["required"]
    definition=schema["$defs"]["CandidateFinding"]
    assert "preparation_role" in definition["required"] and "preparation_basis" in definition["required"]


def test_tender_fingerprint_excludes_company_but_tracks_source_and_notice_identity():
    from app.tenders.screening_workflow import tender_source_signature
    docs=[{"id":"tender","sha256":"one","role":"tender"},{"id":"company","sha256":"two","role":"company_evidence"}]
    initial=tender_source_signature(docs,"notice")
    docs[1].update(id="new-company",sha256="new")
    assert tender_source_signature(docs,"notice")==initial
    assert tender_source_signature(docs,"new-notice")!=initial
    docs[0]["sha256"]="amended"
    assert tender_source_signature(docs,"notice")!=initial
