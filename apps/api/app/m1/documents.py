"""Native source readers run in a child process, preserving original bytes and locations."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from app.m1.policy import DomainError

PDF_MIME='application/pdf'
DOCX_MIME='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
MIME_TYPES={
    '.pdf':PDF_MIME,
    '.docx':DOCX_MIME,
    '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.doc':'application/msword',
}
MAX_FILES=100
MAX_PAGES=2000
MAX_FILE=20*1024*1024
MAX_PACK=100*1024*1024
MAX_TEXT=20_000_000
PARSER_VERSION='native-office-v3'


def inspect_upload(filename,content_type,data):
    if not filename or len(filename)>255 or any(c in filename for c in '/\\\r\n\x00'):
        raise DomainError(422,'INVALID_FILENAME','Use a plain filename without path components.')
    suffix=Path(filename).suffix.lower()
    if suffix not in MIME_TYPES:
        raise DomainError(422,'UNSUPPORTED_FORMAT','Choose PDF, DOCX, DOC, XLSX or PPTX files.')
    expected=MIME_TYPES[suffix]
    if content_type!=expected:
        raise DomainError(422,'MIME_MISMATCH','The declared file type does not match its extension.')
    if len(data)>MAX_FILE:
        raise DomainError(422,'FILE_TOO_LARGE','Each source must be at most 20 MiB.')
    try:
        pages=0
        if suffix=='.pdf':
            from pypdf import PdfReader
            if not data.startswith(b'%PDF-'):raise ValueError()
            reader=PdfReader(io.BytesIO(data),strict=True)
            if reader.is_encrypted:raise ValueError()
            pages=len(reader.pages)
            if pages>MAX_PAGES:
                raise DomainError(422,'PAGE_LIMIT',f'The source set must contain at most {MAX_PAGES} PDF pages.')
            if pages==0:raise ValueError()
        elif suffix=='.doc':
            import olefile
            with olefile.OleFileIO(io.BytesIO(data)) as ole:
                if not ole.exists('WordDocument'):raise ValueError()
                header=ole.openstream('WordDocument').read(32)
                if len(header)<12 or header[:2]!=b'\xec\xa5' or int.from_bytes(header[10:12],'little')&0x100:raise ValueError()
                if any(any('vba' in part.lower() or 'macros' in part.lower() for part in name) for name in ole.listdir()):raise ValueError()
        else:
            from defusedxml.ElementTree import fromstring
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries=archive.infolist()
                if len(entries)>5000 or sum(item.file_size for item in entries)>50*1024*1024:
                    raise DomainError(422,'OFFICE_EXPANSION_LIMIT','The Office package exceeds the supported expansion limit.')
                if any(item.flag_bits&1 or 'vbaproject' in item.filename.lower() for item in entries):raise ValueError()
                core={'.docx':'word/document.xml','.xlsx':'xl/workbook.xml','.pptx':'ppt/presentation.xml'}[suffix]
                tree=fromstring(archive.read(core))
                # Inspect relationships as XML; never resolve or fetch their targets.
                for name in archive.namelist():
                    if name.endswith('.rels'):fromstring(archive.read(name))
                if suffix=='.docx':
                    chars=sum(len(node.text or '') for node in tree.iter() if node.tag.endswith('}t'))
                    if chars>500000:
                        raise DomainError(422,'CHARACTER_LIMIT','DOCX text must contain at most 500,000 characters.')
    except DomainError:raise
    except Exception:
        raise DomainError(422,'INVALID_DOCUMENT','The document is corrupt, encrypted or unsupported.') from None
    return {'filename':filename,'sha256':hashlib.sha256(data).hexdigest(),
            'content_type':expected,'byte_size':len(data),'page_count':pages}


def parse_document(path,version_id,role,expected_sha):
    path=Path(path)
    data=path.read_bytes()
    suffix=path.suffix.lower()
    meta=inspect_upload(path.name,MIME_TYPES.get(suffix,''),data)
    if meta['sha256']!=expected_sha:
        raise DomainError(422,'SOURCE_HASH_MISMATCH','Stored source bytes do not match their pinned version.')
    gaps=[]
    kind='paragraph'
    if suffix=='.pdf':
        from pypdf import PdfReader
        kind='page'
        blocks=[]
        for index,page in enumerate(PdfReader(io.BytesIO(data)).pages,1):
            text=(page.extract_text() or '') if '/Contents' in page else ''
            layout=(page.extract_text(extraction_mode='layout',layout_mode_strip_rotated=False) or '') if '/Contents' in page else ''
            if ' '.join(text.split())!=' '.join(layout.split()):
                text+='\n\n[Same page, positioned text layout for table alignment]\n'+layout
            codes=['IMAGE_REQUIRES_REVIEW'] if page.images.keys() else []
            annotations=page.get('/Annots')
            if any(annotation.get_object().get('/Subtype') not in ('/Link',) for annotation in (annotations.get_object() if annotations else [])):
                codes.append('ANNOTATION_REQUIRES_REVIEW')
            blocks.append((index,text,f'Page {index}',codes))
    elif suffix=='.doc':
        from app.m1.native_formats import legacy_word_blocks
        blocks,gaps=legacy_word_blocks(path)
    else:
        from app.m1.native_formats import word_blocks,spreadsheet_blocks,presentation_blocks
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            blocks,gaps={'.docx':word_blocks,'.xlsx':spreadsheet_blocks,'.pptx':presentation_blocks}[suffix](archive)
    anchors=[];locations=[]
    characters=0
    for index,text,label,codes in blocks:
        characters+=len(text)
        if characters>MAX_TEXT:
            gaps.append('CHARACTER_LIMIT');break
        if not text.strip() and not codes and suffix!='.pdf':continue
        status='partial' if codes else 'complete' if text.strip() else 'unreadable'
        location={kind:index,'status':status,'location_label':label}
        if codes:location['error_code']=codes[0]
        locations.append(location)
        if text.strip():
            anchors.append({'anchor_id':f'{version_id}-{kind}-{index}','document_version_id':str(version_id),
                'source_role':role,kind:index,'location_label':label,'text':text})
    for code in dict.fromkeys(gaps):
        locations.append({kind:max([row[kind] for row in locations],default=0)+1,'status':'partial','location_label':'Document coverage','error_code':code})
    complete=bool(anchors) and bool(locations) and all(row['status']=='complete' for row in locations)
    return {'document_version_id':str(version_id),'source_role':role,'sha256':expected_sha,
            'status':'complete' if complete else 'partial','error_code':None if complete else 'SOURCE_INCOMPLETE',
            'locations':locations,'anchors':anchors}


def build_source_set(results):
    characters=sum(len(anchor['text']) for item in results for anchor in item['anchors'])
    error='CHARACTER_LIMIT' if characters>MAX_TEXT else None
    return {'complete':bool(results) and not error and all(item['status']=='complete' for item in results),
            'error_code':error,'documents':results,'parser':PARSER_VERSION}


async def parse_isolated(source,data,timeout):
    with tempfile.TemporaryDirectory(prefix='m1-parse-') as directory:
        folder=Path(directory)
        suffix=Path(source.get('filename','')).suffix.lower()
        if suffix not in MIME_TYPES:
            suffix=next((ext for ext,mime in MIME_TYPES.items() if mime==source['content_type']),'.bin')
        path=folder/('source'+suffix)
        path.write_bytes(data)
        config=folder/'input.json';output=folder/'output.json'
        config.write_text(json.dumps({'path':str(path),'version_id':str(source['id']),'role':source['role'],'expected_sha':source['sha256']}),encoding='utf-8')
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','app.m1.documents',str(config),str(output),
            cwd=Path(__file__).resolve().parents[2],stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000 if sys.platform=='win32' else 0)
        try:
            await asyncio.wait_for(process.wait(),timeout=timeout)
        except (TimeoutError,asyncio.CancelledError):
            if process.returncode is None:
                process.kill();await process.wait()
            raise
        if process.returncode!=0 or not output.exists():
            raise DomainError(422,'PARSER_PROCESS_FAILED','The isolated parser failed; source coverage is incomplete.')
        return json.loads(output.read_text(encoding='utf-8'))


if __name__=='__main__':
    config=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        Path(sys.argv[2]).write_text(json.dumps(parse_document(**config)),encoding='utf-8')
    except Exception:
        raise SystemExit(1)
