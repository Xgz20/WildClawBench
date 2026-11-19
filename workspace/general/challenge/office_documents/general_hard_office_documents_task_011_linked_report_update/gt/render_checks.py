"""Actual locked Office PDF text and page bounds; full visuals remain a Judge duty."""
from pathlib import Path
import re
import pdfplumber
from pypdf import PdfReader
def render(source,lock,derived,texts,kind,io):
    result=io['OFFICE']['render_docx_pdf' if kind=='word' else 'render_pptx_pdf'](source,lock,derived,timeout_seconds=90)
    reader=PdfReader(result['path'],strict=True)
    if not reader.pages:raise RuntimeError('trusted Office produced no pages')
    chars=[];outside=[];pages=[]
    with pdfplumber.open(result['path']) as document:
        for number,page in enumerate(document.pages,1):
            pages.append(page.extract_text() or '')
            for char in page.chars:
                if not char['text'].strip():continue
                if char['x0']<-.75 or char['x1']>page.width+.75 or char['top']<-.75 or char['bottom']>page.height+.75:outside.append({'page':number,'text':char['text']})
                else:chars.append(char['text'])
    visible=io['canon'](''.join(chars));native=[io['canon'](v) for v in texts if io['canon'](v)]
    presence=[v in visible for v in native]
    return {'pdf':str(result['path']),'receipt':result['audit'],'page_count':len(reader.pages),'out_of_page':outside[:30],
        'native_text_visible':presence,'missing_native_text':[text for text,ok in zip(texts,presence) if not ok][:30],
        'basic_fit':bool(presence and all(presence) and not outside),'pages_text':pages,
        'limit':'Bound PDF text and page bounds do not establish chart visibility, occlusion, contrast or usable layout. Independent visual Judge required.'}
