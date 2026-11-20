from pathlib import PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit
from decimal import Decimal,InvalidOperation
import json,re,unicodedata
ALIASES={'发行编号':'release_id','版本':'version','选用分包':'selected_parts','排除分包':'excluded_parts','成员':'members','笔记':'notes','冲突':'conflicts','资源核验':'resource_checks','输入哈希':'input_sha256','分包编号':'part_id','路径':'path','内容哈希':'sha256','发行路径':'release_path','目标路径':'target_path','字节数':'bytes','来源分包':'part_ids','原路径':'source_path','保留用户路径':'retained_user_path','发行旁存路径':'release_saved_as','类型':'kind','来源':'source','原引用':'raw_ref','目标':'target','片段':'fragment','状态':'status','链接':'links','入口':'entrypoint','发行成员数':'release_member_count','笔记数':'note_count','恢复文件数':'restored_file_count','资源关系数':'resource_edge_count'}
def nfc(v):return unicodedata.normalize('NFC',v) if isinstance(v,str) else v
def pairs(items):
    out={}
    for k,v in items:
        k=ALIASES.get(k,k)
        if k in out:raise ValueError('duplicate normalized key')
        out[k]=v
    return out
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs)
def number(v):
    if isinstance(v,bool) or v is None:return None
    try:
        n=Decimal(str(v).replace(',',''));return int(n) if n.is_finite() and n==n.to_integral_value() else None
    except (InvalidOperation,ValueError):return None
def relative(v,kind='restored'):
    if not isinstance(v,str):return None
    v=nfc(v)
    prefix='/tmp_workspace/results/restored/' if kind=='restored' else '/tmp_workspace/'
    if v.startswith(prefix):v=v[len(prefix):]
    if kind=='restored' and v.startswith('restored/'):v=v[len('restored/'):]
    if v.startswith('./'):v=v[2:]
    if not v or v.startswith('/') or re.match(r'^[A-Za-z]:',v) or '\\' in v or any(x in ('','..','.') for x in v.split('/')):return None
    return v
def summary(p):
    text=p.read_text(encoding='utf-8-sig')
    for m in re.finditer(r'```(?:json|JSON)\s*\n(.*?)\n```',text,re.S):
        try:v=json.loads(m.group(1),object_pairs_hook=pairs)
        except ValueError:continue
        if isinstance(v,dict) and 'release_id' in v:return v
    out={}
    for line in text.splitlines():
        cols=[re.sub(r'[`*]','',c.strip()) for c in line.strip().strip('|').split('|')]
        if len(cols)>=2:
            k=ALIASES.get(cols[0],cols[0])
            if k in {'release_id','entrypoint','release_member_count','note_count','restored_file_count','resource_edge_count'}:
                if k in out:raise ValueError('duplicate summary metric')
                out[k]=cols[1]
    return out
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.refs=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get('id'):self.ids.add(a['id'])
        for k in ('href','src'):
            if a.get(k):self.refs.append((k,a[k]))
def graph(files):
    refs=[];anchors={};errors=[]
    for rel,raw in files.items():
        try:text=raw.decode('utf-8')
        except UnicodeError:errors.append({'source':rel,'error':'non_utf8_text'});continue
        try:
            if rel.endswith('.html'):
                p=Parser();p.feed(text);anchors[rel]=p.ids;refs += [(rel,k,url,'file') for k,url in p.refs]
            elif rel.endswith('.css'):refs += [(rel,'css_url',m.group(1),'file') for m in re.finditer(r'url\([\"\']?([^\)\"\']+)[\"\']?\)',text)]
            elif rel.endswith('.md'):refs += [(rel,'markdown',m.group(1),'file') for m in re.finditer(r'\]\(([^)]+)\)',text)]
        except (ValueError,TypeError):errors.append({'source':rel,'error':'parse_failed'})
    if 'data/catalog.json' in files:
        try:
            data=json.loads(files['data/catalog.json']);refs += [('data/catalog.json','catalog_href',r['href'],'root') for r in data['items'] if isinstance(r,dict) and isinstance(r.get('href'),str)]
        except (ValueError,TypeError,KeyError):errors.append({'source':'data/catalog.json','error':'catalog_parse_failed'})
    rows=[]
    for source,kind,raw_ref,base in refs:
        try:
            u=urlsplit(raw_ref);parts=[] if base=='root' else list(PurePosixPath(source).parent.parts);escaped=bool(u.scheme or u.netloc or u.path.startswith('/'));rawpath=unquote(u.path)
            if not rawpath:target=source
            else:
                for p in rawpath.split('/'):
                    if p in ('','.'):continue
                    if p=='..':
                        if not parts:escaped=True;break
                        parts.pop()
                    else:parts.append(p)
                target=nfc('/'.join(parts))
            fragment=unquote(u.fragment);ok=not escaped and target in files and (not fragment or not target.endswith('.html') or fragment in anchors.get(target,set()));rows.append({'source':source,'kind':kind,'raw_ref':raw_ref,'target':target,'fragment':fragment,'status':'resolved' if ok else 'broken'})
        except (ValueError,TypeError):rows.append({'source':source,'kind':kind,'raw_ref':str(raw_ref),'target':None,'fragment':'','status':'broken'})
    return rows,errors
def edge_key(r):return (relative(r.get('source')),relative(r.get('target')),nfc(r.get('fragment')) if isinstance(r.get('fragment'),str) else '')
def version(v):
    if not isinstance(v,str):return None
    v=v.lstrip('vV')
    if not re.fullmatch(r'\d+\.\d+\.\d+',v):return None
    return tuple(map(int,v.split('.')))
def flatten(resources):
    rows=[]
    for r in resources if isinstance(resources,list) else []:
        if not isinstance(r,dict):continue
        if isinstance(r.get('links'),list):rows += [{**x,'source':r.get('source'),'status':x.get('status',r.get('status'))} for x in r['links'] if isinstance(x,dict)]
        else:rows.append(r)
    return rows
