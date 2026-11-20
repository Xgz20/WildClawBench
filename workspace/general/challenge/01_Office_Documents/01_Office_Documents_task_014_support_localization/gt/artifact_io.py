"""Observe real editable Word bodies and CSV records; do not infer translated meaning."""
from pathlib import Path
import csv
import io
import re
import runpy
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
OFFICE=runpy.run_path(str(Path(__file__).with_name('office_runtime.py')))
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT'}
class CandidateError(ValueError):pass
def clean(text):return unicodedata.normalize('NFC',str(text or '')).strip()
def canon(text):return re.sub(r'\s+','',clean(text))
def safe(path,limit=5_242_880):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>limit:
        raise CandidateError('missing, unsafe or oversized output: '+path.name)
    return path
def word(path):
    try:
        raw=safe(path).read_bytes()
        OFFICE['_inspect_docx_render_package'](raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:root=ET.fromstring(archive.read('word/document.xml'))
    except OFFICE['OfficeRuntimeError'] as exc:
        if exc.code not in CONTENT_ERRORS:raise
        raise CandidateError(exc.code) from exc
    except (OSError,ET.ParseError,zipfile.BadZipFile,KeyError) as exc:raise CandidateError(str(exc)) from exc
    body=root.find(W+'body')
    if body is None:raise CandidateError('missing Word body')
    def paragraph(node):
        return clean(''.join(p.text or '' if p.tag==W+'t' else '\t' if p.tag==W+'tab' else '\n' if p.tag in {W+'br',W+'cr'} else '' for p in node.iter()))
    def blocks(node):
        for child in node:
            if child.tag==W+'p':yield paragraph(child)
            elif child.tag==W+'tbl':
                for row in child.findall(W+'tr'):
                    yield '\n'.join(paragraph(p) for cell in row.findall(W+'tc') for p in cell.iter(W+'p'))
            elif child.tag in {W+'sdt',W+'sdtContent',W+'customXml'}:yield from blocks(child)
    texts=[x for x in blocks(body) if x]
    topics={};duplicates=[];current=None;outside=[]
    for text in texts:
        match=re.match(r'^\s*(K\d{2})(?=$|\s|[:：.、)）-])',text)
        if match:
            current=match[1]
            if current in topics:duplicates.append(current)
            topics.setdefault(current,[]).append(text)
        elif current:topics[current].append(text)
        else:outside.append(text)
    return {'topics':topics,'duplicate_ids':duplicates,'paragraphs':texts,'intro':outside,
            'pending_revisions':any(root.iter(W+'del')) or any(root.iter(W+'ins')),
            'body_editable':bool(list(body.iter(W+'t')))}
def replies(path,columns):
    try:
        raw=safe(path,1_048_576).read_text(encoding='utf-8-sig')
        reader=csv.DictReader(io.StringIO(raw,newline=''),strict=True)
        fields=reader.fieldnames or []
        if len(fields)!=len(set(fields)) or not set(columns)<=set(fields):raise CandidateError('missing or duplicate CSV columns')
        rows={};duplicates=[];bad=[]
        for row in reader:
            if None in row or any(v is None for v in row.values()):raise CandidateError('ragged CSV record')
            record={k:clean(v) for k,v in row.items()};identity=record['case_id']
            if not identity:bad.append(record);continue
            if identity in rows:duplicates.append(identity)
            else:rows[identity]=record
        return rows,{'columns':fields,'duplicates':duplicates,'empty_ids':len(bad)}
    except (OSError,UnicodeError,csv.Error) as exc:raise CandidateError(str(exc)) from exc
def refs(text):return set(re.findall(r'(?<![\w/])release_notes\.md\s*#\s*(F\d{2})(?!\d)',clean(text)))
def render(path,lock,derived,paragraphs):
    import pdfplumber
    result=OFFICE['render_docx_pdf'](path,lock,derived,timeout_seconds=90)
    pages=[];chars=[];outside=[]
    with pdfplumber.open(result['path']) as pdf:
        if not pdf.pages:raise RuntimeError('trusted renderer produced no pages')
        for number,page in enumerate(pdf.pages,1):
            pages.append(page.extract_text() or '')
            for char in page.chars:
                if not char['text'].strip():continue
                chars.append(char['text'])
                if char['x0']<-.75 or char['x1']>page.width+.75 or char['top']<-.75 or char['bottom']>page.height+.75:
                    outside.append({'page':number,'text':char['text']})
    native=canon(''.join(paragraphs));visible=canon(''.join(chars))
    # Paragraphs can wrap or span table cells, but their actual native text must be present.
    presence=[canon(p) in visible for p in paragraphs]
    return {'receipt':result['audit'],'pdf':result['path'],'pages':len(pages),'page_text':pages,
            'native_text_visible':presence,'out_of_page':outside,'basic_fit':bool(native and all(presence) and not outside),
            'limit':'PDF text presence and page bounds do not prove contrast, lack of occlusion, language semantics or usable layout.'}
