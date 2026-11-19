"""Read only production sealed policy-v2 sources; resolve the requested native locator.
No fetch, candidate snapshot, author truth path or source count/URL answer roster.
"""
from pathlib import Path, PurePosixPath
import hashlib, json, os, re, zipfile, io
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

class TrustedSourceError(RuntimeError):pass
class UnsupportedLocator(TrustedSourceError):pass
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError) as e:raise TrustedSourceError('sealed JSON unavailable: '+str(path.name)) from e
def within(root,name):
    if not isinstance(name,str) or not name or name.startswith('/') or '\\' in name or any(x in ('','.','..') for x in name.split('/')):raise TrustedSourceError('unsafe sealed source path')
    p=root/name
    if p.is_symlink() or root.resolve() not in p.resolve().parents:raise TrustedSourceError('sealed path escape')
    if not p.is_file():raise TrustedSourceError('sealed source member missing: '+name)
    return p
def norm(s):return re.sub(r'\s+','',s)
def literal(quote,text,exact=False):
    """Only whitespace normalization. Punctuation, units and every digit remain literal.
    Cell values are exact; prose numeric edges cannot match another number's substring.
    """
    q,t=norm(quote),norm(text)
    if not q:return False
    if exact:return q==t
    pattern=(r'(?<![0-9])' if q[0].isdigit() else '')+re.escape(q)+(r'(?![0-9])' if q[-1].isdigit() else '')
    return re.search(pattern,t) is not None
def load_bundle(candidate,gt,derived,ledger):
    name=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE');digest=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256')
    if not name or not digest:raise TrustedSourceError('required trusted production source context missing')
    root=Path(name)
    if root.is_symlink() or not root.is_dir():raise TrustedSourceError('sealed source directory unavailable')
    root=root.resolve()
    if any(root==p or p in root.parents or root in p.parents for p in (candidate,gt,derived)):raise TrustedSourceError('source context overlaps candidate, GT or derivative')
    manifest=within(root,'manifest.json')
    if sha(manifest)!=digest:raise TrustedSourceError('trusted source manifest digest mismatch')
    doc=read(manifest)
    if doc.get('schema_version')!='wildclawbench.research-source-bundle/v2' or doc.get('policy',{}).get('projection_profile')!='public-native-text-cells/v1':raise TrustedSourceError('required v2 native source profile absent')
    attempt=root.parent.parent;lock=read(attempt/'research-sources.lock.json')
    inventory=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise TrustedSourceError('symlink in source bundle')
        if p.is_file():inventory.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':sha(p)})
    if lock.get('entries')!=inventory or lock.get('bundle_manifest_sha256')!=digest or lock.get('bindings')!=doc.get('bindings'):raise TrustedSourceError('production lock/inventory/bindings mismatch')
    binding={x['path']:x for x in doc.get('bindings',{}).get('deliverables',[])}
    for path in doc['policy']['deliverable_paths']:
        p=candidate/path;exists=p.is_file() and not p.is_symlink();x=binding.get(path,{})
        if x.get('exists')!=exists or x.get('sha256')!=(sha(p) if exists else None):raise TrustedSourceError('candidate delivery/source binding mismatch')
    trusted={};receipts=[]
    if doc.get('candidate_input_status')!='valid':
        return {'root':root,'manifest_sha256':digest,'sources':{},'receipts':[],'acquisition_summary':doc.get('acquisition_summary'),'reuse_origins':doc.get('reuse_origins',[]),'candidate_input_error':doc.get('errors',['invalid source descriptor'])}
    for s in doc.get('sources',[]):
        sid=s.get('source_id')
        if sid in trusted:raise TrustedSourceError('duplicate sealed source id')
        if s.get('status')=='candidate_invalid':trusted[sid]={'candidate_invalid':True,'source':s};continue
        if s.get('status') not in ('acquired','reused'):raise TrustedSourceError('required source not acquired: '+str(sid))
        body=within(root,s['body_path']);projection=within(root,s['projection_path']);receipt=within(root,s['receipt_path'])
        if sha(body)!=s.get('body_sha256') or sha(projection)!=s.get('projection_sha256') or sha(receipt)!=s.get('receipt_sha256'):raise TrustedSourceError('sealed body/projection/receipt drift')
        proj=read(projection)
        if proj.get('schema_version')!='wildclawbench.research-source-text/v2' or proj.get('profile')!='public-native-text-cells/v1' or proj.get('source_sha256')!=sha(body) or proj.get('complete') is not True:raise TrustedSourceError('incomplete or wrong-lineage native projection')
        if proj.get('format') in ('docx','xlsx'):
            try:
                with zipfile.ZipFile(body) as z:
                    actual=[{'part':i.filename,'bytes':i.file_size,'sha256':hashlib.sha256(z.read(i)).hexdigest()} for i in z.infolist()]
                    declared=proj.get('coverage',{}).get('parts')
                    if sorted(actual,key=lambda x:x['part'])!=sorted(declared or [],key=lambda x:x['part']):raise TrustedSourceError('native part inventory mismatch')
                    parts={v['part']:v['sha256'] for v in actual}
                    for r in proj.get('records',[]):
                        loc=r.get('locator',{})
                        if loc.get('part') and loc.get('part_sha256')!=parts.get(loc['part']):raise TrustedSourceError('native record part lineage mismatch')
            except zipfile.BadZipFile as e:raise TrustedSourceError('sealed native body corrupt') from e
        trusted[sid]={'source':s,'projection':proj,'body':body,'receipt':read(receipt)}
        receipts.append({'source_id':sid,'url':s['url'],'final_url':s.get('final_url'),'status':s['status'],'body_sha256':sha(body),'projection_sha256':sha(projection),'receipt_sha256':sha(receipt),'format':proj['format']})
    for carrier in ledger.get('carriers',[]):
        if carrier.get('access_status') not in ('read_full','read_excerpt') and not carrier.get('citations'):continue
        source=trusted.get(carrier.get('carrier_id'))
        if source is None:raise TrustedSourceError('required declared content source absent')
        s=source['source']
        if s.get('url')!=carrier.get('url') or s.get('citations')!=carrier.get('citations'):raise TrustedSourceError('ledger/source descriptor mismatch')
    return {'root':root,'manifest_sha256':digest,'sources':trusted,'receipts':receipts,'acquisition_summary':doc.get('acquisition_summary'),'reuse_origins':doc.get('reuse_origins',[])}

class Node:
    def __init__(self,tag,attrs=(),parent=None):self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.children=[];self.content=[]
    def text(self):return ''.join(x.text() if isinstance(x,Node) else x for x in self.content)
    def all(self):
        yield self
        for x in self.children:yield from x.all()
class DOM(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self,body):
        super().__init__(convert_charrefs=True);self.root=Node('#document');self.stack=[self.root];self.count=0;self.feed(body);self.close()
    def handle_starttag(self,tag,attrs):
        self.count+=1
        if self.count>300000 or len(self.stack)>128:raise TrustedSourceError('HTML DOM bound exceeded')
        if tag in ('li','p','tr','td','th','option') and self.stack[-1].tag==tag:self.stack.pop()
        n=Node(tag,attrs,self.stack[-1]);self.stack[-1].children.append(n);self.stack[-1].content.append(n)
        if tag not in self.VOID:self.stack.append(n)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if self.stack[-1].tag==tag:self.stack.pop()
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:del self.stack[i:];break
    def handle_data(self,s):self.stack[-1].content.append(s)
def html_dom(source):
    if 'dom' in source:return source['dom']
    raw=source['body'].read_bytes();m=re.search(br'charset\s*=\s*["\']?([A-Za-z0-9_-]+)',raw[:10000],re.I)
    charset=m.group(1).decode('ascii') if m else 'utf-8'
    try:body=raw.decode(charset,errors='strict')
    except (LookupError,UnicodeError):
        try:body=raw.decode('utf-8-sig')
        except UnicodeError as e:raise TrustedSourceError('sealed HTML encoding unsupported') from e
    source['dom']=DOM(body).root;return source['dom']
def xpath_html(root,path):
    if not isinstance(path,str) or not path.startswith('/') or '//' in path:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: legal HTML XPath outside bounded absolute element subset')
    nodes=[root]
    for segment in path[1:].split('/'):
        m=re.fullmatch(r'([A-Za-z][\w-]*)(?:\[(\d+)\])?',segment)
        if not m:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: HTML XPath expression not implemented')
        tag,pos=m.group(1).lower(),int(m.group(2) or '1');selected=[]
        for n in nodes:
            choices=[c for c in n.children if c.tag==tag]
            if pos>0 and len(choices)>=pos:selected.append(choices[pos-1])
        nodes=selected
    return nodes
def css_html(root,selector):
    # Bounded ordinary descendant/child compounds and nth-of-type; no regex rewrite to global text.
    if any(x in selector for x in (',','+','~','[')):raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: CSS expression outside bounded selector subset')
    tokens=re.findall(r'[^\s>]+|>',selector);nodes=[root];direct=False
    for token in tokens:
        if token=='>':direct=True;continue
        m=re.fullmatch(r'([A-Za-z][\w-]*|\*)?((?:[#.][\w-]+)*)(?::nth-of-type\((\d+)\))?',token)
        if not m:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: CSS selector not implemented')
        tag,attrs,pos=m.groups();selected=[]
        for n in nodes:
            for c in (n.children if direct else list(n.all())[1:]):
                if tag and tag!='*' and c.tag!=tag:continue
                if any((c.attrs.get('id')!=x[1:] if x.startswith('#') else x[1:] not in c.attrs.get('class','').split()) for x in re.findall(r'[#.][\w-]+',attrs)):continue
                if pos and (not c.parent or [v for v in c.parent.children if v.tag==c.tag].index(c)+1!=int(pos)):continue
                if c not in selected:selected.append(c)
        nodes=selected;direct=False
    return nodes
def resolve_html(source,loc):
    root=html_dom(source)
    if loc.get('xpath'):nodes=xpath_html(root,loc['xpath'])
    elif loc.get('css_selector'):nodes=css_html(root,loc['css_selector'])
    elif loc.get('text_anchor'):
        anchor=loc['text_anchor'];matches=[n for n in root.all() if anchor in n.text() and n.tag not in ('script','style')]
        nodes=[n for n in matches if not any(anchor in c.text() for c in n.children)]
    else:return [],[]
    if len(nodes)!=1:return [],[{'candidate_node_count':len(nodes),'ambiguous':len(nodes)>1}]
    n=nodes[0];return [n.text()],[{'kind':'HTML_DOM','requested_locator':loc,'tag':n.tag,'attributes':n.attrs,'raw_text':n.text(),'body_sha256':source['source']['body_sha256']}]

def row_key(loc):return loc.get('part'),loc.get('node','').split('/cell:',1)[0]
def docx_records(source,loc):
    part=loc.get('part');records=source['projection']['records'];node=None
    if part!='word/document.xml' and part in {p.get('part') for p in source['projection'].get('coverage',{}).get('parts',[])}:
        raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: existing ancillary DOCX part requires its own bounded paragraph/footnote/header addressing')
    if loc.get('xpath'):
        path=loc['xpath'];m=re.fullmatch(r'/w:document/w:body/w:p\[(\d+)\]',path)
        if m:node='paragraph:'+m.group(1)
        else:
            m=re.fullmatch(r'/w:document/w:body/w:tbl\[(\d+)\]/w:tr\[(\d+)\](?:/w:tc\[(\d+)\])?',path)
            if m:node=f'table:{m.group(1)}/row:{m.group(2)}'+(f'/cell:{m.group(3)}' if m.group(3) else '')
            else:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: DOCX XPath outside bounded paragraph/table-row/cell subset')
    elif loc.get('paragraph_1based'):node='paragraph:'+str(loc['paragraph_1based'])
    elif loc.get('table_1based') and loc.get('row_1based'):
        node=f"table:{loc['table_1based']}/row:{loc['row_1based']}"+(f"/cell:{loc['cell_1based']}" if loc.get('cell_1based') else '')
    else:return []
    return [r for r in records if r.get('locator',{}).get('part')==part and (r['locator'].get('node')==node or '/cell:' not in node and r['locator'].get('node','').startswith(node+'/cell:'))]
def colnum(s):
    n=0
    for c in s:n=n*26+ord(c)-64
    return n
def cellkey(s):
    m=re.fullmatch(r'\$?([A-Z]+)\$?([1-9][0-9]*)',s)
    return (int(m.group(2)),colnum(m.group(1))) if m else None
def xlsx_records(source,loc):
    value=loc.get('cell_or_range','').upper();parts=value.split(':')
    if len(parts)>2 or any(cellkey(p) is None for p in parts):raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: XLSX area syntax outside bounded rectangular A1 subset')
    start,end=cellkey(parts[0]),cellkey(parts[-1]);rs=[]
    if end<start:return []
    for r in source['projection']['records']:
        l=r.get('locator',{});k=cellkey(l.get('cell',''))
        if l.get('sheet')==loc.get('sheet') and k and start[0]<=k[0]<=end[0] and start[1]<=k[1]<=end[1] and (loc.get('part') is None or l.get('part')==loc['part']):rs.append(r)
    return sorted(rs,key=lambda r:cellkey(r['locator']['cell']))
def resolve(source,citation):
    loc=citation.get('locator',{});kind=loc.get('type');fmt=source['projection']['format'];quote=citation.get('quote','');texts=[];lineage=[];role_ok=True
    if kind!=fmt:
        if fmt=='html' and kind in ('docx','xlsx','pdf'):
            body=source['body'].read_bytes()[:200000].decode('utf-8',errors='replace')
            barrier=re.search(r'<title[^>]*>[^<]*(?:captcha|验证码|用户登录|统一身份认证)|(?:cf-chl-|challenge-platform)|<form\b[\s\S]{0,20000}(?:captcha|verifycode|验证码)',body,re.I)
            if barrier:raise UnsupportedLocator('NEEDS_SOURCE_REVIEW: actual acquisition is a challenge/login HTML response replacing the cited native source')
        if kind in ('legacy_xls','search_snippet','unavailable'):raise UnsupportedLocator('NEEDS_SOURCE_REVIEW: declared legal evidence kind needs independent supported collection')
        return {'resolved':False,'reason':'locator_actual_format_mismatch','actual_format':fmt,'locator':loc}
    if kind=='html':texts,lineage=resolve_html(source,loc)
    elif kind=='pdf':
        records=[r for r in source['projection']['records'] if r.get('locator',{}).get('page')==loc.get('physical_page_1based')];texts=[r['text'] for r in records];lineage=records
    elif kind=='docx':
        records=docx_records(source,loc);texts=[''.join(r['text'] for r in records)] if records else [];lineage=records
    elif kind=='xlsx':
        records=xlsx_records(source,loc);role=loc.get('value_role');lineage=records
        for r in records:
            n=r.get('native',{});formula=n.get('formula')
            if role=='literal_value':
                if formula is not None:role_ok=False
                texts.append(r['text'])
            elif role=='formula_text':
                if formula is None:role_ok=False
                else:texts.append(str(formula))
            elif role=='cached_result_unverified':texts.append(r['text'])
            elif role=='recalculated_result_with_receipt':raise UnsupportedLocator('NEEDS_SOURCE_FORMULA_REVIEW: source formula truth needs actual bound recalculation receipt')
            else:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: unknown source value role')
    else:raise UnsupportedLocator('NEEDS_LOCATOR_REVIEW: source format not implemented')
    exact=kind=='xlsx' and ':' not in loc.get('cell_or_range','')
    passed=role_ok and any(literal(quote,t,exact=exact) for t in texts)
    if kind=='xlsx' and not exact and texts:passed=role_ok and literal(quote,''.join(texts))
    return {'resolved':passed,'reason':'literal_at_requested_locator' if passed else 'quote_locator_or_value_role_mismatch','locator':loc,'raw_selected_text':texts,'lineage':lineage,'normalization':'Unicode whitespace only; digits/punctuation/units preserved; numeric edge boundaries; single cell exact','body_sha256':source['source']['body_sha256'],'projection_sha256':source['source']['projection_sha256'],'semantic_support':'NOT_DECIDED','source_reading_trace':'NOT_PROVED'}
def official_alias_links(bundle,entries):
    seeds={urlsplit(v['url']).hostname for v in entries['seed_entries']};results=[]
    for source in bundle['sources'].values():
        if source.get('candidate_invalid'):continue
        if source['projection']['format']!='html':continue
        u=source['source'].get('final_url') or source['source']['url'];host=(urlsplit(u).hostname or '').rstrip('.')
        if host not in seeds and u not in {v['url'] for v in entries['identity_only_pages']}:continue
        for n in html_dom(source).all():
            if n.tag=='a' and n.attrs.get('href'):
                dest=urljoin(u,n.attrs['href'])
                if (urlsplit(dest).hostname or '').rstrip('.')=='law.hbu.cn':results.append({'source_url':u,'target_url':dest,'anchor':n.text(),'source_body_sha256':source['source']['body_sha256']})
    return results
