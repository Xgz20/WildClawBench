"""Passive OOXML observations for a bounded template repair contract."""
from pathlib import Path
import hashlib,json,posixpath,re,runpy,zipfile
import xml.etree.ElementTree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
D='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
READER=runpy.run_path(str(Path(__file__).with_name('xlsx_observations.py')))
CandidateError=READER['CandidateError'];equal=READER['equal'];point=READER['point']
def node(n):
    if n is None:return None
    tag=n.tag.split('}')[-1];attrs=dict(n.attrib)
    if tag in {'b','i','strike','outline','shadow','condense','extend'}:
        attrs['val']='1' if attrs.get('val','1') in {'true','1'} else '0'
        if attrs['val']=='0':return None
    if tag=='patternFill' and attrs.get('patternType')=='none':attrs.pop('patternType')
    if tag=='sz' and 'val' in attrs:attrs['val']=format(float(attrs['val']),'g')
    if tag=='alignment':
        defaults={'horizontal':{'general'},'indent':{'0'},'textRotation':{'0'},'shrinkToFit':{'0','false'},'wrapText':{'0','false'},'justifyLastLine':{'0','false'},'relativeIndent':{'0'},'readingOrder':{'0'}}
        for key,values in defaults.items():
            if attrs.get(key) in values:attrs.pop(key)
    if tag=='border':
        for key in ['diagonalUp','diagonalDown']:
            if attrs.get(key) in {'0','false'}:attrs.pop(key)
        if attrs.get('outline') in {'1','true'}:attrs.pop('outline')
    if tag=='protection':
        if attrs.get('locked') in {'1','true'}:attrs.pop('locked')
        if attrs.get('hidden') in {'0','false'}:attrs.pop('hidden')
        if not attrs:return None
    children=[v for c in n if (v:=node(c)) is not None]
    if tag=='font' and any(c[0]=='name' for c in children):children=[c for c in children if c[0]!='family']
    return [tag,dict(sorted(attrs.items())),n.text or '',sorted(children,key=lambda x:json.dumps(x,sort_keys=True))]
def formula(s):
    # Ignore layout whitespace/case outside strings only; quoted business text is significant.
    parts=re.split(r'("(?:[^"]|"")*")',str(s or '').lstrip('='))
    return ''.join(p if i%2 else re.sub(r"'([^']+)'!",r'\1!',re.sub(r'\s+','',p)).casefold() for i,p in enumerate(parts))
def snapshot(path):
    try:return _snapshot(path)
    except (KeyError,IndexError,E.ParseError,ValueError,TypeError) as error:
        if isinstance(error,CandidateError):raise
        raise CandidateError('invalid template package: '+str(error)) from error
def _snapshot(path):
    book=READER['read_book'](path)
    with zipfile.ZipFile(path) as z:
        def xml(n):return E.fromstring(z.read(n))
        styles=xml('xl/styles.xml');fonts=styles.findall(X+'fonts/'+X+'font');fills=styles.findall(X+'fills/'+X+'fill');borders=styles.findall(X+'borders/'+X+'border');xfs=styles.findall(X+'cellXfs/'+X+'xf')
        num={int(n.get('numFmtId')):n.get('formatCode') for n in styles.findall(X+'numFmts/'+X+'numFmt')}
        builtins={0:'General',1:'0',2:'0.00',3:'#,##0',4:'#,##0.00',9:'0%',10:'0.00%',14:'mm-dd-yy',49:'@'}
        def style(i):
            xf=xfs[i];get=lambda items,key:node(items[int(xf.get(key,'0'))])
            return {'font':get(fonts,'fontId'),'fill':get(fills,'fillId'),'border':get(borders,'borderId'),'format':num.get(int(xf.get('numFmtId','0')),builtins.get(int(xf.get('numFmtId','0')),'builtin-'+xf.get('numFmtId','0'))),'alignment':node(xf.find(X+'alignment')),'protection':node(xf.find(X+'protection'))}
        wb=xml('xl/workbook.xml');rels={n.get('Id'):n.get('Target') for n in xml('xl/_rels/workbook.xml.rels')};names={}
        for n in wb.findall(X+'definedNames/'+X+'definedName'):
            identity=n.get('name')
            if not identity or identity in names or n.get('localSheetId') is not None:raise CandidateError('ambiguous/scoped template name')
            names[identity]=n.text or ''
        result={'names':names,'sheets':[]}
        for header,sheet in zip(wb.find(X+'sheets'),book):
            target=rels[header.get(D+'id')];part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target);doc=xml(part)
            native={c.get('r'):c for c in doc.findall(X+'sheetData/'+X+'row/'+X+'c')}
            cells={}
            for cell in sheet['cells'].values():
                address=cell['cell'];element=native.get(address)
                f=element.find(X+'f') if element is not None else None
                cells[address]={'value':None if f is not None else cell['value'],'formula':f.text or '' if f is not None else None,'visible':cell['visible'],'style':style(cell['style'])}
            cols=[]
            for n in doc.findall(X+'cols/'+X+'col'):
                for i in range(int(n.get('min')),int(n.get('max'))+1):
                    cols.append([i,round(float(n.get('width','0')),3),n.get('hidden','0') in {'1','true'}])
            rows=[[int(n.get('r')),round(float(n.get('ht','15')),3),n.get('hidden','0') in {'1','true'}] for n in doc.findall(X+'sheetData/'+X+'row')]
            result['sheets'].append({'name':sheet['name'],'state':sheet['state'],'cells':cells,'cols':cols,'rows':rows,'merges':sorted(n.get('ref') for n in doc.findall(X+'mergeCells/'+X+'mergeCell')),'panes':node(doc.find(X+'sheetViews/'+X+'sheetView/'+X+'pane'))})
        return result
def eligible(address):
    row,col=point(address)
    return 6<=row<=17 and 5<=col<=8
def helper(address):
    row,col=point(address)
    return 5<=row<=17 and 10<=col<=15
def preservation(current,source):
    checks={};checks['sheet_order']=[s['name'] for s in current['sheets']]==[s['name'] for s in source['sheets']]
    old={s['name']:s for s in source['sheets']};new={s['name']:s for s in current['sheets']}
    for name,orig in old.items():
        c=new.get(name)
        if c is None:checks[name+'/present']=False;continue
        for key in ['state','cols','rows','merges','panes']:checks[name+'/'+key]=c[key]==orig[key]
        for addr,cell in orig['cells'].items():
            got=c['cells'].get(addr)
            if name=='Leave' and helper(addr):continue
            if got is None:checks[name+'/'+addr]=False;continue
            checks[name+'/'+addr+'/style']=cell['style']==got['style']
            checks[name+'/'+addr+'/visible']=cell['visible']==got['visible']
            if name=='Leave' and eligible(addr):continue
            checks[name+'/'+addr+'/content']=formula(cell['formula'])==formula(got['formula']) and (cell['formula'] is not None)==(got['formula'] is not None) and equal(got['value'],cell['value'],1e-10)
        for addr,cell in c['cells'].items():
            if addr not in orig['cells'] and not (name=='Leave' and helper(addr)) and (cell['formula'] is not None or not READER['blank'](cell['value'])):checks[name+'/'+addr+'/unexpected']=False
    names=dict(source['names']);names['AsOfDate']="Control!$B$3"
    checks['names']=set(current['names'])==set(names) and all(formula(current['names'][k])==formula(v) for k,v in names.items())
    return checks
def values(path,scenario):
    book={s['name']:s for s in READER['read_book'](path)};checks={};visible=True
    for row in scenario['expected']:
        r=row['row']
        for c,key in enumerate(['complete_years','base_days','entitled_days','status'],5):
            cell=book.get('Leave',{}).get('cells',{}).get((r,c),{})
            checks[row['employee_id']+'/'+key]=equal(cell.get('value'),row[key],1e-9);visible &= cell.get('visible',False)
    cells=book.get('Leave',{}).get('cells',{})
    checks['total_days']=equal(cells.get((3,7),{}).get('value'),scenario['total_days'],1e-9)
    import datetime as dt
    serial=(dt.date.fromisoformat(scenario['as_of'])-dt.date(1899,12,30)).days
    checks['as_of_display']=equal(cells.get((3,3),{}).get('value'),serial,0)
    return {'checks':checks,'complete':all(checks.values()),'visible':visible,'score':sum(checks.values())/len(checks)}
def tables(text):
    result=[];lines=text.splitlines();i=0
    def split(s):return [x.strip().strip('`').strip() for x in s.strip().strip('|').split('|')]
    while i+1<len(lines):
        header=split(lines[i]);sep=split(lines[i+1])
        if len(header)==len(sep) and len(header)>1 and all(re.fullmatch(r':?-{3,}:?',x) for x in sep):
            rows=[];i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip():
                fields=split(lines[i]);rows.append(dict(zip(header,fields)) if len(fields)==len(header) else {});i+=1
            result.append({'header':header,'rows':rows})
        else:i+=1
    return result
def report(text,source,current,expected):
    tt=tables(text);changes=[t for t in tt if t['header']==['target','before','after','rule_id']];verify=[t for t in tt if t['header']==['employee_id','as_of_date','complete_years','base_days','entitled_days','status']]
    bindings={};facts={};crows=changes[0]['rows'] if len(changes)==1 else [];vrows=verify[0]['rows'] if len(verify)==1 else []
    old={s['name']:s for s in source['sheets']};new={s['name']:s for s in current['sheets']} if current else {}
    wanted=[('AsOfDate','R-date')]+[('Leave!'+c+'6',rule) for c,rule in zip('EFGH',['R-years','R-band','R-half','R-missing'])]
    for target,rule in wanted:
        found=[r for r in crows if r.get('target')==target];row=found[0] if len(found)==1 else {}
        before=source['names']['AsOfDate'] if target=='AsOfDate' else old['Leave']['cells'][target.split('!')[1]]['formula']
        after=(current or {}).get('names',{}).get('AsOfDate') if target=='AsOfDate' else new.get('Leave',{}).get('cells',{}).get(target.split('!')[1],{}).get('formula')
        bindings[target]=bool(row and after is not None and formula(row.get('before'))==formula(before) and formula(row.get('after'))==formula(after) and row.get('rule_id')==rule and (target=='AsOfDate' or row.get('after','').startswith('=')))
    for spec in expected['scenarios'][:3]:
        for want in spec['expected']:
            key=want['employee_id']+'/'+want['as_of_date'];found=[r for r in vrows if r.get('employee_id')==want['employee_id'] and r.get('as_of_date')==want['as_of_date']];got=found[0] if len(found)==1 else {}
            facts[key]=bool(got) and all(equal(got.get(k),want[k],1e-9) for k in ['complete_years','base_days','entitled_days','status'])
    cardinality=len(crows)==5 and len(vrows)==36
    return {'bindings':bindings,'facts':facts,'cardinality':cardinality,'complete':cardinality and all(bindings.values()) and all(facts.values()),'facts_score':sum(facts.values())/len(facts),'binding_score':sum(bindings.values())/len(bindings)}
