"""Bounded native Word graph: physical nodes, logical merges and actual note links."""
from pathlib import Path
import hashlib,io,posixpath,re,unicodedata,zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote,urlsplit

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
P='{http://schemas.openxmlformats.org/package/2006/relationships}'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
CT='{http://schemas.openxmlformats.org/package/2006/content-types}'
class CandidateWordError(ValueError):pass

def canon(value):
    text=unicodedata.normalize('NFKC',str(value if value is not None else ''))
    text=re.sub(r'\[(?:F|S)\d{2}\]','',text,flags=re.I)
    text=text.translate(str.maketrans({'。':'.','、':',','“':'"','”':'"','‘':"'",'’':"'",'−':'-'}))
    text=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',text)
    return ''.join(text.split())

def _xml(data):
    if len(data)>16_000_000 or b'<!DOCTYPE' in data.replace(b'\0',b'').upper() or b'<!ENTITY' in data.replace(b'\0',b'').upper():
        raise CandidateWordError('unsafe or oversized XML')
    try:return ET.fromstring(data)
    except ET.ParseError as exc:raise CandidateWordError('malformed Word XML') from exc

def _parts(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>5_242_880:raise CandidateWordError('missing, unsafe or oversized DOCX')
    try:
        with zipfile.ZipFile(path) as archive:
            members=archive.infolist();names=[m.filename for m in members]
            if len(members)>5000 or len(set(names))!=len(names) or sum(m.file_size for m in members)>100_000_000:
                raise CandidateWordError('package size or duplicate member limit')
            if any(m.flag_bits&1 or '\\' in m.filename or m.filename.startswith('/') or any(p in {'','.','..'} for p in m.filename.rstrip('/').split('/')) for m in members):
                raise CandidateWordError('unsafe package member')
            parts={m.filename:archive.read(m) for m in members}
    except (OSError,RuntimeError,zipfile.BadZipFile) as exc:raise CandidateWordError('unreadable DOCX') from exc
    if not {'[Content_Types].xml','_rels/.rels','word/document.xml'}<=set(parts):raise CandidateWordError('missing native Word OPC contract')
    types=_xml(parts['[Content_Types].xml']);rels=_xml(parts['_rels/.rels'])
    main=[r for r in rels if r.get('Type')==R+'officeDocument']
    if (types.tag!=CT+'Types' or rels.tag!=P+'Relationships' or len(main)!=1 or main[0].get('TargetMode')=='External'
        or main[0].get('Target','').lstrip('/')!='word/document.xml'
        or not any(r.get('PartName')=='/word/document.xml' and r.get('ContentType')=='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' for r in types)):
        raise CandidateWordError('invalid native Word content type or main relationship')
    return parts

def _integer(value,default=None):
    try:return int(value) if value is not None else default
    except (ValueError,TypeError):return default

def _val(properties,name,default=None):
    item=properties.find(W+name) if properties is not None else None
    return item.get(W+'val',default) if item is not None else default

def _paragraph(node):
    chunks=[];references=[];length=0
    def walk(parent):
        nonlocal length
        for child in parent:
            if child.tag in {W+'del',W+'moveFrom',W+'drawing',W+'pict',W+'tbl'}:continue
            if child.tag==W+'t':value=child.text or '';chunks.append(value);length+=len(value)
            elif child.tag in {W+'br',W+'cr',W+'tab'}:chunks.append(' ');length+=1
            elif child.tag in {W+'footnoteReference',W+'endnoteReference'}:
                raw=child.get(W+'id','')
                if not re.fullmatch(r'[+-]?\d{1,10}',raw):raise CandidateWordError('invalid Word note reference ID')
                references.append({'kind':'footnote' if child.tag==W+'footnoteReference' else 'endnote','id':str(int(raw)),'offset':length})
            else:walk(child)
    walk(node)
    return ''.join(chunks),references

def read_document(path):
    parts=_parts(path);document=_xml(parts['word/document.xml'])
    if document.tag!=W+'document' or document.find(W+'body') is None:raise CandidateWordError('missing Word body')
    note_targets={};notes={}
    rels=_xml(parts['word/_rels/document.xml.rels']) if 'word/_rels/document.xml.rels' in parts else ET.Element(P+'Relationships')
    if rels.tag!=P+'Relationships':raise CandidateWordError('invalid document relationship root')
    seen=set()
    for relation in rels:
        identity=relation.get('Id')
        if not identity or identity in seen:raise CandidateWordError('ambiguous document relationship ID')
        seen.add(identity)
        if relation.get('Type') not in {R+'footnotes',R+'endnotes'}:continue
        kind='footnote' if relation.get('Type')==R+'footnotes' else 'endnote'
        if relation.get('TargetMode')=='External':note_targets[kind]=None;continue
        target=unquote(relation.get('Target',''))
        try:uri=urlsplit(target)
        except ValueError as exc:raise CandidateWordError('invalid note URI') from exc
        name=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('word',target))
        if not target or '\\' in target or uri.scheme or uri.netloc or uri.query or uri.fragment or name=='..' or name.startswith('../'):
            raise CandidateWordError('unsafe note relationship')
        if kind in note_targets and note_targets[kind]!=name:raise CandidateWordError('ambiguous note part')
        note_targets[kind]=name
        if name not in parts:continue
        root=_xml(parts[name])
        if root.tag!=W+kind+'s':raise CandidateWordError('invalid note part root')
        for note in root.findall(W+kind):
            identity=_integer(note.get(W+'id'))
            if identity is None:raise CandidateWordError('invalid Word note ID')
            key=kind+':'+str(identity)
            if key in notes:raise CandidateWordError('duplicate Word note ID')
            text='\n'.join(_paragraph(p)[0] for p in note.iter(W+'p'))
            notes[key]={'locator':key,'kind':kind,'id':str(identity),'text':text,'part':name,
                'part_sha256':hashlib.sha256(parts[name]).hexdigest(),'type':note.get(W+'type','normal')}
    nodes={};paragraphs=[];tables=[];events=[];position=0;body_paragraph_number=0

    def add_paragraph(node,parent_cell=None,local_index=None):
        nonlocal body_paragraph_number,position
        if parent_cell is None:
            body_paragraph_number+=1;locator='paragraph:'+str(body_paragraph_number)
        else:locator=parent_cell+'/paragraph:'+str(local_index)
        text,refs=_paragraph(node);position+=1
        item={'kind':'paragraph','locator':locator,'text':text,'references':refs,'parent_cell':parent_cell,'position':position}
        for ref in refs:
            ref['node']=locator;ref['cell']=parent_cell
            ref['note_locator']=ref['kind']+':'+ref['id'];ref['available']=ref['note_locator'] in notes
        nodes[locator]=item;paragraphs.append(item);events.append({'kind':'paragraph','locator':locator,'position':position})
        return item

    def add_table(node,parent_cell=None):
        nonlocal position
        number=len(tables)+1;locator='table:'+str(number);position+=1
        result={'kind':'table','locator':locator,'number':number,'parent_cell':parent_cell,'position':position,
            'rows':[],'anchors':[],'repeated_headers':[],'declared_columns':len(node.findall(W+'tblGrid/'+W+'gridCol'))}
        tables.append(result);nodes[locator]=result;events.append({'kind':'table','locator':locator,'position':position})
        previous_vertical={}
        for r,row in enumerate(node.findall(W+'tr'),1):
            properties=row.find(W+'trPr');column=_integer(_val(properties,'gridBefore'),0)+1
            header=row.find(W+'trPr/'+W+'tblHeader')
            if header is not None and header.get(W+'val','1') not in {'0','false','off'}:result['repeated_headers'].append(r)
            cells=[];horizontal=None;groups=[]
            for c,cell in enumerate(row.findall(W+'tc'),1):
                key=f'{locator}/row:{r}/cell:{c}';cp=cell.find(W+'tcPr');span=_integer(_val(cp,'gridSpan'),1)
                if span is None or span<1 or span>128 or column<1 or column>512:raise CandidateWordError('invalid cell grid interval')
                item={'kind':'cell','locator':key,'table':number,'row':r,'physical_cell':c,'column':column,
                    'colspan':span,'vertical_merge':_val(cp,'vMerge','continue') if cp is not None and cp.find(W+'vMerge') is not None else None,
                    'horizontal_merge':_val(cp,'hMerge','continue') if cp is not None and cp.find(W+'hMerge') is not None else None,
                    'paragraphs':[],'child_tables':[],'references':[]}
                nodes[key]=item;cells.append(item);column+=span
                def cell_children(parent):
                    for child in parent:
                        if child.tag==W+'p':
                            p=add_paragraph(child,key,len(item['paragraphs'])+1);item['paragraphs'].append(p['locator']);item['references'].extend(p['references'])
                        elif child.tag==W+'tbl':item['child_tables'].append(add_table(child,key)['number'])
                        elif child.tag in {W+'sdt',W+'sdtContent',W+'customXml'}:cell_children(child)
                cell_children(cell)
                item['text']='\n'.join(nodes[p]['text'] for p in item['paragraphs'])
                if item['horizontal_merge']=='continue' and horizontal is not None:
                    horizontal['colspan']+=span;horizontal['members'].append(key);horizontal['text_parts'].append(item['text'])
                else:
                    group={'locator':key,'row':r,'column':item['column'],'colspan':span,'rowspan':1,
                        'vertical_merge':item['vertical_merge'],'members':[key],'text_parts':[item['text']]}
                    groups.append(group);horizontal=group if item['horizontal_merge']=='restart' else None
            next_vertical={}
            for group in groups:
                interval=(group['column'],group['colspan']);mode=group['vertical_merge']
                if mode=='continue' and interval in previous_vertical:
                    anchor=previous_vertical[interval];anchor['rowspan']=r-anchor['row']+1
                    anchor['members'].extend(group['members']);anchor['text_parts'].extend(group['text_parts'])
                else:
                    anchor=group;anchor['invalid_merge']=mode=='continue' or mode not in {None,'restart'}
                    result['anchors'].append(anchor)
                for member in group['members']:nodes[member]['anchor']=anchor['locator']
                if mode in {'continue','restart'}:next_vertical[interval]=anchor
            result['rows'].append({'index':r,'cells':cells,'column_end':column-1,
                'position':min((nodes[p]['position'] for cell in cells for p in cell['paragraphs']),default=result['position'])})
            previous_vertical=next_vertical
        for anchor in result['anchors']:anchor['text']='\n'.join(text for text in anchor['text_parts'] if text.strip())
        return result

    def walk(parent):
        for child in parent:
            if child.tag==W+'p':add_paragraph(child)
            elif child.tag==W+'tbl':add_table(child)
            elif child.tag in {W+'sdt',W+'sdtContent',W+'customXml'}:walk(child)
    body=document.find(W+'body');walk(body)
    images=len(list(body.iter(W+'drawing')))+len(list(body.iter(W+'pict')))
    return {'nodes':nodes,'paragraphs':paragraphs,'tables':tables,'notes':notes,'events':events,'body_images':images,
        'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'pending_revisions':len(list(body.iter(W+'ins')))+len(list(body.iter(W+'del')))}
