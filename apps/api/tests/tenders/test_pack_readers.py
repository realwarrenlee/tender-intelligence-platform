"""Focused regression coverage for real multi-format tender sources."""
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from app.tenders.documents import inspect_upload,parse_document

XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPTX='application/vnd.openxmlformats-officedocument.presentationml.presentation'
DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def parse(path,version='source-v1'):
    return parse_document(path,version,'tender',hashlib.sha256(path.read_bytes()).hexdigest())


def test_docx_table_header_and_normal_hyperlink_are_source_text(tmp_path):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE
    doc=Document()
    doc.add_paragraph('Original paragraph one')
    doc.add_paragraph('')
    doc.add_paragraph('Original paragraph three')
    doc.add_table(rows=1,cols=1).cell(0,0).text='Must hold FM01 M1'
    doc.sections[0].header.paragraphs[0].text='Contract scope header'
    paragraph=doc.add_paragraph()
    link=OxmlElement('w:hyperlink')
    link.set(qn('r:id'),paragraph.part.relate_to('https://example.invalid/not-fetched',RELATIONSHIP_TYPE.HYPERLINK,is_external=True))
    run,text=OxmlElement('w:r'),OxmlElement('w:t')
    text.text='Public source link'
    run.append(text);link.append(run);paragraph._p.append(link)
    path=tmp_path/'form.docx';doc.save(path)
    inspect_upload(path.name,DOCX,path.read_bytes())
    result=parse(path)
    assert result['status']=='complete'
    assert [(a['paragraph'],a['text']) for a in result['anchors'][:2]]==[(1,'Original paragraph one'),(3,'Original paragraph three')]
    assert any('FM01 M1' in a['text'] and 'Table' in a['location_label'] for a in result['anchors'])
    assert any('scope header' in a['text'] and 'Header' in a['location_label'] for a in result['anchors'])
    assert any('Public source link' in a['text'] for a in result['anchors'])
    assert any('https://example.invalid/not-fetched' in a['text'] for a in result['anchors'])


def test_xlsx_has_cell_addresses_hidden_sheet_and_formula_without_execution(tmp_path):
    from openpyxl import Workbook
    workbook=Workbook()
    sheet=workbook.active;sheet.title='Scope'
    sheet['A1']='Registration';sheet['B1']='FM01 M1';sheet['A2']='=HYPERLINK("https://example.invalid","not executed")'
    sheet['A3']='Submit here';sheet['A3'].hyperlink='https://example.invalid/submission'
    hidden=workbook.create_sheet('Hidden obligations');hidden.sheet_state='hidden';hidden['A1']='Minimum two technicians'
    path=tmp_path/'schedule.xlsx';workbook.save(path)
    inspect_upload(path.name,XLSX,path.read_bytes())
    result=parse(path)
    text='\n'.join(a['text'] for a in result['anchors'])
    assert 'B1=FM01 M1' in text
    assert '=HYPERLINK(' in text
    assert 'https://example.invalid/submission' in text
    assert 'Minimum two technicians' in text
    assert any('Hidden obligations' in a['location_label'] for a in result['anchors'])
    assert all(a.get('paragraph',0)>0 for a in result['anchors'])


def test_pptx_retains_slide_text_table_and_reports_image_gap(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    from PIL import Image
    deck=Presentation()
    slide=deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(0,0,Inches(5),Inches(1)).text='Plant access requires advance notice'
    table=slide.shapes.add_table(1,2,0,Inches(1),Inches(5),Inches(1)).table
    table.cell(0,0).text='Site';table.cell(0,1).text='Woodleigh'
    image=tmp_path/'map.png';Image.new('RGB',(30,30),'white').save(image)
    slide.shapes.add_picture(str(image),0,Inches(2),width=Inches(1))
    path=tmp_path/'maps.pptx';deck.save(path)
    inspect_upload(path.name,PPTX,path.read_bytes())
    result=parse(path)
    assert result['status']=='partial'
    assert 'Plant access' in result['anchors'][0]['text']
    assert 'Woodleigh' in result['anchors'][0]['text']
    assert result['anchors'][0]['location_label']=='Slide 1'
    assert result['locations'][0]['error_code']=='IMAGE_REQUIRES_REVIEW'


def test_office_macro_package_is_rejected(tmp_path):
    from openpyxl import Workbook
    from app.tenders.policy import DomainError
    path=tmp_path/'schedule.xlsx';Workbook().save(path)
    with zipfile.ZipFile(path,'a') as archive:
        archive.writestr('xl/vbaProject.bin',b'macro payload')
    with pytest.raises(DomainError) as error:
        inspect_upload(path.name,XLSX,path.read_bytes())
    assert error.value.code=='INVALID_DOCUMENT'


def test_pdf_native_tables_keep_all_cells(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=500,height=500)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 450 Td (Criterion) Tj 160 0 Td (Mandatory FM01 M1) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    path=tmp_path/'table.pdf';writer.write(path)
    result=parse(path)
    assert result['status']=='complete'
    assert 'Criterion' in result['anchors'][0]['text']
    assert 'Mandatory FM01 M1' in result['anchors'][0]['text']


def test_office_external_nonhyperlink_content_is_not_claimed_complete(tmp_path):
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE
    doc=Document();doc.add_paragraph('Known native text')
    doc.part.relate_to('https://example.invalid/never-download.png',RELATIONSHIP_TYPE.IMAGE,is_external=True)
    path=tmp_path/'linked.docx';doc.save(path)
    result=parse(path)
    assert result['status']=='partial'
    assert any(row.get('error_code')=='EXTERNAL_CONTENT_REQUIRES_REVIEW' for row in result['locations'])


def test_xlsx_percentage_and_date_number_formats_are_retained(tmp_path):
    from openpyxl import Workbook
    workbook=Workbook();sheet=workbook.active
    sheet['A1']=0.4;sheet['A1'].number_format='0%'
    sheet['B1']=45000;sheet['B1'].number_format='yyyy-mm-dd'
    path=tmp_path/'typed.xlsx';workbook.save(path)
    result=parse(path)
    text='\\n'.join(a['text'] for a in result['anchors'])
    assert '0%' in text
    assert 'yyyy-mm-dd' in text


def test_pdf_keeps_rotated_native_text_and_indirect_link_annotations(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject,ArrayObject
    writer=PdfWriter();page=writer.add_blank_page(width=500,height=500)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 0 1 -1 0 100 100 Tm (Rotated mandatory condition) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    annotation=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Link')})
    page[NameObject('/Annots')]=writer._add_object(ArrayObject([writer._add_object(annotation)]))
    path=tmp_path/'rotated.pdf';writer.write(path)
    result=parse(path)
    assert 'Rotated mandatory condition' in result['anchors'][0]['text']
    assert result['status']=='complete'

def test_inherited_slide_master_text_is_preserved_and_layout_reviewed(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    from xml.etree import ElementTree as ET
    from app.tenders.native_formats import A
    deck=Presentation()
    slide=deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(0,0,Inches(5),Inches(1)).text='Readable slide body'
    slide.shapes[0].text_frame.paragraphs[0].runs[0].hyperlink.address='https://example.invalid/slide-link'
    path=tmp_path/'inherited.pptx';deck.save(path)
    with zipfile.ZipFile(path) as archive:
        contents={name:archive.read(name) for name in archive.namelist()}
    master=ET.fromstring(contents['ppt/slideMasters/slideMaster1.xml'])
    notice=ET.SubElement(master,'{'+A+'}p')
    ET.SubElement(notice,'{'+A+'}t').text='Mandatory safety clearance in inherited content'
    contents['ppt/slideMasters/slideMaster1.xml']=ET.tostring(master)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():archive.writestr(name,data)
    result=parse(path)
    text=' '.join(a['text'] for a in result['anchors'])
    assert 'https://example.invalid/slide-link' in text
    assert 'Mandatory safety clearance' in text
    assert result['status']=='partial'

def test_pdf_table_column_reading_order_remains_quotable(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    from app.tenders.citations import normalise_quote
    writer=PdfWriter();page=writer.add_blank_page(width=500,height=500)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 450 Td (within five days) Tj 0 -20 Td (where no timeline is specified) Tj ET BT /F1 12 Tf 300 450 Td (Unrelated penalty column) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    path=tmp_path/'columns.pdf';writer.write(path)
    result=parse(path)
    assert 'within five days where no timeline is specified' in normalise_quote(result['anchors'][0]['text'])
    assert 'Unrelated penalty column' in result['anchors'][0]['text']
