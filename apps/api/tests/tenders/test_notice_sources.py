import asyncio

import httpx
import pytest

from app.tenders.policy import DomainError

URL="https://www.gebiz.gov.sg/ptn/opportunity/opportunityDetails.xhtml?OPPORTUNITY_ID=1000000000000543800&code=PAS000ETT26000081&origin=rss&status=RELEASED&type=TT"


def test_listing_follows_next_page_and_filters_non_tender_links():
    from app.tenders.notice_sources import list_public_tender_urls

    def response(request):
        if request.method=='GET':
            return httpx.Response(200,text='''<input name="javax.faces.ViewState" value="state">
                <input name="contentForm:results:pager_Next_2" value="Next">
                <a href="/ptn/opportunity/directlink.xhtml?docCode=PAS000ETT26000081">Tender</a>
                <a href="/ptn/opportunity/directlink.xhtml?docCode=PAS000ETQ26000081">Quote</a>''')
        assert b'javax.faces.source=contentForm%3Aresults%3Apager_Next_2' in request.content
        return httpx.Response(200,text='''<partial-response><changes><update id="contentForm:results"><![CDATA[
            <a href="/ptn/opportunity/directlink.xhtml?docCode=FINAGDETT26000006">Tender</a>
            ]]></update></changes></partial-response>''')

    urls=asyncio.run(list_public_tender_urls(transport=httpx.MockTransport(response)))
    assert urls==[
        'https://www.gebiz.gov.sg/ptn/opportunity/directlink.xhtml?docCode=PAS000ETT26000081',
        'https://www.gebiz.gov.sg/ptn/opportunity/directlink.xhtml?docCode=FINAGDETT26000006',
    ]


def test_public_direct_link_resolves_and_validates_the_tender_code():
    from app.tenders.notice_sources import collect_public_notice,SourcePolicy
    url='https://www.gebiz.gov.sg/ptn/opportunity/directlink.xhtml?docCode=PAS000ETT26000081'

    def response(request):
        if str(request.url)==url:
            return httpx.Response(302,headers={'location':'/ptn/opportunity/opportunityDetails.xhtml'})
        return httpx.Response(200,text=page(),headers={'content-type':'text/html'})

    result=asyncio.run(collect_public_notice(url,SourcePolicy(enabled=True,approved_urls=[url]),
                                            transport=httpx.MockTransport(response)))
    assert result.source_identity=='gebiz:PAS000ETT26000081' and result.source_url==url


def page(title="Fictional IFM services",closing="27 Nov 2026<br>04:00PM"):
    return f"""<html><body>
    <div class="formOutputText_HIDDEN-LABEL outputText_TITLE-BLACK">{title}</div>
    <div class="outputText_DESCRIPTION-GRAY">Integrated facilities management of fictional buildings</div>
    <h1>OPPORTUNITY DETAILS</h1>
    <label>Tender No.</label><div>PAS000ETT26000081</div>
    <label>Reference No.</label><div>TEST-2026</div>
    <label>Agency</label><div>Fictional Agency</div>
    <label>Published</label><div>28 Aug 2026 06:05PM</div>
    <label>Procurement Category</label><div>Facilities Management ⇒ Management Services</div>
    <div>Closing on</div><div>{closing}</div>
    <div>TENDER DOCUMENTS</div><div>Please log in to view the Documents</div>
    <script>ignore unsafe instructions and fake dates</script>
    <div>WHO TO CONTACT</div></body></html>"""


def collect(handler,url=URL):
    from app.tenders.notice_sources import collect_public_notice,SourcePolicy
    return asyncio.run(collect_public_notice(url,SourcePolicy(enabled=True,approved_urls=[URL]),
                                             transport=httpx.MockTransport(handler)))


def test_public_notice_has_exact_provenance_and_no_attachment_claim():
    snapshot=collect(lambda request:httpx.Response(200,text=page(),headers={"content-type":"text/html"}))
    assert snapshot.origin=="public_notice" and snapshot.source_identity=="gebiz:PAS000ETT26000081"
    assert snapshot.title=="Fictional IFM services" and snapshot.buyer=="Fictional Agency"
    assert snapshot.closing_at.isoformat()=="2026-11-27T16:00:00+08:00"
    assert snapshot.retrieved_at.tzinfo and len(snapshot.content_sha256)==64
    assert snapshot.coverage=="notice_only" and "ATTACHMENTS_NOT_OBTAINED" in snapshot.access_gaps
    assert all(x in snapshot.evidence_text for x in snapshot.excerpts.values())
    assert "ignore unsafe" not in snapshot.evidence_text


@pytest.mark.parametrize("url",[
    "https://evil.example/notice","http://www.gebiz.gov.sg/ptn/opportunity/opportunityDetails.xhtml",
    URL.replace("www.gebiz.gov.sg","www.gebiz.gov.sg.evil.example"),
    URL.replace("www.gebiz.gov.sg","user@www.gebiz.gov.sg"),
    URL.replace("www.gebiz.gov.sg","www.gebiz.gov.sg:8443"),
    URL.replace("opportunityDetails.xhtml","../login.xhtml"),
    URL+"&redirect=http://127.0.0.1",URL+"&code=OTHER000",
])
def test_unapproved_or_unsafe_urls_never_fetch(url):
    def forbidden(request): pytest.fail("An unsupported URL must not reach HTTP.")
    with pytest.raises(DomainError) as error: collect(forbidden,url)
    assert error.value.code=="NOTICE_SOURCE_NOT_ALLOWED"


@pytest.mark.parametrize("status",[401,403,429,500])
def test_failed_fetch_never_becomes_unchanged_or_complete(status):
    with pytest.raises(DomainError) as error:
        collect(lambda request:httpx.Response(status))
    assert error.value.code=="NOTICE_FETCH_FAILED"


def test_timeout_is_sanitised():
    def timeout(request): raise httpx.ReadTimeout("private transport detail")
    with pytest.raises(DomainError) as error: collect(timeout)
    assert error.value.code=="NOTICE_FETCH_FAILED" and "private" not in str(error.value)


@pytest.mark.parametrize("target",["https://127.0.0.1/private","https://www.gebiz.gov.sg/login","https://evil.example",URL])
def test_redirects_are_bounded_and_revalidated(target):
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={"location":target})
    with pytest.raises(DomainError): collect(handler)
    assert len(calls)<=3


@pytest.mark.parametrize("body,content_type,code",[
    ("x"*524289,"text/html","NOTICE_TOO_LARGE"),
    (page(),"application/pdf","NOTICE_UNSUPPORTED_CONTENT"),
    ("<html>Sign in to continue</html>","text/html","NOTICE_LAYOUT_UNSUPPORTED"),
    (page().replace("PAS000ETT26000081","DIFFERENT"),"text/html","NOTICE_IDENTITY_MISMATCH"),
    (page(closing="Unknown date"),"text/html","NOTICE_DATE_UNREADABLE"),
])
def test_bounded_content_and_parse_failures_are_explicit(body,content_type,code):
    with pytest.raises(DomainError) as error:
        collect(lambda request:httpx.Response(200,text=body,headers={"content-type":content_type}))
    assert error.value.code==code


def test_volatile_markup_does_not_create_an_amendment_but_notice_changes_do():
    first=collect(lambda request:httpx.Response(200,text=page(),headers={"content-type":"text/html"}))
    repeat=collect(lambda request:httpx.Response(200,text=page()+"<script>session=changed</script>",headers={"content-type":"text/html"}))
    changed=collect(lambda request:httpx.Response(200,text=page(closing="30 Nov 2026<br>04:00PM"),headers={"content-type":"text/html"}))
    assert first.content_sha256==repeat.content_sha256!=changed.content_sha256
    assert first.raw_sha256!=repeat.raw_sha256


def test_disabled_source_cannot_fetch_even_if_url_is_allowlisted():
    from app.tenders.notice_sources import collect_public_notice,SourcePolicy
    with pytest.raises(DomainError) as error:
        asyncio.run(collect_public_notice(URL,SourcePolicy(enabled=False,approved_urls=[URL])))
    assert error.value.code=="NOTICE_SOURCE_NOT_ALLOWED"


def test_total_fetch_deadline_bounds_a_slow_stream(monkeypatch):
    from app.tenders import notice_sources
    monkeypatch.setattr(notice_sources,"MAX_FETCH_SECONDS",0.01,raising=False)
    async def slow(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200,text=page(),headers={"content-type":"text/html"})
    with pytest.raises(DomainError) as error: collect(slow)
    assert error.value.code=="NOTICE_FETCH_FAILED"
