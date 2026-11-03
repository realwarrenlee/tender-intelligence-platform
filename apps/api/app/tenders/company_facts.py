"""Read-only, dated evidence projection of the accepted Company source."""
from datetime import date
import json
import re
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field
from typing import Literal

from app.tenders.assessments import current_company
from app.tenders.policy import DomainError
from app.tenders.repository import Repository


class FactRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    query:str=Field(min_length=1,max_length=512)
    entity:str=Field(min_length=1,max_length=200)
    as_of:date
    required_on:date|None=None
    purpose:Literal["capability","completed_delivery","current_capacity"]="capability"


class CompanyFacts:
    def __init__(self,pool): self.pool=pool

    async def lookup_company_facts(self,request,accepted_company_version,actor_scope):
        args=FactRequest.model_validate(request)
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            await Repository(self.pool)._member(c,actor_scope)
            row=await c.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind='company_evidence'",
                                actor_scope.workspace_id,UUID(str(accepted_company_version)))
            if row is None: raise DomainError(404,"NOT_FOUND","Company evidence not found.")
            current=await current_company(c,actor_scope.workspace_id)
            if current["id"]!=row["id"]:
                raise DomainError(409,"STALE_COMPANY_EVIDENCE","Use the current accepted Company version.")
            payload=json.loads(row["payload"]);gaps=[];excerpts=[]
            effective=date.fromisoformat(payload["effective_on"])
            expires=date.fromisoformat(payload["expires_on"]) if payload.get("expires_on") else None
            if effective>args.as_of: gaps.append("EVIDENCE_NOT_EFFECTIVE")
            if expires and expires<(args.required_on or args.as_of): gaps.append("EVIDENCE_EXPIRED")
            terms=re.findall(r"\w+",args.query.casefold())
            truncated=False
            for anchor in payload["parsed"]["anchors"]:
                if not all(term in anchor["text"].casefold() for term in terms): continue
                if args.entity.casefold() not in anchor["text"].casefold() and "ENTITY_UNCONFIRMED" not in gaps:
                    gaps.append("ENTITY_UNCONFIRMED")
                if len(excerpts)>=8:
                    truncated=True;continue
                quote=anchor["text"][:2000]
                truncated|=len(quote)<len(anchor["text"])
                excerpts.append({"anchor_id":anchor["anchor_id"],"document_version_id":str(row["id"]),
                    "quote":quote,"effective_on":effective.isoformat(),
                    "expires_on":expires.isoformat() if expires else None,
                    **{k:anchor[k] for k in ("page","paragraph","location_label") if k in anchor}})
            if not excerpts: gaps.append("NO_ACCEPTED_EVIDENCE")
            # A public award or a historic capability statement is not delivery/capacity assurance.
            if args.purpose=="completed_delivery": gaps.append("DELIVERY_NOT_PROVEN")
            if args.purpose=="current_capacity": gaps.append("CAPACITY_NOT_PROVEN")
            # shortcut: Company is free-form prose; confirming facts needs scoped interpretation/accepted structured evidence.
            if excerpts and not gaps: gaps.append("FACT_INTERPRETATION_REQUIRED")
            return {"accepted_company_version":str(row["id"]),"as_of":args.as_of.isoformat(),"excerpts":excerpts,
                "gaps":gaps,"confirms_requested_fact":False,"truncated":truncated,
                "provenance":payload.get("profile",{}).get("sources",[])}
