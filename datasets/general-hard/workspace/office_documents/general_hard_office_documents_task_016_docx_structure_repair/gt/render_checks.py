"""Bound actual Office field rendering, TOC pages and page extents; not a visual Judge."""
import re
import pdfplumber
from pypdf import PdfReader

def canon(s):return re.sub(r'\s+','',s or '')
def render(source,lock,derived,office,expected,original):
    result=office['render_docx_pdf'](source,lock,derived,timeout_seconds=90)
    reader=PdfReader(result['path'],strict=True)
    if not reader.pages:raise RuntimeError('trusted Office produced no pages')
    pages=[p.extract_text() or '' for p in reader.pages]
    lines=[(i,canon(line)) for i,page in enumerate(pages,1) for line in page.splitlines()]
    heading_pages={};heading_visible={};toc_visible={}
    for h in expected['headings']:
        name=canon(h['label']+' '+h['title'])
        hits=[i for i,line in lines if line==name]
        heading_pages[h['paragraph_id']]=hits[0] if len(hits)==1 else None
        heading_visible[h['paragraph_id']]=len(hits)==1
        toc_hits=[]
        for i,line in lines:
            if not line.startswith(name):continue
            tail=line[len(name):]
            m=re.fullmatch(r'[.·…\-]*(\d+)',tail)
            if m:toc_hits.append(int(m[1]))
        toc_visible[h['paragraph_id']]=bool(len(toc_hits)==1 and len(hits)==1 and toc_hits[0]==hits[0])
    text=''.join(line for _,line in lines if not ('CL-SYN-016' in line and '合成资料' in line) and not re.fullmatch(r'\d+[/／]\d+',line))
    public=set(expected['protected']['paragraphs'])
    # Use semantic expected display values read from the clean original before the candidate existed.
    prose={p['id']:canon(p['text']) in text for p in original['paragraphs'] if p['id'] in public}
    captions={t['id']:canon('表 '+str(i)+' '+t['title']) in text for i,t in enumerate(expected['tables'],1)}
    refs={r['paragraph']:prose.get(r['paragraph'],False) for r in expected['references']}
    outside=[]
    with pdfplumber.open(result['path']) as pdf:
        for i,page in enumerate(pdf.pages,1):
            for char in page.chars:
                if char['text'].strip() and (char['x0']<-.75 or char['x1']>page.width+.75 or char['top']<-.75 or char['bottom']>page.height+.75):outside.append({'page':i,'text':char['text']})
    return {'pdf':str(result['path']),'receipt':result['audit'],'page_count':len(pages),'pages_text':pages,
      'heading_pages':heading_pages,'heading_visible':heading_visible,'toc_page_checks':toc_visible,
      'paragraph_visible':prose,'caption_visible':captions,'reference_visible':refs,'out_of_page':outside[:30],
      'basic_fit':bool(all(prose.values()) and all(heading_visible.values()) and all(captions.values()) and all(refs.values()) and not outside),
      'limit':'Native PDF text and page extents only. Full visual Judge must inspect all pages for overlap, occlusion, contrast, readable navigation and honest update claims.'}
