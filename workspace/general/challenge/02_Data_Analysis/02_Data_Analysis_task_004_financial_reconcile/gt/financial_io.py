"""Semantic source/metric/Word discovery without fixed coordinates or sheet names."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import csv,io,re,runpy,unicodedata,datetime,posixpath,zipfile
import xml.etree.ElementTree as E
HERE=Path(__file__).resolve().parent
XLSX=runpy.run_path(str(HERE/'xlsx_observations.py'));WORD=runpy.run_path(str(HERE/'word_model.py'));CandidateError=XLSX['CandidateError']
def canon(v):return re.sub(r'[\s_()（）/、:：%％-]','',unicodedata.normalize('NFKC',str(v if v is not None else ''))).casefold()
def render_canon(v):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(v))).replace('−','-')
def blank(v):return v is None or isinstance(v,str) and not v.strip()
def na(v):return isinstance(v,str) and canon(v) in {'na','不适用','不可计算'}
def number(v):
    if isinstance(v,bool) or blank(v):return None
    text=unicodedata.normalize('NFKC',str(v)).strip().replace('−','-')
    if text.startswith('(') and text.endswith(')'):text='-'+text[1:-1]
    text=re.sub(r'(?:万元|个百分点|百分点|pp|倍)$','',text,flags=re.I).strip()
    if re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?',text):text=text.replace(',','')
    try:value=Decimal(text)
    except InvalidOperation:return None
    return value if value.is_finite() else None
def equal(v,w,tol=1e-9,nullable=False,word_rate=False,percent_header=False):
    if w is None:return na(v) or nullable and blank(v)
    if w=='':return blank(v) or canon(v) in {'none','无','正常'}
    if isinstance(w,str):return v==w
    text=unicodedata.normalize('NFKC',str(v if v is not None else '')).strip();percent=word_rate and ('%' in text or percent_header)
    value=number(text.replace('%','') if percent else v)
    if value is None:return False
    if percent:value/=100
    return abs(value-Decimal(str(w)))<=Decimal(str(tol))
def company(v):
    key=canon(v).upper();known={'A':'A','B':'B','C':'C','青川实业':'A','北辰服务':'B','澄星制造':'C','A青川实业':'A','B北辰服务':'B','C澄星制造':'C'}
    return known.get(key,key if re.fullmatch(r'[A-Z]',key) else None)
def year(v):
    text=str(v or '').strip();m=re.fullmatch(r'(20\d\d)(?:年|[-/]\d{1,2}[-/]\d{1,2})?',text)
    if m:return int(m[1])
    value=number(v)
    if value is not None and value==int(value):
        if 2000<=value<=2100:return int(value)
        if 40000<=value<=60000:return (datetime.date(1899,12,30)+datetime.timedelta(days=int(value))).year
    return None
def mapped(v,lookup):
    key=canon(v)
    return next((name for name,aliases in lookup.items() if key in {canon(a) for a in [name,*aliases]}),None)
def metric(v,contract):return mapped(v,contract['metric_aliases'])
def reason(v,contract):return '' if blank(v) or canon(v) in {'none','无','正常'} else mapped(v,contract['reason_aliases']) or str(v).strip()
def status(v):return 'ok' if canon(v) in {'ok','正常','可比','有效'} else 'not_comparable' if canon(v) in {'notcomparable','不可比','不适用','不可计算'} else v
def candidate_path(root,name):
    p=Path(root)/'results'/name
    if p.parent.is_symlink() or not p.is_file() or p.is_symlink() or p.stat().st_size>5242880 or p.resolve().parent!=p.parent.resolve():raise CandidateError('missing, unsafe or oversized '+name)
    return p
def read_word(path):
    try:return WORD['read_document'](path)
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def grids_word(model):
    grids=[]
    for table in model['tables']:
        if table['parent_cell'] is not None:continue
        cells={}
        for anchor in table['anchors']:
            if anchor.get('invalid_merge'):raise CandidateError('invalid Word merged-cell relation')
            texts=list(dict.fromkeys(t for t in anchor['text_parts'] if t.strip()));value=texts[0] if len(texts)==1 else '\n'.join(texts)
            for row in range(anchor['row'],anchor['row']+anchor['rowspan']):
                for col in range(anchor['column'],anchor['column']+anchor['colspan']):cells[row,col]={'value':value,'row':row,'col':col,'visible':True,'locator':anchor['locator']}
        grids.append({'name':table['locator'],'cells':cells,'state':'visible'})
    return grids
def discover(grids,aliases,required,id_test):
    lookup={canon(a):key for key,values in aliases.items() for a in values};out=[]
    for grid in grids:
        rows=defaultdict(dict)
        for (r,c),cell in grid['cells'].items():rows[r][c]=cell
        headers=[]
        for r,values in sorted(rows.items()):
            found=defaultdict(list)
            for c,cell in values.items():
                key=lookup.get(canon(cell['value']))
                if key and not cell.get('merged_from'):found[key].append(c)
            if not set(required)<=set(found) or any(len(found[k])!=1 for k in required):continue
            headers.append((r,{k:v[0] for k,v in found.items() if len(v)==1}))
        for i,(r,cols) in enumerate(headers):
            end=headers[i+1][0] if i+1<len(headers) else 50001
            for rn,row in sorted(rows.items()):
                if not r<rn<end:continue
                values={k:row.get(c,{}).get('value') for k,c in cols.items()}
                if not id_test(values):continue
                locations={k:{'sheet':grid['name'],'row':rn,'col':c,'cell':row.get(c,{}),'header':grid['cells'][r,c]['value']} for k,c in cols.items()};visible=all(grid['cells'][r,cols[k]]['visible'] and row.get(cols[k],{'visible':True}).get('visible',True) for k in required)
                out.append({**values,'_locations':locations,'_visible':visible,'_group':(grid['name'],r)})
    return out
def identity(row,contract,metric_record=True):
    key=(company(row.get('company_id')),year(row.get('period_year')))
    return (*key,metric(row.get('metric_id'),contract)) if metric_record else key
def records(book,contract,kind,word=False):
    fields=['company_id','period_year']+(['metric_id','value','rank'] if word else ['metric_id',*contract['metric_fields']]) if kind=='metric' else ['company_id','period_year',*contract['data_fields']]
    return discover(book,contract['aliases'],fields,lambda r:company(r.get('company_id')) is not None and year(r.get('period_year')) is not None and (kind!='metric' or metric(r.get('metric_id'),contract) is not None))
def formula_coverage(path,book):
    S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';D='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(path) as z:
        wb=E.fromstring(z.read('xl/workbook.xml'));rels={n.get('Id'):n.get('Target') for n in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet,observed in zip(wb.find(S+'sheets'),book):
            target=rels[sheet.get(D+'id')];part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target);doc=E.fromstring(z.read(part))
            for f in doc.iter(S+'f'):
                ref=f.get('ref')
                if not ref:continue
                ends=ref.replace('$','').split(':');ends=ends*2 if len(ends)==1 else ends
                if len(ends)!=2:raise CandidateError('unsupported output formula range syntax')
                a,b=map(XLSX['point'],ends)
                for (r,c),cell in observed['cells'].items():
                    if a[0]<=r<=b[0] and a[1]<=c<=b[1]:cell['formula']=True
    return book
def csv_rows(path,fields):
    try:text=Path(path).read_text(encoding='utf-8-sig')
    except UnicodeDecodeError as e:raise CandidateError('source CSV must be UTF-8') from e
    try:
        reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)) or not set(fields)<=set(reader.fieldnames):raise CandidateError('source CSV headers mismatch')
        rows=list(reader)
    except csv.Error as e:raise CandidateError('invalid source CSV') from e
    if len(rows)>10000 or any(None in r or any(r.get(k) is None for k in fields) for r in rows):raise CandidateError('invalid source CSV rows')
    return [{k:r[k] for k in fields} for r in rows]
def source_path(v,statement=False):
    value=str(v or '').strip().replace('\\','/')
    if value.startswith('/tmp_workspace/'):value=value[len('/tmp_workspace/'):]
    value=posixpath.normpath(value)
    if value.startswith('../') or value=='..' or value.startswith('/'):return None
    return 'statements/'+value if statement and '/' not in value else value
