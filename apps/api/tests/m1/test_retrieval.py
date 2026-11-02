"""Whole-corpus retrieval preserves native locations, source scope and coverage."""
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.m1.policy import DomainError
from test_documents import create


async def seed_parsed(case, documents, parser="controlled-native-v1",pack_error=None):
    manifest=[];parsed=[]
    async with case.app.state.pool.acquire() as db:
        revision=await db.fetchval("SELECT input_revision FROM m1_app.tenders WHERE id=$1",UUID(case.tender["id"]))
        for source in documents:
            version=uuid4()
            text=source.get("text","")
            digest=source.get("sha256",hashlib.sha256(text.encode()).hexdigest())
            original=source.get("parsed")
            if original:
                old=original["document_version_id"]
                anchors=[{**a,"anchor_id":str(version)+a["anchor_id"][len(old):],"document_version_id":str(version)} for a in original["anchors"]]
                locations=original["locations"];status=original["status"]
            else:
                anchors=[{"anchor_id":str(version)+"-paragraph-1","document_version_id":str(version),
                    "source_role":"tender","paragraph":1,"location_label":source.get("location","Paragraph 1"),"text":text}]
                status=source.get("status","complete")
                locations=[{"paragraph":1,"status":status,"location_label":source.get("location","Paragraph 1")}]
            await db.execute("""
                INSERT INTO m1_app.document_versions(id,workspace_id,tender_id,filename,sha256,storage_key,role)
                VALUES($1,$2,$3,$4,$5,$6,'tender')
            """,version,case.actor.workspace_id,UUID(case.tender["id"]),source["filename"],digest,"index-fixture/"+str(version))
            manifest.append({"id":str(version),"filename":source["filename"],"sha256":digest,"role":"tender"})
            parsed.append({"document_version_id":str(version),"source_role":"tender","sha256":digest,
                "status":status,"error_code":None if status=="complete" else "SOURCE_INCOMPLETE","locations":locations,"anchors":anchors})
        return await db.fetchval("""
            INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by)
            VALUES($1,$2,'parsed_sources',$3,$4::jsonb,$5::jsonb,$6) RETURNING id
        """,case.actor.workspace_id,UUID(case.tender["id"]),revision,json.dumps({"documents":manifest}),
            json.dumps({"parser":parser,"complete":all(d["status"]=="complete" for d in parsed) and not pack_error,"documents":parsed,"error_code":pack_error}),case.actor.user_id)


@pytest.fixture
def index_case(client,actors):
    from app.m1.retrieval import SourceIndex
    http,_,app=client
    case=SimpleNamespace(http=http,app=app,actor=actors["owner"],tender=create(http))
    case.index=SourceIndex(app.state.pool)
    return case


def test_gate_in_appendix_or_sheet_is_retrievable(index_case,tmp_path):
    from openpyxl import Workbook
    from app.m1.documents import parse_document
    c=index_case
    book=Workbook();book.active.title="Pricing"
    book.active["A1"]="Routine quantities"
    hidden=book.create_sheet("Appendix conditions");hidden.sheet_state="hidden"
    hidden["B7"]="Mandatory FM01 registration before submission."
    path=tmp_path/"price-schedule.xlsx";book.save(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    native=parse_document(path,str(uuid4()),"tender",digest)
    source=c.http.portal.call(seed_parsed,c,[
        {"filename":"instructions.pdf","text":"General facilities maintenance scope."},
        {"filename":"appendix.pdf","text":"Tenderers must hold a valid security licence before submission.","location":"Appendix C, note 4"},
        {"filename":path.name,"parsed":native,"sha256":digest}])
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    for query,needle in [("security licence","Appendix C"),("FM01","Appendix conditions")]:
        result=c.http.portal.call(c.index.retrieve,query,version["id"],c.actor,3000)
        assert result["excerpts"] and needle in result["excerpts"][0]["location_label"]
        assert result["excerpts"][0]["quote"] in ("Tenderers must hold a valid security licence before submission." if query=="security licence" else native["anchors"][-1]["text"])
    assert len(version["inventory"])==3


def test_foreign_workspace_anchor_is_denied(index_case,actors):
    c=index_case
    source=c.http.portal.call(seed_parsed,c,[{"filename":"appendix.pdf","text":"Foreign secret obligation."}])
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    for operation,args in [(c.index.retrieve,("secret",version["id"],actors["other"],1000)),
                           (c.index.index_sources,(actors["other"],source,"controlled-native-v1"))]:
        with pytest.raises(DomainError) as error: c.http.portal.call(operation,*args)
        assert error.value.code=="NOT_FOUND"


def test_extraction_reuse_requires_same_hash_and_parser_and_keeps_originals(index_case):
    c=index_case
    docs=[{"filename":"one.pdf","text":"Mandatory licence condition."},{"filename":"duplicate.pdf","text":"Mandatory licence condition."}]
    source=c.http.portal.call(seed_parsed,c,docs)
    first=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    replay=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    assert first["id"]==replay["id"]
    assert len(first["inventory"])==2
    assert first["inventory"][1]["duplicate_of"]==first["inventory"][0]["document_version_id"]
    async def count():
        async with c.app.state.pool.acquire() as db:
            return await db.fetchval("SELECT count(*) FROM m1_app.source_extractions WHERE workspace_id=$1",c.actor.workspace_id)
    assert c.http.portal.call(count)==1
    newer=c.http.portal.call(seed_parsed,c,[docs[0]],"controlled-native-v2")
    c.http.portal.call(c.index.index_sources,c.actor,newer,"controlled-native-v2")
    assert c.http.portal.call(count)==2
    changed=c.http.portal.call(seed_parsed,c,[{"filename":"one.pdf","text":"Different mandatory condition."}])
    c.http.portal.call(c.index.index_sources,c.actor,changed,"controlled-native-v1")
    assert c.http.portal.call(count)==3
    with pytest.raises(DomainError) as error:
        c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v3")
    assert error.value.code=="PARSER_VERSION_MISMATCH"
    result=c.http.portal.call(c.index.retrieve,"licence",first["id"],c.actor,3000)
    assert len({a["document_version_id"] for a in result["excerpts"]})==2
    assert all(a["anchor_id"].startswith(a["document_version_id"]+"-") for a in result["excerpts"])


def test_partial_critical_regions_stay_unknown_even_without_matches(index_case):
    c=index_case
    source=c.http.portal.call(seed_parsed,c,[{"filename":"annex.pdf","text":"Unread drawing labels.","status":"partial","location":"Annex eligibility diagram"}])
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    result=c.http.portal.call(c.index.retrieve,"licence",version["id"],c.actor,1000)
    assert result["excerpts"]==[]
    assert not result["coverage"]["complete"]
    assert result["coverage"]["gaps"][0]["materiality"]=="unknown"
    assert result["coverage"]["gaps"][0]["filename"]=="annex.pdf"


def test_bounded_excerpts_do_not_discard_stored_text_and_stale_indices_are_rejected(index_case):
    c=index_case
    text="Routine information. "*1000+"Hidden mandatory registration condition."
    source=c.http.portal.call(seed_parsed,c,[{"filename":"appendix.pdf","text":text}])
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    result=c.http.portal.call(c.index.retrieve,"registration",version["id"],c.actor,800)
    assert "registration" in result["excerpts"][0]["quote"]
    assert result["excerpts"][0]["quote"] in text
    assert len(json.dumps(result["excerpts"],ensure_ascii=False).encode())<=800
    assert result["truncated"]
    async def amend():
        async with c.app.state.pool.acquire() as db:
            assert await db.fetchval("SELECT payload->'documents'->0->'anchors'->0->>'text' FROM m1_app.artifact_versions WHERE id=$1",source)==text
            await db.execute("UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1",UUID(c.tender["id"]))
    c.http.portal.call(amend)
    with pytest.raises(DomainError) as error:
        c.http.portal.call(c.index.retrieve,"registration",version["id"],c.actor,800)
    assert error.value.code=="STALE_SOURCE_INDEX"


async def seed_company(case,text,effective="2026-01-01",expires=None):
    version=uuid4()
    payload={"effective_on":effective,"expires_on":expires,"profile":{"content":text,"sources":[]},
        "document":{"filename":"Company.docx","storage_key":"index-fixture/company"},
        "parsed":{"anchors":[{"anchor_id":str(version)+"-paragraph-1","document_version_id":str(version),
            "source_role":"company_evidence","paragraph":1,"text":text}]}}
    async with case.app.state.pool.acquire() as db:
        await db.execute("""
            INSERT INTO m1_app.artifact_versions(id,workspace_id,kind,manifest,payload,created_by)
            VALUES($1,$2,'company_evidence','{}',$3::jsonb,$4)
        """,version,case.actor.workspace_id,json.dumps(payload),case.actor.user_id)
    return version


@pytest.mark.parametrize("text,expires,purpose,gap",[
    ("CBM Pte. Ltd. holds ISO9001.", "2026-10-29","capability","EVIDENCE_EXPIRED"),
    ("CBM Qatar holds ISO9001.",None,"capability","ENTITY_UNCONFIRMED"),
    ("CBM Pte. Ltd. was awarded the facilities contract.",None,"completed_delivery","DELIVERY_NOT_PROVEN"),
    ("CBM Pte. Ltd. has historic staffing information.",None,"current_capacity","CAPACITY_NOT_PROVEN"),
])
def test_company_facts_expose_expiry_affiliates_and_award_limits(index_case,text,expires,purpose,gap):
    from app.m1.company_facts import CompanyFacts
    c=index_case
    version=c.http.portal.call(seed_company,c,text,"2026-01-01",expires)
    request={"query":"ISO9001" if "ISO9001" in text else "facilities" if "facilities" in text else "staffing",
        "entity":"CBM Pte. Ltd.","as_of":"2026-10-30","purpose":purpose}
    result=c.http.portal.call(CompanyFacts(c.app.state.pool).lookup_company_facts,request,version,c.actor)
    assert gap in result["gaps"]
    assert result["excerpts"][0]["quote"]==text
    assert result["accepted_company_version"]==str(version)
    assert not result["confirms_requested_fact"]


def test_company_facts_are_scoped_to_the_current_accepted_version(index_case,actors):
    from app.m1.company_facts import CompanyFacts
    c=index_case
    service=CompanyFacts(c.app.state.pool)
    old=c.http.portal.call(seed_company,c,"CBM Pte. Ltd. provides engineering services.")
    new=c.http.portal.call(seed_company,c,"CBM Pte. Ltd. provides facilities services.")
    request={"query":"facilities","entity":"CBM Pte. Ltd.","as_of":"2026-10-30","purpose":"capability"}
    result=c.http.portal.call(service.lookup_company_facts,request,new,c.actor)
    assert result["excerpts"] and result["gaps"]==["FACT_INTERPRETATION_REQUIRED"]
    for version,actor,code in [(old,c.actor,"STALE_COMPANY_EVIDENCE"),(new,actors["other"],"NOT_FOUND")]:
        with pytest.raises(DomainError) as error:
            c.http.portal.call(service.lookup_company_facts,request,version,actor)
        assert error.value.code==code

def test_accepted_free_form_statement_does_not_confirm_a_negated_fact(index_case):
    from app.m1.company_facts import CompanyFacts
    c=index_case
    version=c.http.portal.call(seed_company,c,"CBM Pte. Ltd. does not have confirmed ISO9001 certification.")
    result=c.http.portal.call(CompanyFacts(c.app.state.pool).lookup_company_facts,
        {"query":"ISO9001","entity":"CBM Pte. Ltd.","as_of":"2026-10-30","purpose":"capability"},version,c.actor)
    assert not result["confirms_requested_fact"]
    assert "FACT_INTERPRETATION_REQUIRED" in result["gaps"]

def test_pack_level_parser_limit_cannot_report_complete_coverage(index_case):
    c=index_case
    source=c.http.portal.call(seed_parsed,c,[{"filename":"notice.pdf","text":"A registration condition."}],
        "controlled-native-v1","CHARACTER_LIMIT")
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    result=c.http.portal.call(c.index.retrieve,"registration",version["id"],c.actor,1500)
    assert not result["coverage"]["complete"]
    assert any(gap.get("error_code")=="CHARACTER_LIMIT" for gap in result["coverage"]["gaps"])

def test_concurrent_indices_share_cache_without_lock_order_deadlock(index_case):
    import asyncio
    c=index_case
    other=SimpleNamespace(http=c.http,app=c.app,actor=c.actor,tender=create(c.http))
    a={"filename":"a.pdf","text":"First mandatory licence."}
    b={"filename":"b.pdf","text":"Second registration condition."}
    first=c.http.portal.call(seed_parsed,c,[a,b])
    second=c.http.portal.call(seed_parsed,other,[b,a])
    async def run():
        # Warm both connections so competing transactions start together.
        async with c.app.state.pool.acquire(),c.app.state.pool.acquire(): pass
        return await asyncio.gather(
            c.index.index_sources(c.actor,first,"controlled-native-v1"),
            c.index.index_sources(c.actor,second,"controlled-native-v1"))
    result=c.http.portal.call(run)
    assert len(result)==2 and result[0]["id"]!=result[1]["id"]

def test_failed_extraction_does_not_poison_later_recovery(index_case):
    c=index_case
    text="Recovered registration evidence."
    digest=hashlib.sha256(text.encode()).hexdigest()
    failed=c.http.portal.call(seed_parsed,c,[{"filename":"annex.pdf","text":"","sha256":digest,"status":"failed"}])
    first=c.http.portal.call(c.index.index_sources,c.actor,failed,"controlled-native-v1")
    assert not c.http.portal.call(c.index.retrieve,"registration",first["id"],c.actor,1500)["coverage"]["complete"]
    recovered=c.http.portal.call(seed_parsed,c,[{"filename":"annex.pdf","text":text,"sha256":digest}])
    second=c.http.portal.call(c.index.index_sources,c.actor,recovered,"controlled-native-v1")
    result=c.http.portal.call(c.index.retrieve,"registration",second["id"],c.actor,1500)
    assert result["excerpts"][0]["quote"]==text

def test_excerpt_bound_includes_final_character_offset_metadata(index_case):
    c=index_case
    source=c.http.portal.call(seed_parsed,c,[{"filename":"offset.pdf",
        "text":"x "*2500+"registration "+"y "*1000}])
    version=c.http.portal.call(c.index.index_sources,c.actor,source,"controlled-native-v1")
    result=c.http.portal.call(c.index.retrieve,"registration",version["id"],c.actor,800)
    assert result["excerpts"] and result["excerpts"][0]["character_start"]>1000
    assert len(json.dumps(result["excerpts"],ensure_ascii=False).encode())<=800
