"""Native report quantitative facts and fixed source quotations; basic visibility."""
import re,runpy,unicodedata,xml.etree.ElementTree as E
from pathlib import Path
import pdfplumber
from pypdf import PdfReader
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def word_checks(model,expected,contract,io):
    if model is None:return {'score':0.,'metrics':{},'statistics':{},'quotes':{},'complete':False}
    grids=io['grids_word'](model);rows=io['flatten'](io['discover'](grids,contract['word_metric_aliases'],['metric_id','raw_num','raw_den','raw_rate','weighted_rate'],id_field='metric_id',id_test=lambda v:io['canon'](v) in {io['canon'](m['metric_id']) for m in expected['metrics']}));by_id={}
    for row in rows:by_id.setdefault(io['canon'](row['metric_id']),[]).append(row)
    metrics={}
    for m in expected['metrics']:
        hits=by_id.get(io['canon'](m['metric_id']),[]);row=hits[0] if len(hits)==1 else None;checks={}
        for key in ['raw_num','raw_den','raw_rate','weighted_rate']:
            header=unicodedata.normalize('NFKC',str(row['_locations'][key]['header'])) if row else '';percent='%' in header or '百分' in header
            checks[key]=bool(row and io['equal'](row[key],expected['baseline'][m['metric_id']][key],.00051 if 'rate' in key else 0,word=True,percent_header=percent))
        metrics[m['metric_id']]=checks
    stats=io['flatten'](io['discover'](grids,contract['word_stat_aliases'],['item','value'],id_field='item',id_test=lambda v:io['canon'](v) in contract['stat_label_lookup']));by_stat={}
    for row in stats:by_stat.setdefault(contract['stat_label_lookup'][io['canon'](row['item'])],[]).append(row)
    stat_checks={key:len(by_stat.get(key,[]))==1 and io['equal'](by_stat[key][0]['value'],expected['statistics'][key],word=True) for key in contract['report_statistics']}
    texts=[p['text'] for p in model['paragraphs']]
    referenced={ref['note_locator'] for p in model['paragraphs'] for ref in p['references'] if ref['available']}
    texts += [model['notes'][k]['text'] for k in referenced]
    flat=io['canon'](' '.join(texts));quote_canon=lambda v:re.sub(r'\s+','',unicodedata.normalize('NFKC',str(v))).casefold();quote_flat=quote_canon(' '.join(texts));quotes={key:io['canon'](key) in flat and quote_canon(text) in quote_flat for key,text in expected['quotes'].items()}
    score=.7*mean(mean(v.values()) for v in metrics.values())+.2*mean(stat_checks.values())+.1*mean(quotes.values())
    return {'score':score,'metrics':metrics,'statistics':stat_checks,'quotes':quotes,'complete':all(all(v.values()) for v in metrics.values()) and all(stat_checks.values()) and all(quotes.values()),'texts':texts}
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
