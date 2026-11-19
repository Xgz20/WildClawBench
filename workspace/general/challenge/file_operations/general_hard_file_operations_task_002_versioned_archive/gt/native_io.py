import csv,io,json,re,unicodedata
from datetime import datetime,timezone
ALIASES={'来源编号':'source_id','原路径':'source_path','归档路径':'archive_path','内容哈希':'sha256','业务分类':'business_area','文档编号':'document_id','版本':'version','审批状态':'state','发布时间':'issued_at','版本选择':'selection','重复来源代表':'duplicate_of','识别格式':'detected_format','原因代码':'reason_code','异常类型':'kind','来源编号集合':'source_ids','说明':'detail'}
COLUMNS=['source_id','source_path','archive_path','sha256','business_area','document_id','version','state','issued_at','selection','duplicate_of','detected_format','reason_code']
def normalize(s):return unicodedata.normalize('NFC',s) if isinstance(s,str) else s
def unknown(s):return isinstance(s,str) and s.strip().lower() in ('','unknown','未知')
def path_value(s,kind):
    if not isinstance(s,str):return None
    s=normalize(s)
    prefix='/tmp_workspace/results/' if kind=='archive' else '/tmp_workspace/'
    if s.startswith(prefix):s=s[len(prefix):]
    if s.startswith('./'):s=s[2:]
    if s.startswith('/') or '\\' in s or not s or any(x in ('','..','.') for x in s.split('/')):return None
    if not s.startswith(('archive/' if kind=='archive' else 'incoming/')):return None
    return s
def version(s):
    if not isinstance(s,str) or not re.fullmatch(r'v?\d+\.\d+(?:\.\d+)?',s,re.I):return None
    v=[int(x) for x in s.lstrip('vV').split('.')];return tuple(v+[0]*(3-len(v)))
def instant(s):
    if not isinstance(s,str):return None
    try:
        d=datetime.fromisoformat(s.replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo is not None else None
    except (ValueError,OverflowError):return None
def manifest(p):
    text=p.read_text(encoding='utf-8-sig');reader=csv.DictReader(io.StringIO(text,newline=''))
    if not reader.fieldnames:raise ValueError('CSV header missing')
    keys=[ALIASES.get(k.strip(),k.strip()) for k in reader.fieldnames]
    if len(set(keys))!=len(keys) or not set(COLUMNS)<=set(keys):raise ValueError('CSV required columns missing/duplicate')
    out=[]
    for raw in reader:
        if None in raw:raise ValueError('ragged CSV')
        row={ALIASES.get(k.strip(),k.strip()):(v.strip() if isinstance(v,str) else '') for k,v in raw.items()}
        if not all(isinstance(v,str) for v in row.values()):raise ValueError('invalid CSV cell')
        out.append(row)
    return out
def ids(value):
    if isinstance(value,list):return {str(x).strip() for x in value if isinstance(x,str)}
    if isinstance(value,str):return {x for x in re.split(r'[\s,，、;；]+',value.strip()) if x}
    return set()
def exception_records(p):
    text=p.read_text(encoding='utf-8-sig')
    for m in re.finditer(r'```(?:json|JSON)\s*\n(.*?)\n```',text,re.S):
        try:v=json.loads(m.group(1))
        except ValueError:continue
        if isinstance(v,dict):v=v.get('exceptions')
        if isinstance(v,list):return [{ALIASES.get(k,k):val for k,val in r.items()} for r in v if isinstance(r,dict)]
    lines=[line for line in text.splitlines() if '|' in line];header=None;out=[]
    for line in lines:
        cells=[re.sub(r'[`*]','',x.strip()) for x in line.strip().strip('|').split('|')]
        keys=[ALIASES.get(x,x) for x in cells]
        if {'kind','source_ids','detail'}<=set(keys):header=keys;continue
        if header and len(cells)==len(header) and not all(re.fullmatch(r':?-+:?',x) for x in cells):out.append(dict(zip(header,cells)))
    return out
