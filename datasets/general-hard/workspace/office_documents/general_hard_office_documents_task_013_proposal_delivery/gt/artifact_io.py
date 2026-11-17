"""Native logical observations; author sheet names and coordinates are not grading contracts."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from collections import defaultdict
import csv,hashlib,io,json,posixpath,re,runpy,unicodedata,zipfile
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OFFICE=runpy.run_path(str(HERE/'office_runtime.py'));NATIVE=runpy.run_path(str(HERE/'native_text.py'));WORD=runpy.run_path(str(HERE/'word_model.py'))
class CandidateError(ValueError):pass
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_EMBEDDED_SOURCE_INVALID','OFFICE_EMBEDDED_PART_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(v):v=list(v);return sum(v)/len(v) if v else 0.
def clean(v):return unicodedata.normalize('NFKC','' if v is None else str(v)).strip().replace('−','-')
def canon(v):return re.sub(r'[\s。.,，;；:：、_()（）\[\]“”"‘’]','',clean(v)).casefold()
def number(v):
    if v is None or isinstance(v,bool):return None
    t=clean(v).replace(',','').replace(' ','')
    if t.startswith('(') and t.endswith(')'):t='-'+t[1:-1]
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',t):return None
    try:n=Decimal(t)
    except InvalidOperation:return None
    return n if n.is_finite() and abs(n)<Decimal('1e17') else None
def scalar_ok(v,w,tolerance='.005'):
    if w is None:return canon(v) in {'','unknown','null','none','未知','待确认','未核实'}
    if isinstance(w,bool):return v is w or canon(v) in ({'true','1','是','允许'} if w else {'false','0','否','不允许'})
    n=number(w)
    if n is not None:
        actual=number(v);return actual is not None and abs(actual-n)<=Decimal(tolerance)
    return canon(v)==canon(w)
def state(v,contract):return next((k for k,values in contract['status_aliases'].items() if canon(v) in {canon(x) for x in values}),None)
def candidate_path(path):
    p=Path(path)
    if not p.is_file() or any(x.is_symlink() for x in [p,*p.parents]) or p.stat().st_size>5_242_880:raise CandidateError('missing, unsafe or oversized output: '+p.name)
    return p
def text(path):
    try:return candidate_path(path).read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError) as e:raise CandidateError('unreadable text') from e
def workbook(path):
    p=candidate_path(path)
    try:
        OFFICE['_clean_package'](p.read_bytes());projection=NATIVE['extract_native_text'](p,max_chars=4_000_000)
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    except NATIVE['NativeTextError'] as e:raise CandidateError(str(e)) from e
    if projection['truncated']:raise CandidateError('native XLSX projection limit')
    rows=defaultdict(lambda:defaultdict(dict));sheets={}
    for c in map(json.loads,projection['text'].splitlines()):
        loc=c['locator']
        if loc.startswith('sheet:'):sheets[loc[6:]]=c.get('state','visible');continue
        if '!' not in loc:continue
        sheet,address=loc.rsplit('!',1);m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
        if not m:raise CandidateError('invalid native cell locator')
        col=0
        for char in m[1]:col=col*26+ord(char)-64
        if col in rows[sheet][int(m[2])]:raise CandidateError('duplicate native cell')
        rows[sheet][int(m[2])][col]={**c,'sheet':sheet,'cell':address,'row':int(m[2]),'col':col,'value':c.get('value')}
    # Native IDs may be vertically merged across three business rows; resolve their true anchor.
    X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(p) as z:
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'));targets={r.get('Id'):r.get('Target') for r in rels if r.get('TargetMode')!='External'}
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        for sheet in wb.findall(X+'sheets/'+X+'sheet'):
            name=sheet.get('name');target=targets.get(sheet.get(R+'id'),'')
            part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if name not in rows or part not in z.namelist():continue
            node=ET.fromstring(z.read(part))
            for merge in node.findall(X+'mergeCells/'+X+'mergeCell'):
                m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*):\1([1-9][0-9]*)',merge.get('ref',''))
                if not m or not 0<int(m[3])-int(m[2])<=1000:continue
                col=0
                for char in m[1]:col=col*26+ord(char)-64
                anchor=rows[name].get(int(m[2]),{}).get(col)
                if not anchor or clean(anchor['value']).upper() not in {'S1','S2','S3','A','B','C'}:continue
                for row in range(int(m[2])+1,int(m[3])+1):
                    existing=rows[name][row].get(col)
                    if existing is None or (existing.get('value') in {None,''} and not existing.get('formula')):rows[name][row][col]={**anchor,'merged_id_alias':True,'row':row}
    return {'rows':rows,'sheets':sheets}
def word(path):
    try:return WORD['read_document'](candidate_path(path))
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def grids(book):
    return [{'name':sheet,'rows':rows} for sheet,rows in book['rows'].items() if book['sheets'].get(sheet)=='visible']
def word_grids(model):
    def value(c):return model['nodes'][c['anchor']]['text'] if c.get('vertical_merge')=='continue' and c.get('anchor') in model['nodes'] else c['text']
    return [{'name':t['locator'],'rows':{row['index']:{c['column']:{'value':value(c),'locator':c['locator'],'type':'word'} for c in row['cells']} for row in t['rows']}} for t in model['tables'] if t['parent_cell'] is None]
def alias_map(contract):
    d={canon(a):k for k,values in contract['field_aliases'].items() for a in values}
    for k,values in contract['source_field_aliases'].items():
        for a in values:d[canon(a)]=k
    for k,values in {'field':['field','field_id','metric','metric_id','字段','指标','参数名'],
        'value':['value','数值','值'],'parameter_id':['parameter_id','参数编号','共用参数','参数ID']}.items():
        for a in values:d[canon(a)]=k
    return d
def headers(rows,aliases):
    out=[]
    for r,cells in sorted(rows.items()):
        found={};duplicates=set()
        for col,c in cells.items():
            k=aliases.get(canon(c['value']))
            if k:
                if k in found:duplicates.add(k)
                found[k]=col
        if len(found)>=2 and not duplicates:out.append((r,found))
    return out
def observe(all_grids,contract):
    """Merge complementary tables; retain every repeated value so one correct table cannot mask another."""
    aliases=alias_map(contract);metrics=defaultdict(lambda:defaultdict(list));sources=defaultdict(lambda:defaultdict(list));recommendations=defaultdict(lambda:defaultdict(list));metadata=[]
    source_fields=set(contract['source_field_aliases']);output_fields=set(contract['field_aliases'])-{'site_id','option_id','selected_option'}
    def rec(grid,cells,col):return cells.get(col,{'value':None,'type':'blank','locator':grid['name']+'/blank'})
    def add(target,identity,field,cell):target[identity][field].append(cell)
    for grid in all_grids:
        rows=grid['rows'];hs=headers(rows,aliases)
        for start,mapping in hs:
            end=min((r for r,_ in hs if r>start),default=10**9)
            for r,cells in sorted(rows.items()):
                if not start<r<end:continue
                values={k:rec(grid,cells,c)['value'] for k,c in mapping.items()}
                site=clean(values.get('site_id')).upper();option=clean(values.get('option_id')).upper();selected=clean(values.get('selected_option')).upper()
                pair=site+'-'+option if re.fullmatch(r'S[123]',site) and option in {'A','B','C'} else None
                long_field=aliases.get(canon(values.get('field')))
                if pair:
                    if long_field in output_fields and 'value' in mapping:add(metrics,pair,long_field,rec(grid,cells,mapping['value']))
                    for field,col in mapping.items():
                        if field in output_fields:add(metrics,pair,field,rec(grid,cells,col))
                if re.fullmatch(r'S[123]',site) and 'selected_option' in mapping:
                    for field,col in mapping.items():
                        if field in {'selected_option','status','gross_total','budget_margin'}:add(recommendations,site,field,rec(grid,cells,col))
                # Wide or long source tables, grouped by public site/option IDs.
                for kind,identity in [('site',site),('option',option)]:
                    if not ((kind=='site' and re.fullmatch(r'S[123]',identity)) or (kind=='option' and identity in {'A','B','C'})):continue
                    allowed=set(contract['source_fields_by_kind'][kind]);key=kind+':'+identity
                    if long_field in allowed and 'value' in mapping:add(sources,key,long_field,rec(grid,cells,mapping['value']))
                    for field,col in mapping.items():
                        if field in allowed:add(sources,key,field,rec(grid,cells,col))
                param=clean(values.get('parameter_id'))
                if param and 'value' in mapping:
                    field=contract['parameter_aliases'].get(canon(param),param)
                    if field in contract['source_input_ids']['parameter_ids']:add(sources,'parameter:'+field,'value',rec(grid,cells,mapping['value']))
            metadata.append({'grid':grid['name'],'header_row':start,'fields':sorted(mapping)})
        # Transposed source tables retain the input-native field_id / S1,S2,S3 format.
        for start,cells in sorted(rows.items()):
            mapping={canon(c['value']):col for col,c in cells.items()};field_col=next((col for name,col in mapping.items() if aliases.get(name)=='field'),None)
            if field_col is None:continue
            objects={clean(c['value']).upper():col for col,c in cells.items() if clean(c['value']).upper() in {'S1','S2','S3','A','B','C'}}
            if not objects:continue
            for r,data in sorted(rows.items()):
                if r<=start:continue
                field=aliases.get(canon(rec(grid,data,field_col)['value']))
                if field not in source_fields:continue
                for identity,col in objects.items():
                    kind='site' if identity.startswith('S') else 'option'
                    if field in contract['source_fields_by_kind'][kind]:add(sources,kind+':'+identity,field,rec(grid,data,col))
    return {'metrics':{k:dict(v) for k,v in metrics.items()},'sources':{k:dict(v) for k,v in sources.items()},'recommendations':{k:dict(v) for k,v in recommendations.items()},'table_metadata':metadata}
def prose_recommendations(paragraphs,contract):
    result={};current=None
    for p in paragraphs:
        value=p['text'];m=re.match(r'^\s*(S[123])\s*(?:推荐|选定|选择|建议(?:采用|选用)?)\s*(?:方案)?\s*([ABC])(?=\s|$|[^A-Za-z0-9])',value,re.I)
        if m:
            current=m[1].upper();entry={'text':value,'heading':value,'selected_option':m[2].upper(),'locator':p['locator']}
            if current in result:result[current]=None;current=None
            else:result[current]=entry
        elif current and len(clean(value))<40 and any(k in value for k in ['逐项需求','例外和后续']):current=None
        elif current:result[current]['text']+=' '+value
    out={}
    for identity,row in result.items():
        if not row:continue
        t=row['heading'].split('。',1)[0].split('；',1)[0].split('，',1)[0]
        phase='conditional' if any(k in t for k in ['附条件','有条件','conditional']) else 'infeasible' if any(k in t for k in ['不可行','infeasible']) else 'feasible' if any(k in t for k in ['可行','feasible']) else None
        out[identity]={key:[{'value':v,'type':'prose','locator':row['locator']}] for key,v in [('selected_option',row['selected_option']),('status',phase)]}
        for field in ['gross_total','budget_margin']:
            names='|'.join(re.escape(a) for a in sorted(contract['field_aliases'][field],key=len,reverse=True))
            pattern=r'(?:'+names+r')\s*(?:[:：=]|为|是)?\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)'
            found=re.findall(pattern,row['text'],re.I)
            if found:out[identity][field]=[{'value':v,'type':'prose','locator':row['locator']} for v in found]
    return out
def email(path,contract):
    body=text(path);grids_=[];lines=body.splitlines();i=0
    while i<len(lines):
        if lines[i].lstrip().startswith('|'):
            rows={};count=0
            while i<len(lines) and lines[i].lstrip().startswith('|'):
                values=[v.strip() for v in lines[i].strip().strip('|').split('|')];i+=1
                if values and all(re.fullmatch(r':?-+:?',v or ' ') for v in values):continue
                count+=1;rows[count]={c+1:{'value':v,'type':'markdown','locator':f'line:{i}/cell:{c+1}'} for c,v in enumerate(values)}
            if rows:grids_.append({'name':'email-table:'+str(len(grids_)+1),'rows':rows})
        else:i+=1
    observed=observe(grids_,contract)['recommendations']
    prose=prose_recommendations([{'text':v,'locator':'line:'+str(i)} for i,v in enumerate(lines,1)],contract)
    for identity,data in prose.items():
        dest=observed.setdefault(identity,{})
        for key,entries in data.items():dest.setdefault(key,[]).extend(entries)
    return body,observed
def exceptions(path,contract):
    raw=text(path)
    try:
        reader=csv.DictReader(io.StringIO(raw));names=reader.fieldnames
        if not names or len({canon(k) for k in names})!=len(names):raise CandidateError('CSV headers missing or duplicate')
        aliases={canon(a):k for k,arr in contract['exception_aliases'].items() for a in arr};mapping={name:aliases.get(canon(name),name) for name in names}
        if not set(contract['exceptions_required'])<=set(mapping.values()):raise CandidateError('exception columns missing')
        records=[]
        for row in reader:
            if None in row:raise CandidateError('malformed CSV row')
            records.append({mapping[k]:v for k,v in row.items()})
    except csv.Error as e:raise CandidateError('malformed CSV') from e
    out={};duplicates=[]
    for row in records:
        key=(clean(row.get('site_id')).upper(),clean(row.get('option_id')).upper(),clean(row.get('rule_id')).upper())
        if key in out:duplicates.append(key);out[key]=None
        else:out[key]=row
    return out,{'rows':len(records),'duplicates':duplicates,'keys':[list(k) for k in out]}
def source_anchor(file,locator,expected,index):
    file=clean(file).removeprefix('/tmp_workspace/');locator=clean(locator);anchor=file+'#'+locator
    if anchor in expected:return True
    normalized=canon(locator)
    for key in expected:
        record=index[key]
        if file!=record['file']:continue
        if normalized==canon(record.get('physical_locator')):return True
        # A visible site column or the explicit site+field is a valid input-native locator.
        if normalized==canon(record.get('site_id')):return True
        if normalized==canon(record.get('site_id','')+':'+record.get('field','')):return True
    return False
