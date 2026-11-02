"""Bounded, source-bound screening candidates; business authority stays with people."""
from copy import deepcopy
from datetime import date,datetime,timezone
import hashlib
import json
import re
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator

from app.m1.policy import DomainError

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


class Interpretation(Strict):
    findings:list[Finding]=Field(max_length=24)
    needs_wider_review:bool
    wider_review_reason:str|None=Field(max_length=2000)
    closing_at:str|None
    closing_citations:list[Support]=Field(max_length=2)


def finding_scope(finding):
    return hashlib.sha256(json.dumps([finding["kind"],finding["due_stage"],
        sorted((c["anchor_id"],c["quote"]) for c in finding["tender_citations"])],sort_keys=True).encode()).hexdigest()


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
        if cite["anchor_id"] not in anchors or quote not in anchors[cite["anchor_id"]]: raise ValueError()
        if not re.search(r"clos(e|ing)|deadline|submit",quote,re.I): raise ValueError()
        iso=re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})",quote)
        if iso:
            if len(iso)!=1 or datetime.fromisoformat(iso[0].replace("Z","+00:00"))!=date: raise ValueError()
        elif re.search(r"UTC|GMT|[+-]\d{2}:\d{2}",quote,re.I) or not any(key(pattern) in key(quote) for pattern in patterns):
            raise ValueError()
    return date.isoformat()


def validate_interpretation(raw,context):
    try:
        result=Interpretation.model_validate(raw).model_dump(mode="json")
        findings=result["findings"]
        if len({f["id"] for f in findings})!=len(findings): raise ValueError()
        tender={e["anchor_id"]:e["quote"] for e in context["excerpts"]}
        company={e["anchor_id"]:e["quote"] for e in context["company_excerpts"]}
        company_meta={e["anchor_id"]:e for e in context["company_excerpts"]}
        answers={a["id"]:a for a in context["answers"]}
        if result["closing_at"] is not None:
            result["closing_at"]=supported_closing(result["closing_at"],result["closing_citations"],tender)
            if context.get("closing_at") and datetime.fromisoformat(result["closing_at"])!=datetime.fromisoformat(context["closing_at"]):
                result.update(closing_at=None,closing_citations=[],needs_wider_review=True,
                    wider_review_reason="The cited closing time conflicts with the pinned notice; resolve the current amendment.")

        for f in findings:
            for citations,anchors in ((f["tender_citations"],tender),(f["company_citations"],company)):
                if any(c["anchor_id"] not in anchors or c["quote"] not in anchors[c["anchor_id"]] for c in citations):
                    raise ValueError()
            if f["critical"] and (not f["critical_basis"] or not any(f["critical_basis"] in c["quote"] for c in f["tender_citations"])):
                raise ValueError()
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
    coverage["requires_wider_review"]|=interpretation["needs_wider_review"]
    findings=interpretation["findings"]
    blockers=[]
    unresolved=[g for g in coverage["gaps"] if g.get("materiality")!="reviewed_nonmaterial"]
    coverage["complete"]=not coverage["requires_wider_review"] and not unresolved
    if coverage["requires_wider_review"] or unresolved: blockers.append("CRITICAL_COVERAGE_UNKNOWN")
    if any(f["critical"] and f["status"]!="supported" for f in findings): blockers.append("CRITICAL_CONDITION_UNRESOLVED")
    closing=interpretation.get("closing_at") or context.get("closing_at")
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
        "question":f["request_question"]} for f in findings if f["status"]=="unconfirmed" and (f["critical"] or f["material_now"] is not False)]
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
        "facts":{"closing_at":{"value":closing,"notice_version_id":context["pins"].get("notice_version_id"),
            "citations":interpretation.get("closing_citations") or context.get("closing_citations",[])}} ,
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
