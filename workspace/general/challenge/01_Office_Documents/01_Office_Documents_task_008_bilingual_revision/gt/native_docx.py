"""Visible native paragraphs/tables and selected effective formatting, stdlib only."""
from pathlib import Path
from copy import deepcopy
import re,unicodedata,zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
class CandidateDocumentError(ValueError):pass
def canon(value):
    text=unicodedata.normalize('NFKC',str(value or ''))
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P'))
def integer(value):
    try:return int(value)
    except (ValueError,TypeError):return None
def val(node,name,default=None):
    item=node.find(W+name) if node is not None else None
    return item.get(W+'val',default) if item is not None else default
def props(node):
    result={}
    if node is None:return result
    for child in node:
        key=child.tag.removeprefix(W)
        if key in ('rPr','pPr'):result.update(props(child))
        elif key=='rFonts':result['font']=child.get(W+'eastAsia') or child.get(W+'ascii') or child.get(W+'hAnsi')
        elif key in ('sz','b','i','u','color','vanish'):
            value=child.get(W+'val','1')
            if key=='sz':value=integer(value)
            if key in ('b','i','vanish'):value=value not in ('0','false','off')
            if key=='color':value='000000' if value=='auto' else value.upper()
            result[key]=value
        elif key in ('spacing','ind'):result[key]={k.removeprefix(W):v for k,v in child.attrib.items()}
        elif key in ('jc','keepNext','pageBreakBefore'):result[key]=child.get(W+'val','1')
        elif key=='numPr':result['numId']=val(child,'numId');result['ilvl']=val(child,'ilvl','0')
    return result
def safe_parts(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>5_242_880:raise CandidateDocumentError('not a regular DOCX within size budget')
    try:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist();names=[entry.filename for entry in entries]
            if len(names)!=len(set(names)) or sum(e.file_size for e in entries)>30_000_000:raise CandidateDocumentError('unsafe package size or duplicate members')
            if any(n.startswith(('/','\\')) or '..' in n.replace('\\','/').split('/') for n in names):raise CandidateDocumentError('unsafe package path')
            parts={name:archive.read(name) for name in names}
            if not {'[Content_Types].xml','_rels/.rels','word/document.xml'}<=set(parts):raise CandidateDocumentError('missing native Word package contract')
            try:
                types=ET.fromstring(parts['[Content_Types].xml']);relationships=ET.fromstring(parts['_rels/.rels'])
                main_type=any(node.get('PartName')=='/word/document.xml' and node.get('ContentType')=='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' for node in types)
                main_link=any(node.get('Type','').endswith('/officeDocument') and node.get('Target','').lstrip('/')=='word/document.xml' and node.get('TargetMode')!='External' for node in relationships)
                if not main_type or not main_link:raise CandidateDocumentError('invalid native Word document type or root relationship')
            except ET.ParseError as exc:raise CandidateDocumentError('invalid package contract XML') from exc
            return parts
    except (OSError,zipfile.BadZipFile,RuntimeError) as exc:raise CandidateDocumentError('unreadable DOCX package') from exc
def read_document(path):
    parts=safe_parts(path)
    try:
        doc=ET.fromstring(parts['word/document.xml']);body=doc.find(W+'body')
        if body is None:raise CandidateDocumentError('missing document body')
        styles=ET.fromstring(parts['word/styles.xml']) if 'word/styles.xml' in parts else ET.Element('styles')
        numbering=ET.fromstring(parts['word/numbering.xml']) if 'word/numbering.xml' in parts else ET.Element('numbering')
    except (KeyError,ET.ParseError) as exc:raise CandidateDocumentError('invalid native document XML') from exc
    style_map={s.get(W+'styleId'):s for s in styles.findall(W+'style')}
    defaults=props(styles.find(W+'docDefaults'));defaults.setdefault('color','000000')
    def style_props(identity,seen=()):
        if identity in seen or identity not in style_map:return {}
        node=style_map[identity];base=val(node,'basedOn')
        return {**style_props(base,(*seen,identity)),**props(node)}
    abstract={a.get(W+'abstractNumId'):{l.get(W+'ilvl'):l for l in a.findall(W+'lvl')} for a in numbering.findall(W+'abstractNum')}
    number_map={n.get(W+'numId'):n for n in numbering.findall(W+'num')};counters={}
    def list_number(properties):
        identity=properties.get('numId');level=properties.get('ilvl','0')
        if not identity or identity=='0':return None
        instance=number_map.get(identity)
        if instance is None:return None
        definition=abstract.get(val(instance,'abstractNumId'),{}).get(level)
        if definition is None:return None
        override=next((x for x in instance.findall(W+'lvlOverride') if x.get(W+'ilvl')==level),None)
        if val(definition,'numFmt') not in ('decimal','decimalZero'):return None
        start=integer(val(override,'startOverride')) if override is not None else None
        if start is None:start=integer(val(definition,'start','1'))
        key=(identity,level);counters[key]=counters.get(key,start-1)+1
        return counters[key]
    def runs(parent):
        for child in parent:
            if child.tag in (W+'del',W+'moveFrom',W+'drawing',W+'pict',W+'object'):continue
            if child.tag==W+'r':yield child
            else:yield from runs(child)
    def run_text(parent):
        out=[]
        for child in parent:
            if child.tag in (W+'del',W+'moveFrom',W+'drawing',W+'pict',W+'object'):continue
            if child.tag==W+'t':out.append(child.text or '')
            elif child.tag==W+'tab':out.append('\t')
            elif child.tag in (W+'br',W+'cr'):out.append('\n')
            else:out.append(run_text(child))
        return ''.join(out)
    def paragraph(node,location):
        ppr=node.find(W+'pPr');style_id=val(ppr,'pStyle','Normal')
        properties={**defaults,**style_props(style_id),**props(ppr)}
        segments=[]
        for run in runs(node):
            rpr=run.find(W+'rPr');settings={**properties,**style_props(val(rpr,'rStyle')),**props(rpr)}
            if settings.get('vanish'):continue
            value=run_text(run)
            if value:segments.append({'text':value,'format':{k:settings.get(k) for k in ('font','sz','b','i','u','color')}})
        return {'kind':'paragraph','text':''.join(s['text'] for s in segments),'style':style_id,'format':properties,
                'segments':segments,'list_number':list_number(properties),'bookmarks':[b.get(W+'name') for b in node.iter(W+'bookmarkStart')],
                'locator':location}
    def nodes(parent):
        for node in parent:
            if node.tag in (W+'p',W+'tbl'):yield node
            elif node.tag in (W+'sdt',W+'sdtContent',W+'customXml',W+'ins',W+'moveTo'):yield from nodes(node)
    blocks=[];paragraph_count=table_count=0
    for node in nodes(body):
        if node.tag==W+'p':
            paragraph_count+=1;item=paragraph(node,'paragraph:'+str(paragraph_count))
            if item['text'].strip():blocks.append(item)
        else:
            table_count+=1;rows=[];formats=[]
            for i,row in enumerate(node.findall(W+'tr'),1):
                cells=[];cell_formats=[]
                for j,cell in enumerate(row.findall(W+'tc'),1):
                    paras=[paragraph(p,f'table:{table_count}/row:{i}/cell:{j}/p:{n}') for n,p in enumerate(cell.findall(W+'p'),1)]
                    cells.append({'text':'\n'.join(p['text'] for p in paras),'paragraphs':paras})
                    tcpr=cell.find(W+'tcPr')
                    cell_formats.append(ET.tostring(tcpr,encoding='unicode') if tcpr is not None else '')
                rows.append(cells);formats.append(cell_formats)
            blocks.append({'kind':'table','rows':rows,'grid':[integer(x.get(W+'w')) for x in node.findall(W+'tblGrid/'+W+'gridCol')],
                'cell_properties':formats,'locator':'table:'+str(table_count)})
    section=body.find(W+'sectPr');page={}
    if section is not None:
        for tag in ('pgSz','pgMar','cols'):
            node=section.find(W+tag)
            page[tag]={k.removeprefix(W):v for k,v in node.attrib.items()} if node is not None else {}
    extra=[]
    for name,data in parts.items():
        if re.fullmatch(r'word/(header|footer)\d+\.xml',name):
            try:extra.append(''.join(n.text or '' for n in ET.fromstring(data).iter(W+'t')))
            except ET.ParseError as exc:raise CandidateDocumentError('invalid header/footer XML') from exc
    return {'blocks':blocks,'page_setup':page,'header_footer_text':extra}

def main_paragraphs(document):return [b for b in document['blocks'] if b['kind']=='paragraph']
def step_value(paragraph):
    text=paragraph['text'].strip();match=re.match(r'^([1-9][0-9]*)[\s.、)）]+(.*)$',unicodedata.normalize('NFKC',text),re.S)
    return (int(match[1]),match[2]) if match else (paragraph['list_number'],text)
def physical_source_model(path):
    document=read_document(path);paragraphs=main_paragraphs(document)
    by_name={name:p for p in paragraphs for name in p['bookmarks']}
    if len(by_name)!=16:raise ValueError('source bookmarks incomplete')
    return document,by_name
