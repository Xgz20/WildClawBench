"""Bounded native observations keyed by public business fields, never author coordinates."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import hashlib,json,posixpath,re,runpy,unicodedata,zipfile
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OFFICE=runpy.run_path(str(HERE/'office_runtime.py'));NATIVE=runpy.run_path(str(HERE/'native_text.py'));WORD=runpy.run_path(str(HERE/'word_model.py'))
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED','OFFICE_EMBEDDED_SOURCE_INVALID','OFFICE_EMBEDDED_PART_INVALID'}
class CandidateError(ValueError):pass
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def clean(v):return unicodedata.normalize('NFKC','' if v is None else str(v)).strip().replace('−','-')
def canon(v):return re.sub(r'[\s。.,，;；:：、_()（）\[\]“”"‘’/％%\-]','',clean(v)).casefold()
def candidate_path(path):
    p=Path(path)
    if not p.is_file() or any(x.is_symlink() for x in [p,*p.parents]) or p.stat().st_size>5_242_880:raise CandidateError('missing, unsafe or oversized output: '+p.name)
    return p
def json_file(path):
    try:return json.loads(candidate_path(path).read_text(encoding='utf-8-sig'))
    except (OSError,UnicodeError,json.JSONDecodeError,RecursionError) as e:raise CandidateError('invalid JSON') from e
def projection(path):
    try:result=NATIVE['extract_native_text'](candidate_path(path),max_chars=4_000_000)
    except NATIVE['NativeTextError'] as e:raise CandidateError(str(e)) from e
    if result['truncated']:raise CandidateError('native projection truncated')
    return list(map(json.loads,result['text'].splitlines()))
def workbook(path,contract):
    p=candidate_path(path)
    try:OFFICE['_clean_package'](p.read_bytes())
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    records=projection(p);rows=defaultdict(lambda:defaultdict(dict));states={}
    for c in records:
        loc=c['locator']
        if loc.startswith('sheet:'):states[loc[6:]]=c.get('state','visible');continue
        m=re.fullmatch(r'(.+)!([A-Z]+)([1-9][0-9]*)',loc)
        if not m:continue
        col=0
        for char in m[2]:col=col*26+ord(char)-64
        rows[m[1]][int(m[3])][col]={**c,'stored_value':c.get('value'),'value':c.get('interpreted_date',c.get('value')),'sheet':m[1],'cell':m[2]+m[3],'row':int(m[3]),'col':col}
    X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(p) as z:
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if r.get('TargetMode')!='External'}
        for s in ET.fromstring(z.read('xl/workbook.xml')).findall(X+'sheets/'+X+'sheet'):
            name=s.get('name');target=rels.get(s.get(R+'id'),'');part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if name not in rows:continue
            for merge in ET.fromstring(z.read(part)).findall(X+'mergeCells/'+X+'mergeCell'):
                m=re.fullmatch(r'([A-Z]+)(\d+):\1(\d+)',merge.get('ref',''))
                if not m or not 0<int(m[3])-int(m[2])<1000:continue
                col=0
                for char in m[1]:col=col*26+ord(char)-64
                anchor=rows[name].get(int(m[2]),{}).get(col)
                if not anchor or case_id(anchor.get('value'),contract) is None:continue
                for r in range(int(m[2])+1,int(m[3])+1):
                    if rows[name][r].get(col,{}).get('value') in {None,''}:rows[name][r][col]={**anchor,'merged_alias':True,'row':r}
    return {'grids':[{'name':name,'rows':r} for name,r in rows.items() if states.get(name)=='visible'],'records':records,'sheet_states':states}
def word(path):
    try:return WORD['read_document'](candidate_path(path))
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def word_grids(model):
    return [{'name':t['locator'],'rows':{r['index']:{c['column']:{'value':c['text'],'locator':c['locator'],'type':'word'} for c in r['cells']} for r in t['rows']}} for t in model['tables'] if t['parent_cell'] is None]
def deck(path):
    OFFICE['_inspect_render_package'](candidate_path(path).read_bytes());records=projection(path)
    hidden=[r['locator'] for r in records if r.get('hidden') is True or re.fullmatch(r'slide:\d+',r['locator']) and r.get('show') is False]
    visible=lambda loc:not any(loc==p or loc.startswith(p+'/') for p in hidden)
    paragraphs=[r for r in records if r.get('context') in {'slide','slide_table'} and visible(r['locator']) and 'text' in r]
    tables=defaultdict(lambda:defaultdict(dict))
    for p in paragraphs:
        m=re.match(r'(.+/table:\d+)/row:(\d+)/cell:(\d+)/paragraph:\d+',p['locator'])
        if m:
            dest=tables[m[1]][int(m[2])].setdefault(int(m[3]),{'value':'','locator':p['locator'].rsplit('/paragraph:',1)[0],'type':'pptx'})
            dest['value']+=('\n' if dest['value'] else '')+p['text']
    return {'records':records,'paragraphs':paragraphs,'grids':[{'name':k,'rows':v} for k,v in tables.items()],
            'slide_count':next(r['slide_count'] for r in records if r['locator']=='presentation'),'hidden':hidden}
def case_id(value,contract):
    v=canon(value)
    return next((key for key,names in contract['case_aliases'].items() if v in {canon(n) for n in names}),None)
def channel_id(value,contract):
    v=canon(value)
    exact=next((key for key,names in contract['channel_aliases'].items() if v in {canon(n) for n in names}),None)
    if exact:return exact
    # A bilingual label such as 直销 direct denotes one channel; conflicting composites do not.
    matches=[]
    for key,names in contract['channel_aliases'].items():
        rest=v
        for alias in sorted({canon(n) for n in names},key=len,reverse=True):rest=rest.replace(alias,'')
        if rest in {'','渠道'} and rest!=v:matches.append(key)
    return matches[0] if len(matches)==1 else None
def year(value):
    text=clean(value)
    if re.search(r'(?:Q[124]|[一二四]季度)',text,re.I):return None
    ys=set(re.findall(r'20(?:25|26)',text));return int(next(iter(ys))) if len(ys)==1 else None
def field(value,contract):
    s=clean(value)
    for pattern in [r'20(?:25|26)年?\s*Q3',r'20(?:25|26)年?第三季度',r'Q3',r'第三季度',r'\bCNY\b',r'人民币',r'万元',r'元',r'百分比',r'percentage',r'\bUSD\b']:
        s=re.sub(pattern,'',s,flags=re.I)
    direct={canon(a):k for k,names in contract['field_aliases'].items() for a in names}
    return direct.get(canon(value)) or direct.get(canon(s))
MONEY={'revenue_cny','cogs_cny','gross_profit_cny','receipts_cny','minimum_cny','end_cash_cny','maximum_floor_gap_cny','balance_cny','base_change_cny','option_change_cny','initial_cash_cny','floor_cny'}
RATIOS={'gross_margin','receipts_revenue_ratio'}
def scalar(value,kind,header='',unit='',contract=None):
    s=clean(value)
    if kind in {'date','first_violation','minimum_date'}:
        if kind=='first_violation' and canon(s) in {canon(x) for x in contract['none_date_aliases']}:return None
        m=re.fullmatch(r'(20\d\d)[-/年](\d\d?)[-/月](\d\d?)(?:日|T.*| .*)?',s)
        if m:return f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
        m=re.fullmatch(r'(\d\d?)[-/月](\d\d?)日?',s)
        return f'2026-{int(m[1]):02d}-{int(m[2]):02d}' if m else 'INVALID_DATE'
    if kind=='cash_feasible':
        return next((key=='true' for key,names in contract['cash_state_aliases'].items() if canon(s) in {canon(n) for n in names}),None)
    if isinstance(value,bool) or not s:return None
    units=clean(unit)+' '+clean(header)+' '+s
    if kind in MONEY and any(k in units for k in ['USD','美元']):return None
    s=s.replace(',','').replace(' ','')
    if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
    m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(%|万元|元|CNY)?',s,re.I)
    if not m:return None
    try:n=Decimal(m[1])
    except InvalidOperation:return None
    if not n.is_finite() or abs(n)>Decimal('1e17'):return None
    if kind in MONEY and '万元' in units:n*=10000
    if kind in RATIOS:
        # Stored Excel ratios are already fractions, including percent-formatted numeric cells.
        if m[2]=='%' or (('%' in clean(header) or '%' in clean(unit)) and not isinstance(value,(int,float))):n/=100
        elif canon(unit) in {'百分比','percent','pct'}:n/=100
    return n
def observe(grids,contract):
    out={'historical':defaultdict(lambda:defaultdict(list)),'cash':defaultdict(lambda:defaultdict(list)),
         'nodes':defaultdict(lambda:defaultdict(list)),'inputs':defaultdict(list),'metadata':[]}
    def entry(cell,kind,head='',unit=''):
        if kind in RATIOS and cell.get('type')=='n' and '%' in cell.get('number_format',''):
            head=clean(head).replace('%','');unit=clean(unit).replace('%','')
        return {**cell,'observed':scalar(cell.get('value'),kind,head,unit,contract),'field':kind,'header':head,'unit':unit}
    def add(target,key,kind,cell,head='',unit=''):
        out[target][key][kind].append(entry(cell,kind,head,unit))
    for g in grids:
        rows=g['rows'];prefix=' '.join(clean(c.get('value')) for r,cells in rows.items() if r<min(rows,default=0)+5 for c in cells.values());hint=year(prefix)
        # Recognizable numeric parameter inputs. Multiple literal copies are changed together.
        for r,cells in rows.items():
            for col,c in cells.items():
                kind=field(c.get('value'),contract)
                if kind not in {'initial_cash_cny','floor_cny'}:continue
                for target in [cells.get(col+1),rows.get(r+1,{}).get(col)]:
                    if target and not target.get('formula') and scalar(target.get('value'),kind,c.get('value'),'',contract) is not None:
                        out['inputs'][kind].append(entry(target,kind,c.get('value')));break
        views=[(rows,'rows')]
        transposed=defaultdict(dict)
        for r,cells in rows.items():
            for col,cell in cells.items():transposed[col][r]=cell
        views.append((transposed,'columns'))
        for view,orientation in views:
            headers=[]
            for r,cells in sorted(view.items()):
                found={};bad=False
                for col,c in cells.items():
                    key=field(c.get('value'),contract)
                    if key:
                        if key in found:bad=True
                        found[key]=col
                if not bad and len(found)>=2 and (set(found)&{'year','channel','case_id','object','field','date'}):headers.append((r,found))
            for start,mapping in headers:
                end=min((r for r,_ in headers if r>start),default=10**9)
                head=view[start];head_hint=year(' '.join(clean(c.get('value')) for c in head.values())) or hint
                for r,cells in sorted(view.items()):
                    if not start<r<end:continue
                    get=lambda k:cells.get(mapping.get(k),{'value':None,'locator':g['name']+'/missing'})
                    obj=get('object').get('value');ch=channel_id(get('channel').get('value'),contract) or channel_id(obj,contract)
                    y=year(get('year').get('value')) or year(obj) or head_hint
                    if ch is None and year(obj):ch='ALL'
                    case=case_id(get('case_id').get('value'),contract) or case_id(obj,contract)
                    unit=get('unit').get('value','')
                    # A date/month source-record table must not masquerade as a quarterly summary.
                    monthly=any(canon(c.get('value')) in {'month','月份','月份序号','recordid','记录id'} for c in head.values())
                    for key,col in mapping.items():
                        if key in MONEY|RATIOS and y and ch and not monthly and key in {'revenue_cny','cogs_cny','gross_profit_cny','gross_margin','receipts_cny','receipts_revenue_ratio'}:
                            add('historical',f'{y}/{ch}',key,get(key),head[col].get('value'),unit)
                        if case and key in set(contract['required_cash_summary']):add('cash',case,key,get(key),head[col].get('value'),unit)
                    date=scalar(get('date').get('value'),'date',contract=contract)
                    if case and date not in {'INVALID_DATE',None} and 'balance_cny' in mapping:
                        add('nodes',case+'/'+date,'balance_cny',get('balance_cny'),head[mapping['balance_cny']].get('value'),unit)
                    if 'field' in mapping and 'value' in mapping:
                        k=field(get('field').get('value'),contract)
                        if k in MONEY|RATIOS and y and ch:add('historical',f'{y}/{ch}',k,get('value'),get('field').get('value'),unit)
                        if k in contract['required_cash_summary'] and case:add('cash',case,k,get('value'),get('field').get('value'),unit)
                        if k=='balance_cny' and case and date not in {'INVALID_DATE',None}:add('nodes',case+'/'+date,k,get('value'),get('field').get('value'),unit)
                out['metadata'].append({'grid':g['name'],'orientation':orientation,'header':start,'fields':sorted(mapping)})
        # Wide cash comparison: date plus labeled A/B/C columns, CNY or explicit 万元.
        for start,cells in rows.items():
            date_col=next((col for col,c in cells.items() if field(c.get('value'),contract)=='date'),None)
            cs={col:case_id(c.get('value'),contract) for col,c in cells.items() if case_id(c.get('value'),contract)}
            if date_col is None or len(cs)<2:continue
            for r,data in rows.items():
                if r<=start:continue
                day=scalar(data.get(date_col,{}).get('value'),'date',contract=contract)
                if day in {None,'INVALID_DATE'}:continue
                for col,case in cs.items():
                    if col in data:add('nodes',case+'/'+day,'balance_cny',data[col],cells[col].get('value'),'万元' if '万元' in prefix else '')
    return {k:dict(v) if k!='metadata' else v for k,v in out.items()}
def prose_cash(paragraphs,contract):
    out=defaultdict(lambda:defaultdict(list));active=None
    pattern_keys=contract['required_cash_summary']
    for p in paragraphs:
        text=clean(p.get('text',''));m=re.match(r'^\s*((?:方案)?[ABC](?:[_ ]?(?:phase1|deferred)|\s*(?:原排期|原计划|仅首阶段|仅第一阶段|首阶段|第二阶段延期|延期版|延期))?)\s*[:： ,，]',text,re.I)
        if m:active=case_id(m[1],contract)
        elif re.match(r'^[A-Z]\d|^U\d|^G\d',text) or '推荐' in text or '建议' in text:active=None
        if not active:continue
        for k in pattern_keys:
            names='|'.join(re.escape(x) for x in sorted(contract['field_aliases'][k],key=len,reverse=True))
            pat=r'(?:'+names+r')\s*(?:为|是|:|：|=)?\s*'
            if k in {'minimum_date','first_violation'}:pat+=r'(20\d\d[-/]\d\d?[-/]\d\d?|\d\d?月\d\d?日|none|无违规|无)'
            elif k=='cash_feasible':pat+=r'(within_floor|infeasible|feasible|可行|不可行|底线内|低于底线|true|false)'
            else:pat+=r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:万元|元|CNY)?)'
            for value in re.findall(pat,text,re.I):out[active][k].append({'observed':scalar(value,k,contract=contract),'value':value,'locator':p['locator'],'field':k,'type':'prose'})
    return {k:dict(v) for k,v in out.items()}
def recommendations(paragraphs,contract):
    found=[]
    for p in paragraphs:
        text=clean(p.get('text',''));compact=re.sub(r'\s+','',text)
        if re.match(r'^[IG]\d\d(?:[-a-z]|\s)',text):continue
        if re.search(r'访谈|引文|引用|讨论|对[“「"]',text[:24]) and re.search(r'反驳|不采纳|不采用|拒绝|不代表本轮',text):continue
        pattern=r'(?:建议|推荐|拟议选择|建议方案|选用|采用|先审批|本轮仅选|recommend|choose|select)(?:(?:本轮|本次|先|审批|优先|方案|仅|选择|为|:))*([ABC])(?=$|[^A-Za-z0-9])'
        for m in re.finditer(pattern,compact,re.I):
            before=compact[max(0,m.start()-16):m.start()]
            if re.search(r'不(?:予|再)?$|不可$|若.*$|如果.*$|可作为.*$|替代.*$|(?:donot|not|never)$',before,re.I):continue
            obj=m[1].upper();clause=re.split(r'[。；;\n]',compact[m.end():],1)[0]
            if obj=='A':obj='A_phase1' if re.search(r'仅首阶段|仅第一阶段|phase1',clause,re.I) else 'A_deferred' if re.search(r'延期|12月16|12[-/]16|deferred',clause,re.I) else 'A_phase1' if '首阶段' in clause else 'A'
            found.append({'case_id':obj,'locator':p['locator'],'text':text})
        for m in re.finditer(r'\b(?:recommend|choose|select)\s+(?:option\s+|case\s+)?(A(?:_phase1|_deferred)?|B|C)\b',text,re.I):
            before=text[max(0,m.start()-24):m.start()]
            if re.search(r'\b(?:not|never|do not|if.*?)\s*$',before,re.I):continue
            obj=m[1].upper();tail=re.split(r'[.;\n]',text[m.end():],1)[0]
            if obj=='A_PHASE1':obj='A_phase1'
            elif obj=='A_DEFERRED':obj='A_deferred'
            elif obj=='A':obj='A_phase1' if re.search(r'only\s+(?:the\s+)?first\s+stage|phase\s*1\s+only',tail,re.I) else 'A_deferred' if re.search(r'defer|delay|December\s+16',tail,re.I) else 'A'
            found.append({'case_id':obj,'locator':p['locator'],'text':text})
    return found
