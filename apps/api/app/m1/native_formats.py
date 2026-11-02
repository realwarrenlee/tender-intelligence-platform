"""Native Office text readers. Never resolve links, evaluate formulas or execute content."""
import posixpath
from pathlib import PurePosixPath
import subprocess
from defusedxml.ElementTree import fromstring

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def local(node):
    return node.tag.rsplit('}',1)[-1]


def relationships(archive,part):
    name=str(PurePosixPath(part).parent/'_rels'/(PurePosixPath(part).name+'.rels'))
    return {n.get('Id'):n for n in fromstring(archive.read(name))} if name in archive.namelist() else {}


def link_targets(tree,rels):
    targets=[]
    for node in tree.iter():
        relationship=rels.get(node.get('{'+R+'}id'))
        if relationship is not None and relationship.get('Type','').endswith('/hyperlink'):
            target=relationship.get('Target','')
            if target and target not in targets:targets.append(target)
    return targets


def package_gaps(archive):
    gaps=[]
    for name in archive.namelist():
        if name.endswith('.rels'):
            for node in fromstring(archive.read(name)):
                if node.get('TargetMode')=='External' and not node.get('Type','').endswith('/hyperlink'):
                    gaps.append('EXTERNAL_CONTENT_REQUIRES_REVIEW')
    return list(dict.fromkeys(gaps))


def word_blocks(archive):
    blocks=[]
    gaps=package_gaps(archive)
    part_names=['word/document.xml']+sorted(name for name in archive.namelist()
        if name.startswith(('word/header','word/footer','word/footnotes','word/endnotes','word/comments')) and name.endswith('.xml'))
    counter=0
    for name in part_names:
        tree=fromstring(archive.read(name))
        prefix='' if name=='word/document.xml' else next(
            (label for token,label in [('header','Header'),('footer','Footer'),('footnotes','Footnotes'),('endnotes','Endnotes'),('comments','Comments')] if token in name),'Part')+' '+name.rsplit('/',1)[-1]
        rels=relationships(archive,name)
        parents={child:node for node in tree.iter() for child in node}
        tables={id(node):i for i,node in enumerate((node for node in tree.iter() if local(node)=='tbl'),1)}
        for paragraph in tree.iter('{'+W+'}p'):
            counter+=1
            text=''.join((node.text or '') if local(node) in ('t','delText','instrText') else '\t' if local(node)=='tab' else '\n' if local(node) in ('br','cr') else '' for node in paragraph.iter()).strip()
            links=link_targets(paragraph,rels)
            if links:text+='\n'+'\n'.join('Hyperlink target: '+target for target in links)
            ancestor=paragraph
            cell=row=table=None
            while ancestor in parents:
                ancestor=parents[ancestor]
                if local(ancestor)=='tc' and cell is None: cell=ancestor
                if local(ancestor)=='tr' and row is None: row=ancestor
                if local(ancestor)=='tbl':
                    table=ancestor;break
            label=(prefix+' ' if prefix else '')+'Paragraph '+str(counter)
            if table is not None and row is not None and cell is not None:
                rows=[n for n in table if local(n)=='tr']
                cells=[n for n in row if local(n)=='tc']
                label=(prefix+' ' if prefix else '')+f'Table {tables[id(table)]}, row {rows.index(row)+1}, cell {cells.index(cell)+1}, paragraph {counter}'
            codes=[]
            names={local(node) for node in paragraph.iter()}
            if names & {'drawing','pict','object','txbxContent','oMath','oMathPara'}:
                codes.append('IMAGE_REQUIRES_REVIEW')
            if names & {'ins','del','moveFrom','moveTo','fldSimple','fldChar','instrText','altChunk'}:
                codes.append('STRUCTURE_REQUIRES_REVIEW')
            blocks.append((counter,text,label,codes))
        if any(local(node) in ('altChunk','object') for node in tree.iter()):
            gaps.append('STRUCTURE_REQUIRES_REVIEW')
    return blocks,list(dict.fromkeys(gaps))


def _cell_value(cell,shared):
    kind=cell.get('t')
    value=cell.find('{'+S+'}v')
    raw=(value.text or '') if value is not None else ''
    if kind=='s':
        raw=shared[int(raw)] if raw else ''
    elif kind=='inlineStr':
        raw=''.join(n.text or '' for n in cell.iter('{'+S+'}t'))
    elif kind=='b':
        raw='TRUE' if raw=='1' else 'FALSE'
    formula=cell.find('{'+S+'}f')
    if formula is not None:
        raw='='+(formula.text or '')+(' [cached value: '+raw+']' if raw else ' [no cached value]')
    return raw


def spreadsheet_blocks(archive):
    tree=fromstring(archive.read('xl/workbook.xml'))
    rels={node.get('Id'):node for node in fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
    shared=[]
    if 'xl/sharedStrings.xml' in archive.namelist():
        shared=[''.join(node.text or '' for node in item.iter('{'+S+'}t')) for item in fromstring(archive.read('xl/sharedStrings.xml'))]
    blocks=[]
    gaps=package_gaps(archive)
    number_formats={0:'General',1:'0',2:'0.00',3:'#,##0',4:'#,##0.00',9:'0%',10:'0.00%',11:'0.00E+00',
        14:'mm-dd-yy',15:'d-mmm-yy',16:'d-mmm',17:'mmm-yy',18:'h:mm AM/PM',19:'h:mm:ss AM/PM',
        20:'h:mm',21:'h:mm:ss',22:'m/d/yy h:mm',45:'mm:ss',46:'[h]:mm:ss',47:'mmss.0',49:'@'}
    styles=[0]
    if 'xl/styles.xml' in archive.namelist():
        style_tree=fromstring(archive.read('xl/styles.xml'))
        for node in style_tree.iter('{'+S+'}numFmt'):
            number_formats[int(node.get('numFmtId'))]=node.get('formatCode','')
        cell_styles=style_tree.find('{'+S+'}cellXfs')
        if cell_styles is not None:styles=[int(node.get('numFmtId','0')) for node in cell_styles]
    workbook_properties=tree.find('{'+S+'}workbookPr')
    epoch='1904' if workbook_properties is not None and workbook_properties.get('date1904') in ('1','true') else '1900'
    index=0
    for sheet in tree.iter('{'+S+'}sheet'):
        relation=rels[sheet.get('{'+R+'}id')]
        if relation.get('TargetMode')=='External':
            gaps.append('EXTERNAL_CONTENT_REQUIRES_REVIEW');continue
        target=relation.get('Target','')
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        if not target.startswith('xl/') or target not in archive.namelist():
            gaps.append('STRUCTURE_REQUIRES_REVIEW');continue
        xml=fromstring(archive.read(target))
        sheet_rels=relationships(archive,target)
        title=sheet.get('name','Sheet')
        hidden=' (hidden)' if sheet.get('state','visible')!='visible' else ''
        rows=[];start=None;end=None;chars=0;used_formats={}
        def flush():
            nonlocal rows,start,end,chars,index,used_formats
            if not rows:return
            index+=1
            legend=('Number formats (Excel date epoch '+epoch+'): '+' | '.join(f'{key}={value}' for key,value in sorted(used_formats.items()))+'\n') if used_formats else ''
            blocks.append((index,legend+'\n'.join(rows),f'Sheet "{title}"{hidden}, rows {start}-{end}',[]))
            rows=[];start=None;end=None;chars=0;used_formats={}
        for row in xml.iter('{'+S+'}row'):
            values=[];row_formats={}
            for cell in row.findall('{'+S+'}c'):
                value=_cell_value(cell,shared)
                if value.strip():
                    style=int(cell.get('s','0'))
                    number_format=styles[style] if style<len(styles) else 0
                    annotation=''
                    if cell.get('t') not in ('s','inlineStr','b') and number_format:
                        annotation=f' [format {number_format}]'
                        row_formats[number_format]=number_formats.get(number_format,'Excel built-in format '+str(number_format))
                    values.append(cell.get('r','?')+'='+value+annotation)
            if not values:continue
            text=' | '.join(values)
            row_number=row.get('r','?')
            if rows and (len(rows)>=40 or chars+len(text)>16000):flush()
            if start is None:start=row_number
            used_formats.update(row_formats)
            end=row_number;rows.append(text);chars+=len(text)
        flush()
        for node in xml.iter():
            if local(node)=='hyperlink':
                targets=link_targets(node,sheet_rels)
                if node.get('location'):targets.append('#'+node.get('location'))
                if targets:
                    index+=1;blocks.append((index,'\n'.join('Hyperlink target: '+t for t in targets),f'Sheet "{title}", hyperlink {node.get("ref","")}',[]))
            if local(node) in ('drawing','legacyDrawing','oleObjects'):
                gaps.append('IMAGE_REQUIRES_REVIEW')
            if local(node) in ('oddHeader','evenHeader','firstHeader','oddFooter','evenFooter','firstFooter') and (node.text or '').strip():
                index+=1;blocks.append((index,node.text,f'Sheet "{title}", {local(node)}',[]))
            if local(node)=='dataValidation':
                details=' | '.join(f'{key}={value}' for key,value in node.attrib.items())
                values=' '.join(n.text or '' for n in node.iter() if n is not node)
                index+=1;blocks.append((index,details+' '+values,f'Sheet "{title}", validation {node.get("sqref","")}',[]))
    for node in tree.iter('{'+S+'}definedName'):
        if (node.text or '').strip():
            index+=1;blocks.append((index,node.text,'Workbook defined name '+node.get('name',''),[]))
    for name in sorted(archive.namelist()):
        if name.startswith('xl/drawings/') and name.endswith('.xml'):
            xml=fromstring(archive.read(name))
            text='\n'.join(n.text or '' for n in xml.iter('{'+A+'}t'))
            if text.strip():
                index+=1;blocks.append((index,text,'Drawing text '+name,['IMAGE_REQUIRES_REVIEW']))
        if name.startswith('xl/') and 'comment' in name.lower() and name.endswith('.xml'):
            xml=fromstring(archive.read(name))
            for node in xml.iter('{'+S+'}comment'):
                value=''.join(n.text or '' for n in node.iter('{'+S+'}t'))
                if value.strip():
                    index+=1;blocks.append((index,value,f'Comment {name}, cell {node.get("ref","")}',[]))
    return blocks,list(dict.fromkeys(gaps))


def presentation_blocks(archive):
    presentation=fromstring(archive.read('ppt/presentation.xml'))
    rels={node.get('Id'):node for node in fromstring(archive.read('ppt/_rels/presentation.xml.rels'))}
    blocks=[]
    gaps=package_gaps(archive)
    for index,slide in enumerate((n for n in presentation.iter() if local(n)=='sldId'),1):
        target=rels[slide.get('{'+R+'}id')].get('Target','')
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target)
        if not target.startswith('ppt/') or target not in archive.namelist():
            blocks.append((index,'',f'Slide {index}',['STRUCTURE_REQUIRES_REVIEW']));continue
        xml=fromstring(archive.read(target))
        text=[''.join(n.text or '' for n in paragraph.iter('{'+A+'}t')) for paragraph in xml.iter('{'+A+'}p')]
        slide_rels=relationships(archive,target)
        text+=['Hyperlink target: '+link for link in link_targets(xml,slide_rels)]
        codes=[]
        inherited=[(target,slide_rels)]
        visited={target}
        for depth in range(2):
            following=[]
            for owner,owner_rels in inherited:
                for relation in owner_rels.values():
                    if not relation.get('Type','').endswith(('/slideLayout','/slideMaster')):continue
                    if relation.get('TargetMode')=='External':continue
                    raw=relation.get('Target','')
                    part=raw.lstrip('/') if raw.startswith('/') else posixpath.normpath(str(PurePosixPath(owner).parent/raw))
                    if part in visited:continue
                    visited.add(part)
                    if not part.startswith('ppt/') or part not in archive.namelist():
                        codes.append('STRUCTURE_REQUIRES_REVIEW');continue
                    inherited_xml=fromstring(archive.read(part))
                    values=[n.text or '' for n in inherited_xml.iter('{'+A+'}t')]
                    if any(v.strip() for v in values):
                        text+=['Inherited template text (rendering requires review):']+values
                        codes.append('STRUCTURE_REQUIRES_REVIEW')
                    if any(local(n) in ('pic','oleObj','chart','diagram','videoFile','audioFile') for n in inherited_xml.iter()):codes.append('IMAGE_REQUIRES_REVIEW')
                    inherited_rels=relationships(archive,part)
                    text+=['Hyperlink target: '+link for link in link_targets(inherited_xml,inherited_rels)]
                    following.append((part,inherited_rels))
            inherited=following
        if any(local(n) in ('pic','oleObj','chart','diagram','videoFile','audioFile') or (local(n)=='graphicData' and not n.get('uri','').endswith('/table')) for n in xml.iter()):
            codes.insert(0,'IMAGE_REQUIRES_REVIEW')
        rel_name=str(PurePosixPath(target).parent/'_rels'/(PurePosixPath(target).name+'.rels'))
        if rel_name in archive.namelist():
            for relation in fromstring(archive.read(rel_name)):
                if relation.get('Type','').endswith('/notesSlide') and relation.get('TargetMode')!='External':
                    note=posixpath.normpath(str(PurePosixPath(target).parent/relation.get('Target','')))
                    if note in archive.namelist():
                        notes=fromstring(archive.read(note))
                        values=[''.join(n.text or '' for n in p.iter('{'+A+'}t')) for p in notes.iter('{'+A+'}p')]
                        text+=['Speaker notes:']+[v for v in values if v.strip()]
        blocks.append((index,'\n'.join(t for t in text if t.strip()),f'Slide {index}',codes))
    return blocks,gaps


def legacy_word_blocks(path):
    import shutil
    if not shutil.which('antiword'):
        return [(1,'','Legacy Word document',['CONVERTER_UNAVAILABLE'])],[]
    result=subprocess.run(['antiword','-t','-w','0',str(path)],capture_output=True,timeout=30,check=False)
    if result.returncode:
        return [(1,'','Legacy Word document',['LEGACY_DOC_REQUIRES_REVIEW'])],[]
    text=result.stdout.decode('utf-8',errors='replace')
    lines=text.splitlines()
    blocks=[]
    for offset in range(0,len(lines),20):
        blocks.append((len(blocks)+1,'\n'.join(lines[offset:offset+20]),f'Extracted text lines {offset+1}-{min(offset+20,len(lines))}',[]))
    # Binary Word text extraction cannot attest floating shapes, drawings and page layout.
    return blocks,['LEGACY_DOC_REQUIRES_REVIEW']
