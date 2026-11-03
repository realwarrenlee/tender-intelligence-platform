"""Bounded, source-bound screening candidates; business authority stays with people."""
from copy import deepcopy
from datetime import date,datetime,timezone
import hashlib
import json
import re
from zoneinfo import ZoneInfo
from typing import Annotated,Literal

from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator,model_validator

from app.tenders.policy import DomainError

Kind=Literal["eligibility","scored_criterion","bid_artifact","delivery_commitment","informational"]
Due=Literal["submission","award","mobilisation","delivery","unknown"]


class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class Support(Strict):
    anchor_id:str=Field(min_length=1,max_length=160)
    quote:str=Field(min_length=1,max_length=1000)

    @field_validator("anchor_id","quote")
    @classmethod
    def nonblank_support(cls,value):
        if not value.strip(): raise ValueError("Use a substantive exact citation.")
        return value


class SummaryFact(Strict):
    value:str|None=Field(min_length=1,max_length=1000)
    citations:list[Support]=Field(max_length=3)

    @model_validator(mode="after")
    def exact_extract(self):
        if self.value is None:
            if self.citations: raise ValueError("Unknown facts cannot have citations.")
        elif not self.value.strip() or not any(self.value in cite.quote for cite in self.citations):
            raise ValueError("Use a substantive verbatim extract from a cited quote.")
        return self


class QualificationSummary(Strict):
    buyer:SummaryFact
    reference:SummaryFact
    scope:SummaryFact
    contract_period:SummaryFact
    sites:SummaryFact


OverviewQuotes=Annotated[list[Support],Field(min_length=1,max_length=3)]


class QuotedOverview(Strict):
    buyer:OverviewQuotes|None
    reference:OverviewQuotes|None
    scope:OverviewQuotes|None
    contract_period:OverviewQuotes|None
    sites:OverviewQuotes|None


class Finding(Strict):
    id:str=Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    statement:str=Field(min_length=1,max_length=1500)
    kind:Kind
    due_stage:Due
    material_now:bool|None
    critical:bool
    critical_basis:str|None=Field(max_length=1000,description=
        "If critical is true, a nonblank verbatim substring of one of this finding's tender_citations quotes "
        "showing the mandatory or exclusion consequence; include the parent criterion in tender_citations if needed. "
        "Put explanations in statement. Use null when critical is false.")
    status:Literal["supported","unconfirmed","evidenced_failure"]
    tender_citations:list[Support]=Field(min_length=1,max_length=3)
    company_citations:list[Support]=Field(max_length=3)
    answer_ids:list[str]=Field(max_length=3)
    owner_function:Literal["compliance","operations","finance","bid_team"]
    request_question:str=Field(min_length=1,max_length=1000)
    preparation_role:Literal["decision_gate","preparation_work","future_duty","review"]|None=None
    preparation_basis:str|None=Field(default=None,min_length=1,max_length=1000)


class CandidateFinding(Finding):
    preparation_role:Literal["decision_gate","preparation_work","future_duty","review"]|None=Field(...)
    preparation_basis:str|None=Field(...,min_length=1,max_length=1000)


class OverviewIssue(Strict):
    field:Literal["buyer","reference","scope","contract_period","sites","closing_at"]
    kind:Literal["not_established","conflicting"]
    question:str=Field(min_length=1,max_length=1000)
    citations:list[Support]=Field(max_length=3)

    @field_validator("question")
    @classmethod
    def substantive_question(cls,value):
        if not value.strip(): raise ValueError("Ask a substantive review question.")
        return value


class Interpretation(Strict):
    summary:QualificationSummary|None
    findings:list[CandidateFinding]=Field(max_length=24)
    overview_issues:list[OverviewIssue]=Field(max_length=6)
    needs_wider_review:bool
    wider_review_reason:str|None=Field(max_length=2000)
    closing_at:str|None
    closing_citations:list[Support]=Field(max_length=2)


class RetainedFinding(Strict):
    retain_id:str=Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ProducerInterpretation(Interpretation):
    summary:QuotedOverview|None
    findings:list[CandidateFinding|RetainedFinding]=Field(max_length=24)


def reusable_findings(context):
    previous=context.get("previous")
    if not previous or context.get("affected_ids") is not None: return {}
    before=previous.get("pins",{});after=context["pins"]
    keys=("source_signature","input_revision","evidence_revision","source_index_version",
          "company_version_id","notice_version_id")
    if any(k not in before or k not in after or before[k]!=after[k] for k in keys): return {}
    if not after["source_signature"] or not after["source_index_version"]: return {}
    if any(not isinstance(pins.get("answer_version_ids"),list) for pins in (before,after)): return {}
    if set(before["answer_version_ids"])!=set(after["answer_version_ids"]): return {}
    return {f["id"]:f for f in previous["findings"]}


def expand_producer(raw,context):
    if not isinstance(raw,dict): raise ValueError()
    candidate=deepcopy(raw)
    reusable=reusable_findings(context)
    for i,f in enumerate(candidate.get("findings",[])):
        if isinstance(f,dict) and "retain_id" in f:
            key=RetainedFinding.model_validate(f).retain_id
            if key not in reusable: raise ValueError("The previous finding is not reusable.")
            candidate["findings"][i]=Finding.model_validate(reusable[key]).model_dump(mode="json")
    if candidate.get("summary") is not None:
        extracts=QuotedOverview.model_validate(candidate["summary"]).model_dump(mode="json")
        candidate["summary"]={key:{"value":quotes[0]["quote"] if quotes else None,"citations":quotes or []}
            for key,quotes in extracts.items()}
    return candidate


def finding_scope(finding):
    return hashlib.sha256(json.dumps([finding["kind"],finding["due_stage"],finding["critical"],finding.get("critical_basis"),
        finding["material_now"],finding.get("preparation_role"),finding.get("preparation_basis"),
        sorted((c["anchor_id"],c["quote"]) for c in finding["tender_citations"])],sort_keys=True).encode()).hexdigest()


def conditional_preparation(finding):
    role=finding.get("preparation_role")
    return (finding["status"]=="unconfirmed" and finding["material_now"] is False
        and bool(finding.get("preparation_basis")) and (
            role=="preparation_work" and finding["kind"]=="bid_artifact" and finding["due_stage"]=="submission"
            or role=="future_duty" and finding["kind"]=="delivery_commitment"
                and finding["due_stage"] in {"award","mobilisation","delivery"}))


def requires_preparation_condition(finding):
    return finding["status"]=="unconfirmed" and (finding["material_now"] is not False or conditional_preparation(finding))


def same_tender_sources(context):
    previous=context.get("previous")
    if not previous: return False
    before=previous.get("pins",{}).get("tender_source_signature")
    after=context["pins"].get("tender_source_signature")
    # Old histories are resolved from their native manifest by _context. Unknown identity cannot clear a conflict.
    return before==after if before and after else True


def retained_notice_conflict(context):
    return same_tender_sources(context) and bool(context["previous"].get("facts",{}).get("closing_at",{}).get("notice_conflict"))


def source_windows(excerpts):
    windows={}
    for e in excerpts: windows.setdefault(e["anchor_id"],[]).append(e["quote"])
    return windows


def exact_support(citation,windows):
    return any(citation["quote"] in quote for quote in windows.get(citation["anchor_id"],[]))


def tender_overview_windows(context):
    return source_windows(e for e in context["excerpts"]+context.get("overview_excerpts",[])
        if e.get("source_role") in {"tender","addendum"}
        and e.get("source_index_version")==context["pins"]["source_index_version"])


def supported_closing(value,citations,anchors):
    date=datetime.fromisoformat(value)
    if date.utcoffset() is None or not citations: raise ValueError()
    local=date.astimezone(ZoneInfo("Asia/Singapore"))
    def key(text): return re.sub(r"[^a-z0-9]","",text.casefold())
    patterns=[local.strftime("%Y-%m-%dT%H:%M")]
    for month in ("%b","%B"):
        for day in (local.strftime("%d"),str(local.day)):
            for time in (local.strftime("%H:%M"),local.strftime("%I:%M%p"),
                         str(local.hour%12 or 12)+local.strftime(":%M%p")):
                patterns.append(day+" "+local.strftime(month+" %Y")+" "+time)
    for cite in citations:
        quote=cite["quote"]
        if not exact_support(cite,anchors): raise ValueError()
        if not re.search(r"clos(e|ing)|deadline|submit",quote,re.I): raise ValueError()
        iso=re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})",quote)
        if iso:
            if len(iso)!=1 or datetime.fromisoformat(iso[0].replace("Z","+00:00"))!=date: raise ValueError()
        elif re.search(r"UTC|GMT|[+-]\d{2}:\d{2}",quote,re.I) or not any(key(pattern) in key(quote) for pattern in patterns):
            raise ValueError()
    return date.isoformat()


def validate_summary(summary:QualificationSummary|None,context:dict)->dict|None:
    if summary is None: return None
    anchors=tender_overview_windows(context)
    result=summary.model_dump(mode="json")
    for fact in result.values():
        if any(not exact_support(c,anchors) for c in fact["citations"]):
            raise ValueError("Summary support must come from the pinned tender excerpts.")
    return result


def validate_interpretation(raw,context):
    try:
        parsed=Interpretation.model_validate(raw)
        result=parsed.model_dump(mode="json")
        result["summary"]=validate_summary(parsed.summary,context)
        findings=result["findings"]
        if len({f["id"] for f in findings})!=len(findings): raise ValueError()
        tender=source_windows(context["excerpts"])
        # Overview reads are separately role/index checked; never join disjoint source windows.
        for anchor,windows in tender_overview_windows(context).items(): tender.setdefault(anchor,[]).extend(windows)
        company=source_windows(context["company_excerpts"])
        company_meta={e["anchor_id"]:e for e in context["company_excerpts"]}
        answers={a["id"]:a for a in context["answers"]}
        if result["closing_at"] is not None:
            result["closing_at"]=supported_closing(result["closing_at"],result["closing_citations"],tender)
            if context.get("closing_at") and datetime.fromisoformat(result["closing_at"])!=datetime.fromisoformat(context["closing_at"]):
                result["closing_conflict_citations"]=result["closing_citations"]
                result.update(closing_at=None,closing_citations=[],needs_wider_review=True,
                    wider_review_reason="The cited closing time conflicts with the pinned notice; resolve the current amendment.")

        issues=result["overview_issues"]
        if len({i["field"] for i in issues})!=len(issues): raise ValueError()
        for issue in issues:
            if any(not exact_support(c,tender_overview_windows(context)) for c in issue["citations"]): raise ValueError()
            fact=(result["summary"] or {}).get(issue["field"])
            if (issue["field"]=="closing_at" and result["closing_at"] is not None) or (fact and fact["value"] is not None): raise ValueError()
            if issue["field"]=="closing_at" and issue["kind"]=="not_established" and context.get("closing_at") and not retained_notice_conflict(context): raise ValueError()
            if issue["kind"]=="conflicting":
                passages={(c["anchor_id"],c["quote"].strip()) for c in issue["citations"]}
                if not any(a!=b and (a[0]!=b[0] or (a[1] not in b[1] and b[1] not in a[1])) for a in passages for b in passages): raise ValueError()
                result.update(needs_wider_review=True,wider_review_reason=issue["question"])

        for f in findings:
            for citations,anchors in ((f["tender_citations"],tender),(f["company_citations"],company)):
                if any(not exact_support(c,anchors) for c in citations):
                    raise ValueError()
            if f["critical"] and (not f["critical_basis"] or not any(f["critical_basis"] in c["quote"] for c in f["tender_citations"])):
                raise ValueError()
            if f["preparation_role"] in {"preparation_work","future_duty"}:
                if not conditional_preparation(f) or not any(f["preparation_basis"] in c["quote"] for c in f["tender_citations"]): raise ValueError()
                timing={"submission":r"submi|tender|bid","award":r"award|appoint",
                    "mobilisation":r"mobili[sz]|commenc","delivery":r"deliver|during|throughout|contractor"}
                if not re.search(timing[f["due_stage"]],f["preparation_basis"],re.I): raise ValueError()
                if any(re.search(r"eligib|disqualif|exclu|reject|not be considered|not be evaluated|minimum.+(?:score|threshold)|"
                       r"registr|licen[cs]|debar|suspend|net\s+worth|working\s+capital",c["quote"],re.I)
                       for c in f["tender_citations"]): raise ValueError()
            usable=[]
            for key in f["answer_ids"]:
                answer=answers.get(key)
                if not answer or f["id"] not in answer["finding_ids"] or answer["source_signature"]!=context["pins"]["source_signature"] or answer.get("finding_scopes",{}).get(f["id"])!=finding_scope(f):
                    raise ValueError()
                usable.append(answer)
            if f["status"]!="unconfirmed":
                company_ok=bool(f["company_citations"]) and not set(context["company_gaps"])&{
                    "EVIDENCE_EXPIRED","EVIDENCE_NOT_EFFECTIVE","ENTITY_UNCONFIRMED","CAPACITY_NOT_PROVEN","DELIVERY_NOT_PROVEN"}
                required=datetime.fromisoformat(result.get("closing_at") or context["closing_at"]).date() if result.get("closing_at") or context.get("closing_at") else datetime.now(timezone.utc).date()
                for cite in f["company_citations"]:
                    evidence=company_meta[cite["anchor_id"]]
                    if evidence.get("expires_on") and date.fromisoformat(evidence["expires_on"])<required: company_ok=False
                    if evidence.get("effective_on") and date.fromisoformat(evidence["effective_on"])>datetime.now(timezone.utc).date(): company_ok=False
                if f["kind"]=="delivery_commitment": company_ok=False
                answer_ok=any(a["basis"] and a["response_kind"]==("confirmed" if f["status"]=="supported" else "denied") for a in usable)
                if not company_ok and not answer_ok: f["status"]="unconfirmed"
        affected=context.get("affected_ids")
        previous=context.get("previous")
        if same_tender_sources(context) and any(i["kind"]=="conflicting" and i not in issues for i in previous.get("overview_issues",[])):
            raise DomainError(422,"SCREENING_DEPENDENCY_WIDER_REQUIRED","A known source conflict requires source clarification; an unrelated answer cannot erase it.")
        if previous and previous.get("pins",context["pins"]).get("source_signature")==context["pins"]["source_signature"]:
            old={f["id"]:f for f in previous["findings"]}
            if any(f["id"] in old and (affected is not None or old[f["id"]]["critical"])
                   and finding_scope(f)!=finding_scope(old[f["id"]]) for f in findings):
                raise DomainError(422,"SCREENING_DEPENDENCY_WIDER_REQUIRED","An answer cannot reclassify a known obligation or remove its decision safeguards.")
        if (affected is None and previous and previous.get("pins",context["pins"]).get("source_signature")==context["pins"]["source_signature"]
            and not {f["id"] for f in previous["findings"] if f["critical"]}<={f["id"] for f in findings}):
            raise DomainError(422,"SCREENING_DEPENDENCY_WIDER_REQUIRED","A known critical condition cannot disappear without a source-backed wider review.")
        if affected is not None and previous:
            expected={f["id"] for f in previous["findings"] if f["id"] in affected}
            if {f["id"] for f in findings}!=expected:
                raise DomainError(422,"SCREENING_DEPENDENCY_WIDER_REQUIRED","The answer does not authorise changes to unrelated findings.")
            retained=[deepcopy(f) for f in previous["findings"] if f["id"] not in affected]
            result["findings"]=retained+findings
            if len(result["findings"])>24: raise ValueError()
        return result
    except (ValidationError,KeyError,ValueError,TypeError):
        raise DomainError(422,"SCREENING_INVALID","The candidate has invalid source support, scope or schema.") from None


def reviewed_coverage(context):
    coverage=deepcopy(context["coverage"])
    coverage["source_complete"]=coverage["complete"]
    for gap in coverage["gaps"]:
        original={k:v for k,v in gap.items() if k not in {"gap_id","materiality","review_answer_id"}}
        gap["gap_id"]=hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
        for answer in context["answers"]:
            if (gap.get("document_version_id") and gap["gap_id"] in answer.get("coverage_refs",[])
                and answer["source_signature"]==context["pins"]["source_signature"]
                and answer["response_kind"]=="confirmed" and answer.get("basis")):
                gap.update(materiality="reviewed_nonmaterial",review_answer_id=answer["id"])
    return coverage


def screening_artifact(context,interpretation,usage,attention=None):
    coverage=reviewed_coverage(context)
    previous=context.get("previous")
    same_source=same_tender_sources(context)
    retained_conflicts=([i for i in previous.get("overview_issues",[]) if i["kind"]=="conflicting"]
        if same_source else [])
    issues=deepcopy(interpretation.get("overview_issues",retained_conflicts))
    notice_conflict=bool(interpretation.get("closing_conflict_citations") or retained_notice_conflict(context))
    if notice_conflict and not any(i["field"]=="closing_at" for i in issues):
        old_issue=next((i for i in previous.get("overview_issues",[]) if i["field"]=="closing_at"),None) if same_source else None
        issues.append(deepcopy(old_issue) if old_issue else {"field":"closing_at","kind":"not_established",
            "question":"Resolve the cited tender deadline against the pinned notice; obtain the applicable source clarification or amendment.",
            "citations":interpretation.get("closing_conflict_citations",[])})
    coverage["requires_wider_review"]|=interpretation["needs_wider_review"] or notice_conflict or any(i["kind"]=="conflicting" for i in issues)
    findings=interpretation["findings"]
    blockers=[]
    unresolved=[g for g in coverage["gaps"] if g.get("materiality")!="reviewed_nonmaterial"]
    coverage["complete"]=not coverage["requires_wider_review"] and not unresolved
    if coverage["requires_wider_review"] or unresolved: blockers.append("CRITICAL_COVERAGE_UNKNOWN")
    if any(f["critical"] and f["status"]!="supported" and not conditional_preparation(f) for f in findings): blockers.append("CRITICAL_CONDITION_UNRESOLVED")
    closing_conflict=notice_conflict or any(i["field"]=="closing_at" and i["kind"]=="conflicting" for i in issues)
    closing=None if closing_conflict else interpretation.get("closing_at") or context.get("closing_at")
    if closing is None: blockers.append("CLOSING_UNKNOWN")
    elif datetime.fromisoformat(closing)<=datetime.now(timezone.utc): blockers.append("CLOSING_PASSED")
    company_gaps=list(context["company_gaps"])
    required=datetime.fromisoformat(closing).date() if closing else datetime.now(timezone.utc).date()
    if any(e.get("expires_on") and date.fromisoformat(e["expires_on"])<required for e in context["company_excerpts"]):
        if "EVIDENCE_EXPIRED" not in company_gaps: company_gaps.append("EVIDENCE_EXPIRED")
    if not findings: blockers.append("FINDINGS_NOT_ESTABLISHED")
    if attention: blockers.append(attention)
    recommendation=("outside_policy" if any(f["critical"] and f["status"]=="evidenced_failure" for f in findings)
                    else "needs_information" if blockers else "promising")
    drafts=[{"draft_ref":"finding:"+f["id"],"purpose":"screening_input","finding_ids":[f["id"]],
        "suggested_role":"service_reviewer","owner_function":f["owner_function"],
        "question":f["request_question"]} for f in findings if f["status"]=="unconfirmed" and not conditional_preparation(f)
            and (f["critical"] or f["material_now"] is not False)]
    questions={"buyer":"Confirm the contracting buyer from the current tender notice or cover.",
        "reference":"Confirm the tender reference from the current tender notice or cover.",
        "scope":"Confirm the services and material scope exclusions from the current tender pack.",
        "contract_period":"Confirm the base contract period, options and commencement basis from the current tender pack.",
        "sites":"Confirm the named sites and any phased commencement or decommissioning that affects delivery.",
        "closing_at":"Confirm the current closing date and time, including the applicable notice or amendment."}
    for field,question in questions.items():
        if any(i["field"]==field for i in issues): continue
        fact=(interpretation.get("summary") or {}).get(field,{})
        if (field=="closing_at" and closing is None) or (field!="closing_at" and fact.get("value") is None):
            issues.append({"field":field,"kind":"not_established","question":question,"citations":[]})
    drafts.extend({"draft_ref":"overview:"+i["field"],"purpose":"screening_input","finding_ids":[],
        "coverage_refs":[],"overview_field":i["field"],"suggested_role":"service_reviewer",
        "owner_function":"operations" if i["field"] in {"scope","sites"} else "bid_team","question":i["question"]} for i in issues)
    reviewable=[g for g in unresolved if g.get("document_version_id")][:8]
    if reviewable:
        regions="; ".join((g.get("filename","Source")+": "+g.get("location_label","specified region"))[:170] for g in reviewable)
        drafts.append({"draft_ref":"coverage_review","purpose":"screening_input","finding_ids":[],
            "coverage_refs":[g["gap_id"] for g in reviewable],"suggested_role":"service_reviewer","owner_function":"bid_team",
            "question":"Inspect these exact unread regions and confirm whether they add NO unrepresented material entry condition or preparation risk. "
                "A confirmation requires a recorded inspection basis; otherwise deny or mark unable to confirm. Regions: "+regions})
    if coverage["requires_wider_review"]:
        drafts.append({"draft_ref":"wider_review","purpose":"screening_input","finding_ids":[],"coverage_refs":[],
            "suggested_role":"service_reviewer","owner_function":"bid_team",
            "question":"Identify the specific missing source or bounded source regions needing wider investigation. "
                "This input does not confirm eligibility or unrelated obligations."})
    drafts.append({"draft_ref":"preparation","purpose":"preparation_approval","finding_ids":[],
        "suggested_role":"approver","owner_function":"bid_team",
        "question":"Review this exact preparation brief and approve a scope/budget, request information, or decline."})
    return {"schema_version":"screening.v1","pins":context["pins"],"title":context["title"],"closing_at":closing,
        "summary":interpretation.get("summary"),
        "overview_issues":issues,"preparation_condition_ids":[f["id"] for f in findings if requires_preparation_condition(f)],
        "facts":{"closing_at":{"value":closing,"notice_version_id":context["pins"].get("notice_version_id"),
            "notice_conflict":notice_conflict,
            "citations":[] if closing_conflict else interpretation.get("closing_citations") or context.get("closing_citations",[])}} ,
        "company_evidence":{"accepted_version_id":context["pins"].get("company_version_id"),"gaps":company_gaps,
            "dates":[{k:e.get(k) for k in ("anchor_id","effective_on","expires_on")} for e in context["company_excerpts"]]},
        "findings":findings,"coverage":coverage,"recommendation":recommendation,"approval_blockers":blockers,
        "request_drafts":drafts,"work_packages":[{"owner_function":owner,"finding_ids":[f["id"] for f in findings
            if f["owner_function"]==owner and f["status"]=="unconfirmed"]} for owner in sorted({f["owner_function"] for f in findings})],
        "wider_review_reason":interpretation["wider_review_reason"],"usage":usage,"attention":attention}


async def run_screening(pinned_context,decisions_client,reasoning_client,budget_ledger):
    context=pinned_context;hints=[];attention=None
    model=getattr(decisions_client,"model","controlled")
    cached={(e["excerpt_key"],e["model"],e["rubric_version"]):e for e in context.get("cached_classifications",[])
            if e.get("source_signature")==context["pins"]["source_signature"]}
    entries=list(cached.values())[-8:]
    try:
        selected=[] if context.get("affected_ids") is not None or context.get("answer_driven") else context["excerpts"][:4]
        for position,excerpt in enumerate(selected):
            key=hashlib.sha256(json.dumps([excerpt["anchor_id"],excerpt["quote"]],ensure_ascii=False).encode()).hexdigest()
            cached=next((e for e in entries if e["excerpt_key"]==key and e["model"]==model and e["rubric_version"]=="screening-v1"),None)
            if cached: hints.append(cached["result"]);continue
            result=await decisions_client.classify_excerpt(excerpt,[
                {"name":"kind","instructions":"Separate entry, scoring, bid artifacts and later delivery; do not infer compliance.",
                 "choices":["eligibility","scored_criterion","bid_artifact","delivery_commitment","informational","unknown"]}],
                "screening-v1",context["budget_id"],f"screening:{context['job_id']}:{context['attempt']}:classify:{position}")
            hints.append(result)
            entries.append({"excerpt_key":key,"source_signature":context["pins"]["source_signature"],
                            "rubric_version":"screening-v1","model":model,"result":result})
            entries=entries[-8:]
            if context.get("_checkpoint"): await context["_checkpoint"](entries)
        raw=await reasoning_client.interpret(context,hints)
        interpretation=validate_interpretation(raw,context)
    except DomainError as error:
        if error.code not in {"STAGE_BUDGET_EXHAUSTED","STAGE_REQUEST_LIMIT","STAGE_RESPONSES_LIMIT","STAGE_INPUT_LIMIT",
                              "WORKSPACE_BUDGET_EXHAUSTED","USAGE_BUDGET_REQUIRED",
                              "MODEL_PRICING_MISSING","DECISIONS_MODEL_NOT_CONFIGURED","SCREENING_DEPENDENCY_WIDER_REQUIRED",
                              "SCREENING_INPUT_LIMIT","SCREENING_PROVIDER_UNAVAILABLE"}:
            error.classifications=entries
            raise
        attention=error.code
        previous=context.get("previous")
        retained=bool(previous and previous.get("pins",context["pins"]).get("source_signature")==context["pins"]["source_signature"])
        interpretation={"findings":deepcopy(previous["findings"]) if retained else [],
                        "needs_wider_review":True,"wider_review_reason":"Bounded investigation stopped; retain uncertainty and review a bounded wider scope."}
    usage=await budget_ledger.summary(context["budget_id"],context.get("_actor"))
    artifact=screening_artifact(context,interpretation,usage,attention)
    artifact["classifications"]=entries
    return artifact


class ScreeningArtifact(Strict):
    schema_version:Literal["screening.v1"]
    pins:dict
    title:str
    closing_at:str|None
    summary:QualificationSummary|None=None
    overview_issues:list[OverviewIssue]=Field(default_factory=list)
    preparation_condition_ids:list[str]|None=None
    findings:list[Finding]
    facts:dict
    company_evidence:dict
    coverage:dict
    recommendation:Literal["promising","outside_policy","needs_information"]
    approval_blockers:list[str]
    request_drafts:list[dict]
    work_packages:list[dict]
    wider_review_reason:str|None
    usage:dict
    attention:str|None
    classifications:list[dict]
