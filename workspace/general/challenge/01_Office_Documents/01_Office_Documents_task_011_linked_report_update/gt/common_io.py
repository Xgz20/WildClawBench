"""Bounded native observations, scalar equivalence and explicit candidate errors."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from collections import defaultdict
import hashlib,json,re,runpy,unicodedata
HERE=Path(__file__).resolve().parent
OFFICE=runpy.run_path(str(HERE/'office_runtime.py'))
NATIVE=runpy.run_path(str(HERE/'native_text.py'))
WORD=runpy.run_path(str(HERE/'word_model.py'))
class CandidateError(ValueError):pass
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_EMBEDDED_SOURCE_INVALID','OFFICE_EMBEDDED_PART_INVALID',
 'OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}
def clean(v):return unicodedata.normalize('NFKC','' if v is None else str(v)).strip().replace('−','-')
def canon(v):return re.sub(r'\s+','',clean(v)).replace(',','').replace('；',';').replace('，',',').replace('。','.').casefold()
def key(v):return re.sub(r'[\s_()（）]','',clean(v)).casefold()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(v):v=list(v);return sum(v)/len(v) if v else 0.
def number(v):
    if v is None or isinstance(v,bool):return None
    if isinstance(v,(int,float,Decimal)):
        try:n=Decimal(str(v))
        except InvalidOperation:return None
        return n if n.is_finite() and abs(n)<Decimal('1e17') else None
    text=clean(v).replace(' ','')
    if text.startswith('(') and text.endswith(')'):text='-'+text[1:-1]
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+',text):return None
    try:n=Decimal(text.replace(',',''))
    except InvalidOperation:return None
    return n if n.is_finite() and abs(n)<Decimal('1e17') else None
def match(v,w,tolerance='.005'):
    a,b=number(v),number(w);return a is not None and b is not None and abs(a-b)<=Decimal(tolerance)
def scalar(v,unit,target):
    units={'cny':Decimal(1),'rmb':Decimal(1),'元':Decimal(1),'万元':Decimal(10000),'ratio':Decimal(1),'比例':Decimal(1),'%':Decimal('.01'),'百分比':Decimal('.01')}
    unit=clean(unit).casefold();target=clean(target).casefold();n=number(v)
    money={'cny','rmb','元','万元'};ratio={'ratio','比例','%','百分比'}
    if n is None or not ((unit in money and target in money) or (unit in ratio and target in ratio)):return None
    return n*units[unit]/units[target]
def json_object(path):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise CandidateError('duplicate JSON key')
            d[k]=v
        return d
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>5_242_880:raise CandidateError('missing/oversized JSON')
    try:d=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(CandidateError('non-finite JSON')))
    except (OSError,UnicodeError,json.JSONDecodeError) as e:raise CandidateError('unreadable JSON') from e
    if not isinstance(d,dict):raise CandidateError('expected JSON object')
    return d
def coordinate(address):
    m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
    if not m:return None
    col=0
    for c in m[1]:col=col*26+ord(c)-64
    return int(m[2]),col
def workbook(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise CandidateError('missing native workbook')
    try:
        OFFICE['_clean_package'](path.read_bytes());projection=NATIVE['extract_native_text'](path,max_chars=3_000_000)
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    except NATIVE['NativeTextError'] as e:raise CandidateError(str(e)) from e
    if projection['truncated']:raise CandidateError('workbook observation limit')
    cells={};rows=defaultdict(lambda:defaultdict(dict));sheets={}
    for r in map(json.loads,projection['text'].splitlines()):
        loc=r['locator']
        if loc.startswith('sheet:'):sheets[loc[6:]]=r.get('state','visible');continue
        if '!' not in loc:continue
        sheet,address=loc.rsplit('!',1);point=coordinate(address)
        if point is None or loc in cells:raise CandidateError('invalid/duplicate workbook cell')
        v=r.get('value')
        if r.get('type')=='n' and v is not None:
            try:v=number(Decimal(v))
            except InvalidOperation:v=None
        r={**r,'value':v,'sheet':sheet,'cell':address,'row':point[0],'col':point[1]};cells[loc]=r;rows[sheet][point[0]][point[1]]=r
    return {'cells':cells,'rows':rows,'sheets':sheets,'sha256':sha(path)}
def logical_rows(book,aliases,id_field,pattern):
    wanted={key(v):field for field,values in aliases.items() for v in values};headers=[]
    for sheet,rows in book['rows'].items():
        if book['sheets'].get(sheet)!='visible':continue
        for row,cells in sorted(rows.items()):
            found={};duplicates=set()
            for col,c in cells.items():
                field=wanted.get(key(c['value']))
                if field:
                    if field in found:duplicates.add(field)
                    found[field]=col
            if set(found)==set(aliases) and not duplicates:headers.append((sheet,row,found))
    records={};extra=[]
    for sheet,start,mapping in headers:
        end=min((r for s,r,_ in headers if s==sheet and r>start),default=10**9)
        for row,cells in sorted(book['rows'][sheet].items()):
            if not start<row<end:continue
            cell=cells.get(mapping[id_field],{});identity=clean(cell.get('value'))
            if not re.fullmatch(pattern,identity):continue
            data={field:cells.get(col) for field,col in mapping.items()}
            if identity in records:records[identity]=None;extra.append(identity)
            else:records[identity]={'cells':data,'sheet':sheet,'row':row}
    return {'rows':records,'duplicates':extra,'origins':[{'sheet':s,'row':r,'columns':m} for s,r,m in headers]}
def word(path):
    try:return WORD['read_document'](path)
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def pptx(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():raise CandidateError('missing native presentation')
    try:
        OFFICE['_inspect_render_package'](path.read_bytes());p=NATIVE['extract_native_text'](path,max_chars=3_000_000)
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    except NATIVE['NativeTextError'] as e:raise CandidateError(str(e)) from e
    if p['truncated']:raise CandidateError('presentation observation limit')
    return list(map(json.loads,p['text'].splitlines()))
def output_path(v):
    v=clean(v)
    if v.startswith('/tmp_workspace/'):v=v[len('/tmp_workspace/'):]
    if v.startswith('/') or '\\' in v or any(p in {'.','..',''} for p in v.split('/')):return None
    return v
