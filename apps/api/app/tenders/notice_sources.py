"""Allowlisted GeBIZ listing and public notices."""
import asyncio
from datetime import datetime,timezone
import hashlib
from html.parser import HTMLParser
import json
import re
from urllib.parse import parse_qsl,urlencode,urljoin,urlsplit,urlunsplit
from uuid import UUID
from typing import Literal
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel,ConfigDict,Field,ValidationError

from app.tenders.policy import DomainError

MAX_NOTICE_BYTES=512*1024
MAX_FETCH_SECONDS=20
PATH="/ptn/opportunity/opportunityDetails.xhtml"
DIRECT_PATH="/ptn/opportunity/directlink.xhtml"
LISTING_PATH="/ptn/opportunity/BOListing.xhtml"
ORIGIN="https://www.gebiz.gov.sg"
LISTING_URL=ORIGIN+LISTING_PATH+"?origin=opportunities"
MAX_LISTING_PAGES=10
TENDER_CODE=r"[A-Z]{3}[A-Z0-9]{3}ETT[0-9]{8}"


class SourcePolicy(BaseModel):
    model_config=ConfigDict(extra="forbid")
    enabled:bool=False
    approved_urls:list[str]=Field(default_factory=list,max_length=100)


class NoticeJob(BaseModel):
    model_config=ConfigDict(extra="forbid")
    key:str=Field(min_length=1,max_length=100)
    workspace_id:UUID
    intake_owner_user_id:UUID
    source_url:str=Field(max_length=2000)
    enabled:bool=False


class NoticeSnapshot(BaseModel):
    model_config=ConfigDict(extra="forbid")
    source_identity:str
    origin:Literal['public_notice','controlled_import']
    source_url:str|None
    retrieved_at:datetime
    title:str=Field(min_length=1,max_length=300)
    buyer:str|None
    reference:str
    category:str|None
    closing_at:datetime|None
    published_at:datetime|None
    evidence_text:str=Field(min_length=1,max_length=50000)
    excerpts:dict[str,str]
    coverage:Literal["notice_only"]="notice_only"
    access_gaps:list[str]
    raw_sha256:str
    content_sha256:str


def snapshot(**fields):
    stable={k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in fields.items() if k!="raw_sha256"}
    digest=hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return NoticeSnapshot(**fields,retrieved_at=datetime.now(timezone.utc),content_sha256=digest)


def imported_snapshot(command):
    evidence="\n".join([command.title,"Buyer: "+(command.buyer or "Unknown"),
        "Reference: "+command.reference,"Category: "+(command.category or "Unknown"),
        "Closing: "+(command.closing_at.isoformat() if command.closing_at else "Unknown"),command.notice_text])
    return snapshot(source_identity="controlled:"+command.notice_id,origin="controlled_import",source_url=None,
        title=command.title,buyer=command.buyer,reference=command.reference,category=command.category,
        closing_at=command.closing_at,published_at=None,evidence_text=evidence,
        excerpts={"title":command.title,"notice":command.notice_text},
        access_gaps=["CONTROLLED_IMPORT","ATTACHMENTS_NOT_OBTAINED"],
        raw_sha256=hashlib.sha256(command.model_dump_json(exclude={"client_request_id"}).encode()).hexdigest())


def canonical_url(url):
    try:
        p=urlsplit(url)
        pairs=parse_qsl(p.query,keep_blank_values=True)
        q=dict(pairs)
        trusted=(p.scheme=="https" and p.hostname=="www.gebiz.gov.sg" and p.port in (None,443)
            and not p.username and not p.password and not p.fragment)
        if trusted and p.path==DIRECT_PATH and len(pairs)==1 and re.fullmatch(TENDER_CODE,q.get("docCode","")):
            return ORIGIN+DIRECT_PATH+"?"+urlencode(q)
        valid=(trusted and p.path==PATH
            and len(q)==len(pairs) and set(q)=={"OPPORTUNITY_ID","code","origin","status","type"}
            and re.fullmatch(r"[0-9]{19}",q["OPPORTUNITY_ID"])
            and re.fullmatch(r"[A-Z]{3}[0-9]{3}ETT[0-9]{8}",q["code"])
            and q["origin"]=="rss" and q["status"]=="RELEASED" and q["type"]=="TT")
        if valid: return urlunsplit(("https","www.gebiz.gov.sg",PATH,urlencode(sorted(q.items())),""))
    except (ValueError,KeyError): pass
    raise DomainError(422,"NOTICE_SOURCE_NOT_ALLOWED","Only the configured GeBIZ public tender-notice route is supported.")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","head"): self.skip+=1
        if not self.skip and tag in ("div","p","br","h1","label","tr","li"): self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in ("script","style","head"): self.skip=max(0,self.skip-1)
        if not self.skip and tag in ("div","p","h1","label","tr","li"): self.parts.append("\n")
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)
    def text(self):
        return "\n".join(" ".join(line.split()) for line in "".join(self.parts).splitlines() if line.strip())


def _plain(html):
    parser=_Text();parser.feed(html);return parser.text()


def _parse(body,url):
    html=body.decode("utf-8",errors="replace")
    title=re.search(r'<div[^>]*class=["\'][^"\']*outputText_TITLE-BLACK[^"\']*["\'][^>]*>(.*?)</div>',html,re.S)
    text=_plain(html)
    if not title or "OPPORTUNITY DETAILS" not in text or "Tender No." not in text:
        raise DomainError(422,"NOTICE_LAYOUT_UNSUPPORTED","The page is not a supported public opportunity notice.")
    name=_plain(title.group(1));start=text.find(name);end=text.find("WHO TO CONTACT",start)
    evidence=text[start:end if end>=0 else len(text)]
    lines=evidence.splitlines()
    def value(label,required=False):
        positions=[i for i,line in enumerate(lines) if line==label]
        if len(positions)!=1 or positions[0]+1>=len(lines):
            if required: raise DomainError(422,"NOTICE_LAYOUT_UNSUPPORTED","Required public notice fields are missing or ambiguous.")
            return None
        return lines[positions[0]+1]
    reference=value("Tender No.",True)
    params=dict(parse_qsl(urlsplit(url).query))
    if reference!=(params.get("code") or params.get("docCode")):
        raise DomainError(422,"NOTICE_IDENTITY_MISMATCH","The returned notice does not match the requested tender.")
    closing=value("Closing on",True)
    position=lines.index("Closing on")+1
    if not re.search(r"[0-9]:[0-9]{2}",closing) and position+1<len(lines): closing+="\n"+lines[position+1]
    def date(text):
        if not text: return None
        try: return datetime.strptime(text.replace("\n"," "),"%d %b %Y %I:%M%p").replace(tzinfo=ZoneInfo("Asia/Singapore"))
        except ValueError: raise DomainError(422,"NOTICE_DATE_UNREADABLE","The public notice date requires review.") from None
    buyer=value("Agency",True);category=value("Procurement Category");published=value("Published")
    try:
        return snapshot(source_identity="gebiz:"+reference,origin="public_notice",source_url=url,
            title=name,buyer=buyer,reference=reference,category=category,closing_at=date(closing),
            published_at=date(published),evidence_text=evidence,
            excerpts={k:v for k,v in {"title":name,"buyer":buyer,"reference":reference,"category":category,"closing":closing}.items() if v},
            access_gaps=["ATTACHMENTS_NOT_OBTAINED"],raw_sha256=hashlib.sha256(body).hexdigest())
    except ValidationError:
        raise DomainError(422,"NOTICE_LAYOUT_UNSUPPORTED","The public notice exceeds the supported field limits.") from None


async def _bounded_body(response):
    chunks=[];size=0
    async for chunk in response.aiter_bytes():
        size+=len(chunk)
        if size>MAX_NOTICE_BYTES: raise DomainError(413,"NOTICE_TOO_LARGE","The public notice exceeds the supported size.")
        chunks.append(chunk)
    return b"".join(chunks)


class _Listing(HTMLParser):
    def __init__(self,html):
        super().__init__()
        self.urls=[]
        self.next_button=None
        self.view_state=None
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="a" and (href:=attrs.get("href","")).startswith(DIRECT_PATH+"?docCode="):
            code=dict(parse_qsl(urlsplit(href).query)).get("docCode","")
            if re.fullmatch(TENDER_CODE,code):
                self.urls.append(ORIGIN+DIRECT_PATH+"?docCode="+code)
        if tag=="input" and attrs.get("name")=="javax.faces.ViewState":
            self.view_state=attrs.get("value")
        if tag=="input" and attrs.get("value")=="Next" and "disabled" not in attrs:
            name=attrs.get("name","")
            if re.fullmatch(r"contentForm:[\w:]+_Next_\d+",name):
                self.next_button=name


async def list_public_tender_urls(transport=None):
    urls={}
    try:
        async with asyncio.timeout(60),httpx.AsyncClient(timeout=15,transport=transport,trust_env=False) as http:
            async with http.stream("GET",LISTING_URL) as response:
                response.raise_for_status()
                listing=_Listing((await _bounded_body(response)).decode("utf-8",errors="replace"))
            state=listing.view_state
            if not state:
                raise DomainError(422,"NOTICE_LAYOUT_UNSUPPORTED","The GeBIZ listing layout changed.")
            for page in range(MAX_LISTING_PAGES):
                urls.update(dict.fromkeys(listing.urls))
                button=listing.next_button
                if not button or page==MAX_LISTING_PAGES-1:
                    break
                results=button.rsplit(":",1)[0]
                data={
                    "contentForm":"contentForm","javax.faces.ViewState":state,
                    "javax.faces.partial.ajax":"true","javax.faces.source":button,
                    "javax.faces.partial.execute":results,"javax.faces.partial.render":results,
                    "javax.faces.behavior.event":"action","javax.faces.partial.event":"click",
                    button:button,
                }
                async with http.stream("POST",ORIGIN+LISTING_PATH,data=data,
                                       headers={"Faces-Request":"partial/ajax"}) as response:
                    response.raise_for_status()
                    updates=ElementTree.fromstring(await _bounded_body(response)).findall("./changes/update")
                html=next((item.text for item in updates if item.get("id")==results),None)
                if html is None:
                    raise DomainError(422,"NOTICE_LAYOUT_UNSUPPORTED","GeBIZ listing pagination changed.")
                state=next((item.text for item in updates
                            if "javax.faces.ViewState" in item.get("id","") and item.text),state)
                listing=_Listing(html)
    except (httpx.HTTPError,TimeoutError,ElementTree.ParseError):
        raise DomainError(503,"NOTICE_LISTING_FAILED","The GeBIZ opportunities listing could not be read.") from None
    return list(urls)


async def collect_public_notice(source_url,source_policy,transport=None):
    url=canonical_url(source_url)
    approved={canonical_url(x) for x in source_policy.approved_urls}
    if not source_policy.enabled or url not in approved:
        raise DomainError(422,"NOTICE_SOURCE_NOT_ALLOWED","This notice source is not enabled and allowlisted.")
    original_url=url
    try:
        async with asyncio.timeout(MAX_FETCH_SECONDS),httpx.AsyncClient(timeout=15,follow_redirects=False,transport=transport,trust_env=False) as http:
            for attempt in range(3):
                async with http.stream("GET",url,headers={"Accept":"text/html","User-Agent":"TenderIntelligence/0.1"}) as response:
                    if response.is_redirect:
                        target=urljoin(url,response.headers.get("location",""))
                        direct_redirect=(urlsplit(original_url).path==DIRECT_PATH and url==original_url
                                         and target==ORIGIN+PATH)
                        if not direct_redirect:
                            target=canonical_url(target)
                        if (not direct_redirect and target not in approved) or attempt==2:
                            raise DomainError(422,"NOTICE_SOURCE_NOT_ALLOWED","The public notice redirected outside the approved route or limit.")
                        url=target;continue
                    if response.status_code!=200:
                        raise DomainError(503,"NOTICE_FETCH_FAILED","The public notice could not be obtained; earlier evidence is unchanged.")
                    if response.headers.get("content-type","").split(";")[0].strip().lower()!="text/html":
                        raise DomainError(422,"NOTICE_UNSUPPORTED_CONTENT","The public notice route returned unsupported content.")
                    return _parse(await _bounded_body(response),original_url if urlsplit(original_url).path==DIRECT_PATH else url)
    except (httpx.HTTPError,TimeoutError):
        raise DomainError(503,"NOTICE_FETCH_FAILED","The public notice could not be obtained; retry later.") from None
