import asyncio
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[4]
PDF = ROOT / 'evals/fixtures/development/D1-qualification/inputs/initial/tender.pdf'


def documents():
    assert (ROOT / 'apps/api/app/tenders/documents.py').exists(), 'T2 document processing is missing'
    from app.tenders import documents
    return documents


def create(http):
    return http.post('/api/v1/tenders', json={'title':'Fictional T2 tender','client_request_id':str(uuid4())}).json()


def upload(http, tender, files=None, revision=1, request_id=None, entries=None):
    files = files or [('tender.pdf', PDF.read_bytes(), 'application/pdf')]
    metadata = {'expected_input_revision':revision,'client_request_id':request_id or str(uuid4()),
                'files':entries or [{'role':'tender'} for _ in files]}
    return http.post(f"/api/v1/tenders/{tender['id']}/documents", data={'metadata':json.dumps(metadata)},
                     files=[('files', item) for item in files])


def test_real_parser_covers_both_pages_and_preserves_hash(tmp_path):
    module = documents()
    result = module.parse_document(PDF, 'fictional-v1', 'tender', hashlib.sha256(PDF.read_bytes()).hexdigest())
    assert result['status'] == 'complete'
    assert [a['page'] for a in result['anchors']] == [1, 2]
    assert all(a['text'].strip() for a in result['anchors'])
    assert 'Submission and Evaluation Requirements' in result['anchors'][1]['text']
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == 'f204d4ab533a3543a7a884402fe0e4f74460773376fc3f9d3622c8e50746817f'


def test_docx_blank_paragraph_anchor_is_not_renumbered(tmp_path):
    module = documents()
    from docx import Document
    path = tmp_path / 'fictional.docx'
    doc = Document()
    doc.add_paragraph('First obligation')
    doc.add_paragraph('')
    doc.add_paragraph('Third paragraph obligation')
    doc.save(path)
    result = module.parse_document(path, 'fictional-docx', 'tender', hashlib.sha256(path.read_bytes()).hexdigest())
    assert result['status'] == 'complete'
    assert [(a['paragraph'],a['text']) for a in result['anchors']] == [(1,'First obligation'),(3,'Third paragraph obligation')]


@pytest.mark.parametrize('name,mime,data,code', [
    ('bad.exe','application/pdf',b'%PDF-1.4', 'UNSUPPORTED_FORMAT'),
    ('bad.pdf','text/html',b'%PDF-1.4', 'MIME_MISMATCH'),
    ('../bad.pdf','application/pdf',b'%PDF-1.4', 'INVALID_FILENAME'),
    ('bad.pdf','application/pdf',b'not a PDF', 'INVALID_DOCUMENT'),
    ('large.pdf','application/pdf',b'x'*(20*1024*1024+1), 'FILE_TOO_LARGE'),
], ids=['extension','mime','path','invalid','size'])
def test_upload_preflight_rejects_unsafe_inputs(name,mime,data,code):
    module = documents()
    from app.tenders.policy import DomainError
    with pytest.raises(DomainError) as error:
        module.inspect_upload(name,mime,data)
    assert error.value.code == code


def test_page_and_docx_character_limits_before_conversion(tmp_path):
    module = documents()
    from app.tenders.policy import DomainError
    from pypdf import PdfWriter
    from docx import Document
    stream = io.BytesIO()
    writer = PdfWriter()
    for _ in range(module.MAX_PAGES+1):
        writer.add_blank_page(width=72,height=72)
    writer.write(stream)
    with pytest.raises(DomainError) as error:
        module.inspect_upload('large.pdf','application/pdf',stream.getvalue())
    assert error.value.code == 'PAGE_LIMIT'
    stream = io.BytesIO()
    doc = Document()
    doc.add_paragraph('x'*500001)
    doc.save(stream)
    with pytest.raises(DomainError) as error:
        module.inspect_upload('large.docx',module.DOCX_MIME,stream.getvalue())
    assert error.value.code == 'CHARACTER_LIMIT'


def test_unreadable_page_keeps_pack_incomplete(tmp_path):
    module = documents()
    from pypdf import PdfWriter
    path = tmp_path / 'blank.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=72,height=72)
    writer.write(path)
    result = module.parse_document(path,'blank-v1','tender',hashlib.sha256(path.read_bytes()).hexdigest())
    assert result['status'] != 'complete'
    pack = module.build_source_set([result])
    assert not pack['complete']
    assert len(pack['documents']) == 1
    assert pack['documents'][0]['locations'][0]['page'] == 1


def test_upload_is_immutable_idempotent_and_source_is_protected(client):
    documents()
    http,current,app = client
    tender = create(http)
    key = str(uuid4())
    first = upload(http,tender,request_id=key)
    assert first.status_code == 201, first.text
    assert upload(http,tender,request_id=key).json() == first.json()
    assert first.json()['input_revision'] == 2
    version = first.json()['document_version_ids'][0]
    result = http.get(f'/api/v1/sources/{version}')
    assert result.status_code == 200
    assert result.content == PDF.read_bytes()
    assert result.headers['cache-control'] == 'private, no-store'
    changed = upload(http,tender,files=[('changed.pdf',PDF.read_bytes(),'application/pdf')],request_id=key)
    assert changed.status_code == 409
    owner = current[0]
    from app.tenders.models import ActorContext
    current[0] = ActorContext(user_id=uuid4(), workspace_id=uuid4(), roles={'viewer'})
    assert http.get(f'/api/v1/sources/{version}').status_code in (403,404)
    current[0] = owner
    assert len(http.get(f"/api/v1/tenders/{tender['id']}").json()['documents']) == 1


def test_upload_permissions_amendments_and_active_pack_limits(client,actors):
    documents()
    http,current,_ = client
    tender = create(http)
    current[0] = actors['viewer']
    assert upload(http,tender).status_code == 403
    current[0] = actors['owner']
    assert upload(http,tender,entries=[{'role':'company_evidence'}]).status_code == 403
    assert upload(http,tender,entries=[{'role':'addendum','amends_version_id':str(uuid4())}]).status_code == 422
    first = upload(http,tender)
    assert first.status_code == 201
    version = first.json()['document_version_ids'][0]
    second = upload(http,tender,revision=2,entries=[{'role':'addendum','amends_version_id':version}])
    assert second.status_code == 201, second.text
    assert upload(http,tender,revision=2).status_code == 409
    files = [(f't{i}.pdf',PDF.read_bytes(),'application/pdf') for i in range(documents().MAX_FILES-1)]
    assert upload(http,tender,files=files,revision=3).status_code == 422
    assert len(http.get(f"/api/v1/tenders/{tender['id']}").json()['documents']) == 2


@pytest.mark.parametrize('count,size,pages,code',[(6,20*1024*1024,1,'PACK_LIMIT'),(2,1,1001,'PAGE_LIMIT')])
def test_cumulative_limits_are_enforced_in_transaction(client,count,size,pages,code):
    documents()
    from app.tenders.models import RegisterSources,SourceInput
    from app.tenders.policy import DomainError
    http,current,app = client
    tender = create(http)
    command = RegisterSources(tender_id=tender['id'],expected_input_revision=1,client_request_id=str(uuid4()),
        sources=[SourceInput(filename=f'fictional{i}.pdf',sha256='a'*64,storage_key='test-only/no-upload',role='tender',byte_size=size,page_count=pages) for i in range(count)])
    with pytest.raises(DomainError) as error:
        http.portal.call(app.state.repository.register_sources,current[0],command)
    assert error.value.code == code
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()['input_revision'] == 1


def test_docx_character_limit_is_cumulative_across_pack():
    module = documents()
    result = module.build_source_set([
        {'status':'complete','anchors':[{'paragraph':1,'text':'x'*10000000}]},
        {'status':'complete','anchors':[{'paragraph':1,'text':'y'*10000001}]},
    ])
    assert not result['complete']
    assert result['error_code'] == 'CHARACTER_LIMIT'


def test_multipart_file_limit_has_structured_error(client):
    documents()
    http,_,_ = client
    tender = create(http)
    response = upload(http,tender,files=[(f'f{i}.pdf',PDF.read_bytes(),'application/pdf') for i in range(documents().MAX_FILES+1)],
                      entries=[{'role':'tender'} for _ in range(documents().MAX_FILES)])
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_UPLOAD'


@pytest.mark.parametrize('structure',['table','header','tracked_change'])
def test_docx_structures_are_preserved_or_explicitly_incomplete(tmp_path,structure):
    module = documents()
    from docx import Document
    from docx.oxml import OxmlElement
    from app.tenders.policy import DomainError
    doc = Document()
    doc.add_paragraph('Introductory paragraph')
    if structure == 'table':
        doc.add_table(rows=1,cols=1).cell(0,0).text = 'Mandatory qualification hidden in a table'
    elif structure == 'header':
        doc.sections[0].header.paragraphs[0].text = 'Mandatory qualification in header'
    else:
        paragraph = doc.add_paragraph()
        inserted,run,text = OxmlElement('w:ins'),OxmlElement('w:r'),OxmlElement('w:t')
        text.text = 'Mandatory tracked insertion'
        run.append(text)
        inserted.append(run)
        paragraph._p.append(inserted)
    stream = io.BytesIO()
    doc.save(stream)
    path=tmp_path/'structured.docx'
    path.write_bytes(stream.getvalue())
    module.inspect_upload(path.name,module.DOCX_MIME,path.read_bytes())
    result=module.parse_document(path,'structured-v1','tender',hashlib.sha256(path.read_bytes()).hexdigest())
    assert 'Mandatory' in '\n'.join(a['text'] for a in result['anchors'])
    assert result['status']==('partial' if structure=='tracked_change' else 'complete')


def test_pdf_text_does_not_mask_unread_bitmap(tmp_path):
    module = documents()
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import NameObject,NumberObject,DictionaryObject,DecodedStreamObject,ArrayObject
    writer = PdfWriter()
    page = writer.add_page(PdfReader(PDF).pages[0])
    image = DecodedStreamObject()
    image.set_data(bytes([0,0,0,255,255,255])*200)
    image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
        NameObject('/Width'):NumberObject(20),NameObject('/Height'):NumberObject(20),
        NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    page['/Resources'][NameObject('/XObject')] = DictionaryObject({NameObject('/Scan'):writer._add_object(image)})
    content = DecodedStreamObject()
    content.set_data(b'q 300 0 0 300 10 10 cm /Scan Do Q')
    page[NameObject('/Contents')] = ArrayObject([page.raw_get('/Contents'),writer._add_object(content)])
    path = tmp_path/'mixed.pdf'
    writer.write(path)
    result = module.parse_document(path,'mixed-v1','tender',hashlib.sha256(path.read_bytes()).hexdigest())
    assert result['status'] == 'partial'
    assert result['anchors'][0]['text'].strip()
    assert result['locations'][0]['status'] == 'partial'
    assert result['locations'][0]['error_code'] == 'IMAGE_REQUIRES_REVIEW'
