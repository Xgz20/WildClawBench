"""Frozen existing native Word visibility/PDF helpers; business facts live separately."""
import re,runpy,unicodedata,xml.etree.ElementTree as E

from pathlib import Path

import pdfplumber

from pypdf import PdfReader

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def visibility_risks(source,word_api):
    parts=word_api['_parts'](source);doc=word_api['_xml'](parts['word/document.xml']);styles=word_api['_xml'](parts['word/styles.xml']) if 'word/styles.xml' in parts else E.Element(W+'styles');nodes={s.get(W+'styleId'):s for s in styles.findall(W+'style')};parent={c:p for p in doc.iter() for c in p};images=any(n.tag in {W+'drawing',W+'pict'} for n in doc.iter())
    def val(n,key):
        x=n.find(W+key) if n is not None else None
        return x.get(W+'val') if x is not None else None
    def props(pr):
        if pr is None:return {}
        out={k:val(pr,k) for k in ['sz','color'] if val(pr,k) is not None}
        for key in ['vanish','webHidden']:
            n=pr.find(W+key)
            if n is not None:out[key]=n.get(W+'val','1').lower() not in {'0','false','off'}
        return out
    def inherited(s,seen=()):
        if s in seen:raise word_api['CandidateWordError']('cyclic Word run style')
        n=nodes.get(s)
        if n is None:return {}
        base=val(n,'basedOn');return {**(inherited(base,seen+(s,)) if base else {}),**props(n.find(W+'rPr'))}
    defaults=props(styles.find(W+'docDefaults/'+W+'rPrDefault/'+W+'rPr'));risks=[]
    for p in doc.iter(W+'p'):
        pp=p.find(W+'pPr');style=val(pp,'pStyle');shade=pp.find(W+'shd') if pp is not None else None;cur=parent.get(p)
        while shade is None and cur is not None:
            if cur.tag==W+'tc':shade=cur.find(W+'tcPr/'+W+'shd')
            cur=parent.get(cur)
        fill=shade.get(W+'fill','AUTO').upper() if shade is not None else 'AUTO'
        for r in p.iter(W+'r'):
            text=''.join(n.text or '' for n in r.iter(W+'t'))
            if not text.strip():continue
            rp=r.find(W+'rPr');pr={**defaults,**inherited(style),**inherited(val(rp,'rStyle')),**props(rp)}
            try:tiny=float(pr.get('sz','22'))<12
            except ValueError as e:raise word_api['CandidateWordError']('invalid Word font size') from e
            if pr.get('vanish') or pr.get('webHidden') or tiny or not images and str(pr.get('color','')).upper()=='FFFFFF' and fill in {'AUTO','FFFFFF','NIL'}:risks.append(text)
    return risks

def render(source,lock,derived,office,texts,io):
    result=office['render_docx_pdf'](source,lock,derived,timeout_seconds=90);reader=PdfReader(result['path'],strict=True)
    if not reader.pages:raise RuntimeError('trusted Office returned an empty PDF')
    chars=[];outside=[]
    with pdfplumber.open(result['path']) as document:
        for i,page in enumerate(document.pages,1):
            for char in page.chars:
                if not char['text'].strip():continue
                if char['x0']<-.75 or char['x1']>page.width+.75 or char['top']<-.75 or char['bottom']>page.height+.75:outside.append({'page':i,'text':char['text']})
                else:chars.append(char['text'])
    native=[io['canon'](t) for t in texts if io['canon'](t)];visible=io['canon'](''.join(chars));present=[s in visible for s in native]
    return {'pdf':str(result['path']),'receipt':result['audit'],'page_count':len(reader.pages),'native_text_present':present,'out_of_page':outside[:30],'basic_fit':bool(present and all(present) and not outside),'limit':'Bounded PDF text/page extents plus native style risks, not a full visual-usability score.'}
