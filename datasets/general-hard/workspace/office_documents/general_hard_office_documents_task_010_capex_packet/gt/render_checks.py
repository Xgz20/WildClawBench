"""Frozen Writer PDF text and page-bound observations, not a complete visual Judge."""
from pathlib import Path
import re
import pdfplumber
from pypdf import PdfReader

def render(source,lock,derived,word,io):
    result=io['OFFICE']['render_docx_pdf'](source,lock,derived,timeout_seconds=75)
    pdf=Path(result['path']);reader=PdfReader(pdf,strict=True)
    if not reader.pages:raise RuntimeError('Trusted Writer produced empty PDF')
    chars=[];outside=[]
    with pdfplumber.open(pdf) as document:
        for i,page in enumerate(document.pages,1):
            for c in page.chars:
                if c['text'].strip():
                    if c['x0']<-.75 or c['x1']>page.width+.75 or c['top']<-.75 or c['bottom']>page.height+.75:outside.append({'page':i,'text':c['text']})
                    else:chars.append(c['text'])
    visible=io['canon'](''.join(chars))
    texts=[p['text'] for p in word['paragraphs'] if io['canon'](p['text'])]
    observations=[io['canon'](v) in visible for v in texts]
    return {'pdf':str(pdf),'receipt':result['audit'],'page_count':len(reader.pages),'out_of_page':outside[:30],
        'native_text_visible':observations,'missing_native_text':[v for v,good in zip(texts,observations) if not good][:20],
        'basic_fit':bool(observations and all(observations) and not outside),
        'limit':'Actual PDF text and page bounds only. Full occlusion, contrast, typography and usable layout require independent visual Judge.'}
