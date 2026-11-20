"""Native candidate projections and declared coordinate equivalence, not visual interpretation."""
from pathlib import Path
from collections import defaultdict
import json,hashlib,math,re,runpy,unicodedata
HERE=Path(__file__).resolve().parent
OFFICE=runpy.run_path(str(HERE/'office_runtime.py'))
NATIVE=runpy.run_path(str(HERE/'native_text.py'))
WORD=runpy.run_path(str(HERE/'word_model.py'))
class CandidateError(ValueError):pass
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_EMBEDDED_SOURCE_INVALID','OFFICE_EMBEDDED_PART_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(v):
    v=list(v);return sum(v)/len(v) if v else 0.
def clean(v):return unicodedata.normalize('NFKC','' if v is None else str(v)).strip()
def canon(v):return re.sub(r'[\s。.,，；;：:、“”"‘’\[\]（）()]','',clean(v)).casefold()
def blank(v):return canon(v) in {'','unknown','null','none','未决','未知','不适用','n/a','无'}
def same_text(v,w):return canon(v)==canon(w)
def status(v,contract):return next((s for s,aliases in contract['status_aliases'].items() if canon(v) in {canon(a) for a in aliases}),None)
def load_json(p):
    p=Path(p)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>5_242_880:raise CandidateError('missing/unsafe/oversized JSON')
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise CandidateError('duplicate JSON key')
            d[k]=v
        return d
    try:return json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(CandidateError('nonfinite JSON')))
    except (OSError,UnicodeError,json.JSONDecodeError) as e:raise CandidateError('unreadable JSON') from e
def workbook(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>5_242_880:raise CandidateError('missing/unsafe/oversized XLSX')
    try:
        OFFICE['_clean_package'](path.read_bytes());p=NATIVE['extract_native_text'](path,max_chars=3_000_000)
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    except NATIVE['NativeTextError'] as e:raise CandidateError(str(e)) from e
    if p['truncated']:raise CandidateError('XLSX projection limit')
    rows=defaultdict(lambda:defaultdict(dict));visible={}
    for cell in map(json.loads,p['text'].splitlines()):
        loc=cell['locator']
        if loc.startswith('sheet:'):visible[loc[6:]]=cell.get('state','visible');continue
        if '!' not in loc:continue
        sheet,address=loc.rsplit('!',1);m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
        if not m:raise CandidateError('invalid cell address')
        col=0
        for c in m[1]:col=col*26+ord(c)-64
        if col in rows[sheet][int(m[2])]:raise CandidateError('duplicate native cell')
        rows[sheet][int(m[2])][col]={**cell,'value':cell.get('value')}
    return {'rows':rows,'visible':visible}
def logical_rows(book,aliases,required,*,multiple=False):
    names={canon(a):k for k,v in aliases.items() for a in v};headers=[];out={};duplicates=[]
    for sheet,rows in book['rows'].items():
        if book['visible'].get(sheet)!='visible':continue
        for row,cells in sorted(rows.items()):
            mapping={};dups=set()
            for col,cell in cells.items():
                k=names.get(canon(cell['value']))
                if k:
                    if k in mapping:dups.add(k)
                    mapping[k]=col
            if set(required)<=set(mapping) and not dups:headers.append((sheet,row,mapping))
    for sheet,start,mapping in headers:
        end=min((row for s,row,_ in headers if s==sheet and row>start),default=10**9)
        for row,cells in sorted(book['rows'][sheet].items()):
            if not start<row<end:continue
            identity=clean(cells.get(mapping['revision_id'],{}).get('value')).upper()
            if not re.fullmatch(r'R\d{2}',identity):continue
            entry={k:cells.get(col,{}).get('value') for k,col in mapping.items()}
            entry['_origin']={'sheet':sheet,'row':row};entry['_formula_fields']=[k for k,col in mapping.items() if cells.get(col,{}).get('formula')]
            if multiple:out.setdefault(identity,[]).append(entry)
            elif identity in out:out[identity]=None;duplicates.append(identity)
            else:out[identity]=entry
    return out,{'headers':[{'sheet':s,'row':r,'columns':m} for s,r,m in headers],'duplicate_ids':duplicates}
def parse_value(v):
    if isinstance(v,(dict,list)):return v
    if not isinstance(v,str):return None
    try:return json.loads(v)
    except json.JSONDecodeError:return None
def matrix(path,contract):
    book=workbook(path);rows,meta=logical_rows(book,contract['matrix_fields'],contract['matrix_required'])
    # A separate evidence table is accepted when JSON-in-cell is not used.
    evidence_rows,_=logical_rows(book,contract['evidence_fields'],['revision_id','file','bbox','observation'],multiple=True)
    for identity,row in rows.items():
        if row is None:continue
        value=parse_value(row.get('evidence'))
        if value is None:
            value=[{'file':r['file'],'bbox':parse_value(r['bbox']),'observation':r['observation'],
                    'coordinate_space':r.get('coordinate_space','pixel_xyxy')} for r in evidence_rows.get(identity,[])]
        row['evidence']=value
    return rows,meta
def word(path):
    try:return WORD['read_document'](path)
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def document_sections(model):
    """Associate native paragraphs/table rows with reader-visible execution/appendix headings."""
    result={'execution':[],'conditional':[],'nonexecution':[],'unclassified':[]};current='unclassified';previous=None
    top=[p for p in model['paragraphs'] if p['parent_cell'] is None]
    tables=[t for t in model['tables'] if t['parent_cell'] is None]
    for node in sorted(top+tables,key=lambda n:n['position']):
        if node['kind']=='paragraph':
            text=node['text'];t=canon(text)
            heading=None
            if (not re.search(r'[RC]\d{2}',text,re.I) and len(t)<40
                and not any(c in text for c in ['。','；',';']) and not t.startswith('前置条件')):
                if any(k in t for k in ['条件未满足','暂不执行','未满足条件','conditional']):heading='conditional'
                elif any(k in t for k in ['状态附表','待确认附表','非执行','未决附表','不执行附表','nonexecution']):heading='nonexecution'
                elif any(k in t for k in ['执行正文','可确认采用','已确认条款','executionclauses']):heading='execution'
            if heading:current=heading;previous=None;continue
            if re.search(r'[RC]\d{2}',text,re.I):
                previous={'text':text,'locator':node['locator']};result[current].append(previous)
            elif previous:previous['text']+=' '+text
        else:
            for row in node['rows']:
                # read_document exposes physical cell text; logical identity remains in the visible row.
                texts=[cell.get('text','') for cell in row['cells']]
                text=' '.join(texts)
                if re.search(r'[RC]\d{2}',text,re.I):result[current].append({'text':text,'locator':node['locator']+'/row:'+str(row['index'])})
    return result
def list_records(value):
    if isinstance(value,list):rows=value
    elif isinstance(value,dict):rows=next((value[k] for k in ['items','records','uncertain','unresolved'] if isinstance(value.get(k),list)),[])
    else:return {},False
    out={};ok=True
    for row in rows:
        if not isinstance(row,dict):ok=False;continue
        identity=clean(row.get('revision_id')).upper()
        if not re.fullmatch(r'R\d{2}',identity) or identity in out:ok=False;out[identity]=None
        else:out[identity]=row
    return out,ok
def field_names(v,contract):
    if isinstance(v,str):v=parse_value(v) or re.split(r'[,，;；\s]+',v)
    if not isinstance(v,list):return set()
    aliases={canon(a):k for k,arr in contract['unknown_field_aliases'].items() for a in arr}
    return {aliases.get(canon(item),'unrecognized:'+clean(item)) for item in v}
def rule_names(v):return set(re.findall(r'\bA[0-7]\b',clean(v))) if not isinstance(v,list) else {clean(x).upper() for x in v}
def business_text(v,w,anchors):
    if same_text(v,w):return True
    text=canon(v);wanted=canon(w)
    # Bounded subject/value checks allow ordinary paraphrases. A Judge must still assess full meaning.
    if any(t in text for t in ['不必','无需','不得','不用','不再','不予','取消','并非']):return False
    numbers=lambda t:sorted(re.findall(r'\d+(?:\.\d+)?',t))
    if numbers(text)!=numbers(wanted):return False
    return bool(text) and all(any(canon(a) in text for a in group) for group in anchors)
def image_name(v):
    v=clean(v)
    if v.startswith('/tmp_workspace/'):v=v[len('/tmp_workspace/'):]
    return v if re.fullmatch(r'signed_pages/scan_0[1-5]\.png',v) else None
def region(value):
    if not isinstance(value,dict):return None
    box=value.get('bbox');space=clean(value.get('coordinate_space','pixel_xyxy')).casefold()
    if not isinstance(box,list) or len(box)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):return None
    x,y,a,b=box
    if space in {'normalized_xyxy','normalized','relative_xyxy'}:x,a=x*1500,a*1500;y,b=y*2100,b*2100
    elif space in {'pixel_xywh','xywh'}:a,b=x+a,y+b
    elif space not in {'pixel_xyxy','xyxy','pixels','original_image_pixels'}:return None
    return [x,y,a,b] if 0<=x<a<=1500 and 0<=y<b<=2100 else None
def area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])
def intersection(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
def evidence_score(value,visual,contract):
    if isinstance(value,str):value=parse_value(value)
    if isinstance(value,dict):value=[value]
    if not isinstance(value,list):return {'score':0.,'features':{},'reason':'no typed evidence'}
    boxes=[]
    for record in value:
        if not isinstance(record,dict) or image_name(record.get('file'))!=visual['file'] or not clean(record.get('observation')):continue
        box=region(record)
        if box and area(box)<=contract['maximum_region_page_ratio']*1500*2100:boxes.append(box)
    features={f['key']:any(intersection(box,f['bbox'])/area(f['bbox'])>=contract['minimum_feature_coverage'] for box in boxes) for f in visual['features']}
    return {'score':mean(features.values()),'features':features,'accepted_boxes':boxes,
            'limit':'Coordinate coverage and nonempty observation only; actual image meaning must be judged independently.'}
