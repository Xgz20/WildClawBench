"""Read actual native nodes and conservative static HTML; no business truth here."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from collections import defaultdict
from html.parser import HTMLParser
import hashlib,json,posixpath,re,runpy,unicodedata,zipfile
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
OFFICE=runpy.run_path(str(HERE/'office_runtime.py'))
NATIVE=runpy.run_path(str(HERE/'native_text.py'))
WORD=runpy.run_path(str(HERE/'word_model.py'))
GRID=runpy.run_path(str(HERE/'html_grid.py'))
class CandidateError(ValueError):pass

def clean(value):return unicodedata.normalize('NFKC','' if value is None else str(value)).strip()
def key(value):return re.sub(r'[\s_（）()]','',clean(value)).casefold()
def canon(value):return re.sub(r'\s+','',clean(value)).replace(',','').casefold()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):values=list(values);return sum(values)/len(values) if values else 0.
def number(value):
    if value is None or isinstance(value,bool):return None
    if isinstance(value,(int,float,Decimal)):
        try:n=Decimal(str(value))
        except InvalidOperation:return None
        return n if n.is_finite() and abs(n)<=Decimal('1e16') else None
    text=clean(value).replace(' ','')
    text=re.sub(r'^(?:CNY|RMB|人民币|￥|¥)','',text,flags=re.I);text=re.sub(r'元$','',text)
    if text.startswith('(') and text.endswith(')'):text='-'+text[1:-1]
    if not re.fullmatch(r'[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)',text):return None
    try:n=Decimal(text.replace(',',''))
    except InvalidOperation:return None
    return n if n.is_finite() and abs(n)<=Decimal('1e16') else None
def match(value,wanted,tolerance='0.005'):
    n=number(value);w=number(wanted)
    return n is not None and w is not None and abs(n-w)<=Decimal(tolerance)
def json_object(path):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise CandidateError('duplicate JSON key')
            result[k]=v
        return result
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>4_000_000:raise CandidateError('missing/oversized JSON')
    try:result=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:None if False else (_ for _ in ()).throw(CandidateError('non-finite JSON')))
    except (UnicodeError,json.JSONDecodeError,OSError) as exc:raise CandidateError('unreadable JSON') from exc
    if not isinstance(result,dict):raise CandidateError('ledger must be an object')
    return result

def column(text):
    result=0
    for c in text:result=result*26+ord(c)-64
    return result
def coordinate(address):
    m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
    return (int(m[2]),column(m[1])) if m else None
def workbook(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise CandidateError('missing native workbook')
    try:
        OFFICE['_clean_package'](path.read_bytes())
        projection=NATIVE['extract_native_text'](path,max_chars=3_000_000)
    except (OFFICE['OfficeRuntimeError'],NATIVE['NativeTextError']) as exc:raise CandidateError(str(exc)) from exc
    if projection['truncated']:raise CandidateError('workbook observation limit')
    cells={};sheets={};rows=defaultdict(lambda:defaultdict(dict))
    for record in map(json.loads,projection['text'].splitlines()):
        if record['locator'].startswith('sheet:'):
            sheets[record['locator'][6:]]=record.get('state','visible');continue
        if '!' not in record['locator']:continue
        sheet,address=record['locator'].rsplit('!',1);coord=coordinate(address)
        if coord is None or record['locator'] in cells:raise CandidateError('duplicate or invalid workbook cell')
        value=record.get('value')
        if record.get('type')=='n' and value is not None:
            try:value=Decimal(value)
            except InvalidOperation:value=None
            if value is not None and not value.is_finite():value=None
        record={**record,'value':value,'sheet':sheet,'cell':address,'row':coord[0],'col':coord[1]}
        cells[record['locator']]=record;rows[sheet][coord[0]][coord[1]]=record
    return {'cells':cells,'rows':rows,'sheets':sheets,'sha256':sha(path)}

def logical_table(book,headers,id_field,pattern):
    required={key(v):v for v in headers};found=[]
    for sheet,rows in book['rows'].items():
        if book['sheets'].get(sheet)!='visible':continue
        for row,cells in sorted(rows.items()):
            mapping={};duplicate=False
            for col,cell in cells.items():
                k=key(cell['value'])
                if k in required:
                    if required[k] in mapping:duplicate=True
                    mapping[required[k]]=col
            if not duplicate and set(mapping)==set(headers):found.append((sheet,row,mapping))
    output={};duplicates=[];origins=[]
    for sheet,start,mapping in found:
        end=min((r for s,r,m in found if s==sheet and r>start),default=10**8)
        for row,cells in sorted(book['rows'][sheet].items()):
            if not start<row<end:continue
            id_cell=cells.get(mapping[id_field]);identity=clean(id_cell['value']).upper() if id_cell else ''
            if not re.fullmatch(pattern,identity):continue
            if id_field=='option_id' and not any(cells.get(mapping[f],{}).get('value') for f in ['p1_cl','p1_fan','p2_cl','p2_fan']):continue
            record={'id':identity,'sheet':sheet,'row':row,'cells':{field:cells.get(col) for field,col in mapping.items()},
                'values':{field:cells.get(col,{}).get('value') for field,col in mapping.items()}}
            if identity in output:duplicates.append(identity);output[identity]=None
            else:output[identity]=record
        origins.append({'sheet':sheet,'header_row':start,'columns':mapping})
    return {'rows':output,'duplicates':duplicates,'origins':origins}

def numeric_cell(cell):return cell is not None and cell.get('type')=='n' and isinstance(cell.get('value'),Decimal)
def driver(book,cell):
    if cell is None:return None
    locator=cell['locator'];seen=set()
    for _ in range(12):
        if locator in seen:return None
        seen.add(locator);current=book['cells'].get(locator)
        if current is None:return None
        if 'formula' not in current:return current if numeric_cell(current) else None
        expression=clean(current['formula']).lstrip('=+').strip()
        m=re.fullmatch(r"(?:(?:'((?:[^']|'')+)'|([^!]+))!)?(\$?[A-Za-z]+\$?[1-9][0-9]*)",expression)
        if not m:return None
        sheet=(m[1].replace("''", "'") if m[1] else m[2]) or current['sheet']
        locator=sheet+'!'+m[3].replace('$','').upper()
    return None

def word(path):
    try:return WORD['read_document'](path)
    except WORD['CandidateWordError'] as exc:raise CandidateError(str(exc)) from exc
def word_tables(model):
    result=[]
    for table in model['tables']:
        if table['parent_cell'] is not None:continue
        previous=[p['text'] for p in model['paragraphs'] if p['parent_cell'] is None and p['position']<table['position'] and p['text'].strip()]
        label=previous[-1] if previous and re.search(r'替代|备选|alternative',previous[-1],re.I) else ' '.join(previous[-2:])
        result.append({'locator':table['locator'],'label':label,'attrs':{},
            'rows':[[cell['text'] for cell in row['cells']] for row in table['rows']]})
    return result
def word_blocks(model):
    blocks=[(p['position'],p['text']) for p in model['paragraphs'] if p['parent_cell'] is None]
    for table in model['tables']:
        if table['parent_cell'] is None:blocks.extend((r['position'],' '.join(c['text'] for c in r['cells'])) for r in table['rows'])
    return [text for _,text in sorted(blocks)]

class HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.root={'tag':'root','attrs':{},'children':[]};self.stack=[self.root];self.active=False;self.external=False
    def handle_starttag(self,tag,attrs):
        attrs={k:v or '' for k,v in attrs};node={'tag':tag,'attrs':attrs,'children':[]};self.stack[-1]['children'].append(node)
        if tag in {'script','iframe','object','embed'} or any(k.startswith('on') for k in attrs):self.active=True
        if any(k in {'src','href','action'} and v and not v.startswith(('#','data:')) for k,v in attrs.items()):self.external=True
        if tag not in {'meta','link','br','img','hr','input','source','wbr'}:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i]['tag']==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1]['children'].append(data)
def descendants(node,tag):
    for child in node['children']:
        if isinstance(child,dict):
            if child['tag']==tag:yield child
            yield from descendants(child,tag)
def text(node,hidden=()):
    if isinstance(node,str):return node
    attrs=node['attrs'];style=attrs.get('style','')
    if (node['tag'] in {'style','script','template','head','meta','title'} or 'hidden' in attrs or attrs.get('aria-hidden')=='true'
        or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:[;\s]|$)|font-size\s*:\s*0',style,re.I)
        or any((s.startswith('.') and s[1:] in attrs.get('class','').split()) or (s.startswith('#') and s[1:]==attrs.get('id')) or s==node['tag'] for s in hidden)):
        return ''
    if node['tag']=='br':return '\n'
    value=''.join(text(c,hidden) for c in node['children'])
    return value+'\n' if node['tag'] in {'p','li','tr','div','h1','h2','h3','section'} else value
def html(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>5_242_880:raise CandidateError('missing/oversized HTML')
    try:raw=path.read_text(encoding='utf-8-sig');parser=HTML();parser.feed(raw);parser.close()
    except (UnicodeError,OSError) as exc:raise CandidateError('unreadable HTML') from exc
    styles=' '.join(''.join(c for c in n['children'] if isinstance(c,str)) for n in descendants(parser.root,'style'))
    hidden=[]
    for selectors,body in re.findall(r'([^{}]+)\{([^{}]*)\}',styles):
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:[;\s]|$)',body,re.I):
            hidden.extend(s.strip() for s in selectors.split(',') if re.fullmatch(r'[.#]?[\w-]+',s.strip()))
    if re.search(r'@import|url\s*\(\s*["\']?(?!data:|#)',styles,re.I):parser.external=True
    def visible_tables(node):
        if isinstance(node,str) or not text(node,hidden).strip():return
        if node['tag']=='table':yield node;return
        for child in node['children']:yield from visible_tables(child)
    tables=[]
    for i,node in enumerate(visible_tables(parser.root),1):
        if not text(node,hidden).strip():continue
        try:expanded=GRID['table_grid'](node,lambda n:text(n,hidden))
        except ValueError as exc:raise CandidateError(str(exc)) from exc
        tables.append({'locator':'table:'+str(i),'attrs':node['attrs'],**expanded,'label':node['attrs'].get('data-plan','')})
    blocks=[]
    for table in tables:blocks.extend(' '.join(row) for row in table['rows'])
    def non_table_blocks(node):
        if isinstance(node,str) or node['tag']=='table' or not text(node,hidden).strip():return
        if node['tag'] in {'p','li'}:blocks.append(text(node,hidden));return
        for child in node['children']:non_table_blocks(child)
    non_table_blocks(parser.root)
    return {'tables':tables,'blocks':blocks,'text':text(parser.root,hidden),'self_contained':not(parser.active or parser.external),'sha256':sha(path)}

def budget_rows(tables,aliases):
    wanted={key(v):name for name,values in aliases.items() for v in values};candidates=[]
    for table in tables:
        for i,row in enumerate(table['rows']):
            mapping={};plan_column=None
            for col,value in enumerate(row):
                if key(value) in wanted:mapping[wanted[key(value)]]=col
                if key(value) in {'方案','方案类型','组合','plan','plantype','scenario','option'}:plan_column=col
            if set(mapping)!=set(aliases):continue
            data={};physical={};active_plan=''
            for r,values in enumerate(table['rows'][i+1:],i+2):
                if plan_column is not None:
                    if plan_column<len(values) and clean(values[plan_column]):active_plan=clean(values[plan_column])
                    if re.search(r'替代|备选|alternative|不推荐|非推荐|non.?recommended',active_plan,re.I):continue
                p=clean(values[mapping['phase']]).upper() if len(values)>mapping['phase'] else ''
                if re.fullmatch(r'P[0-9]+',p):
                    if p in data:data[p]=None
                    else:data[p]={k:values[c] if c<len(values) else None for k,c in mapping.items()}
                    physical[p]=r
            if data:candidates.append({'table':table,'rows':data,'physical_rows':physical,
                'recommended':bool(re.search(r'推荐|recommend',table.get('label',''),re.I) or table['attrs'].get('data-plan')=='recommended'),
                'alternative':bool(re.search(r'替代|alternative',table.get('label',''),re.I) or table['attrs'].get('data-plan')=='alternative')})
    selected=[c for c in candidates if c['recommended'] and not c['alternative']]
    if not selected:selected=[c for c in candidates if not c['alternative']]
    # Multiple per-phase native tables are allowed; duplicate phase claims are ambiguous.
    result={}
    for c in selected:
        for p,row in c['rows'].items():
            if p in result:result[p]=None
            else:result[p]={'values':row,'table':c['table'],'physical_row':c['physical_rows'][p]}
    return result

def schedules(blocks):
    found={};duplicates=[];active=None
    for block in blocks:
        ids=re.findall(r'P[12]-(?:CL|FAN)',clean(block),re.I)
        dates=[]
        for y,m,d in re.findall(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?',clean(block)):
            dates.append(f'{int(y):04}-{int(m):02}-{int(d):02}')
        if len(set(map(str.upper,ids)))==1:
            active=ids[0].upper()
            if dates:
                if active in found:duplicates.append(active)
                found[active]=dates;active=None
        elif not ids and active and dates:
            found.setdefault(active,[]).extend(dates)
        elif clean(block) and not dates:active=None
    for identity in duplicates:found[identity]=None
    return found
