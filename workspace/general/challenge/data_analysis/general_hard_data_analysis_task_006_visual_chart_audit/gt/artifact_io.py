"""Sparse, read-only XLSX observations and unit/region normalization for H022."""
from pathlib import Path
import json,math,posixpath,re,runpy,unicodedata,zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote

OFFICE=runpy.run_path(str(Path(__file__).with_name('office_runtime.py')))
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
CONTENT_ERRORS={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT'}
class CandidateError(ValueError):pass
def clean(v):return unicodedata.normalize('NFKC',str(v if v is not None else '')).strip()
def key(v):return re.sub(r'[\s_\-()（）:：]','',clean(v)).lower()
def safe(path,limit=5_242_880):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.parent.is_symlink() or p.stat().st_size>limit:raise CandidateError('missing/unsafe/oversized '+p.name)
    return p
def text(path,limit=1_048_576):
    try:return safe(path,limit).read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError) as exc:raise CandidateError('unreadable text output') from exc
def column(address):
    value=0
    for c in re.match('[A-Z]+',address)[0]:value=value*26+ord(c)-64
    return value
def workbook(path):
    p=safe(path)
    try:
        OFFICE['_clean_package'](p.read_bytes())
        with zipfile.ZipFile(p) as z:
            def xml(name):
                raw=z.read(name)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise CandidateError('XML entities unsupported')
                return ET.fromstring(raw)
            book=xml('xl/workbook.xml');rels=xml('xl/_rels/workbook.xml.rels')
            targets={r.get('Id'):r.get('Target') for r in rels if r.get('TargetMode')!='External'}
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(n.text or '' for n in item.iter(S+'t')) for item in xml('xl/sharedStrings.xml').findall(S+'si')]
            formats={0:'General',9:'0%',10:'0.00%'};styles=[]
            if 'xl/styles.xml' in z.namelist():
                st=xml('xl/styles.xml')
                for item in st.findall(S+'numFmts/'+S+'numFmt'):formats[int(item.get('numFmtId'))]=item.get('formatCode','')
                styles=[formats.get(int(item.get('numFmtId','0')),'') for item in st.findall(S+'cellXfs/'+S+'xf')]
            sheets=[]
            for sh in book.findall(S+'sheets/'+S+'sheet'):
                name=sh.get('name');target=targets.get(sh.get(R+'id'))
                if not target:raise CandidateError('missing sheet relationship')
                part=posixpath.normpath(unquote(target).lstrip('/') if target.startswith('/') else 'xl/'+unquote(target))
                if not part.startswith('xl/'):raise CandidateError('sheet escapes package')
                tree=xml(part);cells={};hidden_rows={int(n.get('r')) for n in tree.findall(S+'sheetData/'+S+'row') if n.get('hidden') in {'1','true'}}
                hidden_cols=[(int(n.get('min')),int(n.get('max'))) for n in tree.findall(S+'cols/'+S+'col') if n.get('hidden') in {'1','true'}]
                for cell in tree.iter(S+'c'):
                    address=cell.get('r','')
                    if not re.fullmatch('[A-Z]{1,3}[1-9][0-9]{0,6}',address):raise CandidateError('invalid cell address')
                    row=int(re.search('[0-9]+',address)[0]);col=column(address);kind=cell.get('t','n');value=cell.find(S+'v')
                    raw=value.text if value is not None else None
                    if kind=='inlineStr':value=''.join(n.text or '' for n in cell.iter(S+'t'))
                    elif kind=='s':value=strings[int(raw)] if raw is not None else ''
                    elif kind=='b':value=raw=='1'
                    elif kind in {'str','e'}:value=raw or ''
                    elif raw is None:value=None
                    else:
                        try:value=float(raw)
                        except ValueError:raise CandidateError('invalid native numeric value')
                    style=int(cell.get('s','0'));formula=cell.find(S+'f')
                    cells[(row,col)]={'value':value,'number_format':styles[style] if 0<=style<len(styles) else '',
                        'formula':formula.text if formula is not None else None,'type':kind,'address':address,
                        'visible':sh.get('state','visible')=='visible' and row not in hidden_rows and not any(a<=col<=b for a,b in hidden_cols)}
                merges=[]
                for item in tree.findall(S+'mergeCells/'+S+'mergeCell'):
                    a,b=item.get('ref').split(':');merges.append((int(re.search('[0-9]+',a)[0]),column(a),int(re.search('[0-9]+',b)[0]),column(b)))
                sheets.append({'name':name,'visible':sh.get('state','visible')=='visible','cells':cells,'merges':merges})
            return sheets
    except OFFICE['OfficeRuntimeError'] as e:
        if e.code not in CONTENT_ERRORS:raise
        raise CandidateError(e.code) from e
    except (OSError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,TypeError,ValueError) as e:
        if isinstance(e,CandidateError):raise
        raise CandidateError(str(e)) from e

def grid_cell(sheet,row,col):
    cell=sheet['cells'].get((row,col))
    if cell:return cell
    for r0,c0,r1,c1 in sheet['merges']:
        if r0<=row<=r1 and c0<=col<=c1:return sheet['cells'].get((r0,c0))
    return None
def collect(sheets,contract):
    aliases={key(alias):name for name,items in contract['column_aliases'].items() for alias in items}
    claims={};readings={};metadata={'headers':[],'unidentified_ids':[]}
    orientations=[]
    for sheet in sheets:
        orientations.append({**sheet,'orientation':'records_in_rows'})
        orientations.append({**sheet,'orientation':'records_in_columns','cells':{(c,r):cell for (r,c),cell in sheet['cells'].items()},
            'merges':[(c0,r0,c1,r1) for r0,c0,r1,c1 in sheet['merges']]})
    for sheet in orientations:
        if not sheet['visible']:continue
        rows=sorted({r for r,c in sheet['cells']});active={};header_row=None
        for row in rows:
            present={c:cell for (r,c),cell in sheet['cells'].items() if r==row and cell['visible']}
            for r0,c0,r1,c1 in sheet['merges']:
                if r0<=row<=r1:
                    anchor=sheet['cells'].get((r0,c0))
                    if anchor and anchor['visible']:
                        for col in range(c0,min(c1,c0+128)+1):present.setdefault(col,anchor)
            candidate={};header_units={}
            for col,cell in present.items():
                text=clean(cell['value']);bare=re.sub(r'[（(][^()（）]*[)）]','',text)
                name=aliases.get(key(text)) or aliases.get(key(bare))
                if name:
                    if name in candidate:candidate[name]=None
                    else:candidate[name]=col
                    if name in {'lower','upper'}:
                        unit=re.search(r'[（(]([^()（）]*)[)）]',text)
                        if unit:header_units[name]=unit[1]
            if any(name in candidate for name in ['claim_id','reading_id']) and any(name in candidate for name in ['decision','lower','upper']):
                active={name:col for name,col in candidate.items() if col is not None};header_row=row
                active['_header_units']=header_units;metadata['headers'].append({'sheet':sheet['name'],'row':row,'orientation':sheet['orientation'],'columns':{k:v for k,v in active.items() if not k.startswith('_')}});continue
            if not active:continue
            observed={};cells={}
            for name,col in active.items():
                if name.startswith('_'):continue
                cell=grid_cell(sheet,row,col)
                if cell and cell['visible']:observed[name]=cell['value'];cells[name]=cell
            if 'unit' not in observed:
                units=set(active['_header_units'].values())
                if len(units)==1:observed['unit']=next(iter(units))
            for field,prefix,target in [('claim_id','C',claims),('reading_id','R',readings)]:
                value=clean(observed.get(field));match=re.fullmatch(prefix+r'0*([1-9][0-9]?)',value,re.I)
                if not match:continue
                identity=prefix+f'{int(match[1]):02}'
                target.setdefault(identity,[]).append({'values':observed,'cells':cells,'location':{'sheet':sheet['name'],'row':row,'header_row':header_row,'orientation':sheet['orientation']}})
    return claims,readings,metadata
def decision(v,contract):return next((name for name,items in contract['decision_aliases'].items() if key(v) in {key(x) for x in items}),None)
def axis(v,contract):return next((name for name,items in contract['axis_aliases'].items() if key(v) in {key(x) for x in items}),None)
def unit(v,contract):return next((name for name,items in contract['unit_aliases'].items() if key(v) in {key(x) for x in items}),None)
def number(cell):
    if not cell:return None,False
    value=cell['value'];literal_percent=False
    if isinstance(value,bool) or value is None:return None,False
    if isinstance(value,str):
        value=clean(value).replace(',','');literal_percent=value.endswith('%')
        if literal_percent:value=value[:-1]
        try:value=float(value)
        except ValueError:return None,False
    if not isinstance(value,(float,int)) or not math.isfinite(value):return None,False
    fmt=re.sub(r'"[^\"]*"|\\.','',cell.get('number_format',''))
    return float(value),literal_percent or '%' in fmt
def normalized_bounds(row,want,contract):
    actual_unit=unit(row['values'].get('unit'),contract);out=[]
    for field in ['lower','upper']:
        value,percent=number(row['cells'].get(field))
        if value is None:return None,actual_unit
        cell=row['cells'][field];is_literal=isinstance(cell['value'],str) and clean(cell['value']).endswith('%')
        if want in {'千人','人'}:
            factors={'people':1.,'thousand_people':1000.,'ten_thousand_people':10000.}
            if actual_unit not in factors:return None,actual_unit
            value=value*factors[actual_unit]/(1000. if want=='千人' else 1.)
        elif want=='%':
            if actual_unit=='percent':value=value if is_literal or not percent else value*100
            elif actual_unit=='fraction':value=value if is_literal else value*100
            else:return None,actual_unit
        else:
            if actual_unit=='percent':value=value/100 if is_literal or not percent else value
            elif actual_unit in {'multiple','fraction'}:value=value/100 if is_literal else value
            else:return None,actual_unit
        out.append(value)
    return out,actual_unit
def image_file(value):
    text=clean(value).replace('\\','/');name=text.rsplit('/',1)[-1]
    match=re.fullmatch(r'chart_([ABCD])\.png',name,re.I)
    if not match:
        match=re.fullmatch(r'图?([ABCD])',text,re.I)
        if match:return 'chart_pages/chart_'+match[1].upper()+'.png'
        return None
    return 'chart_pages/chart_'+match[1].upper()+'.png'
def regions(value,width=1467,height=960):
    text=clean(value);result=[]
    try:obj=json.loads(text)
    except (json.JSONDecodeError,TypeError):obj=None
    def walk(item,mode=None):
        if isinstance(item,dict):
            current=item.get('coordinate_system',item.get('coordinates',mode));boxes=item.get('boxes',item.get('bbox',item.get('regions')))
            if boxes is not None:walk(boxes,current)
        elif isinstance(item,list):
            if len(item)==4 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in item):
                values=[float(x) for x in item];pixels=key(mode) in {'pixel','pixels','像素'} or (not mode and max(values)>1)
                if pixels:values=[values[0]/width,values[1]/height,values[2]/width,values[3]/height]
                if 0<=values[0]<values[2]<=1 and 0<=values[1]<values[3]<=1:result.append(values)
            else:
                for box in item:walk(box,mode)
    if obj is not None:walk(obj)
    else:
        matches=re.findall(r'\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]',text)
        for match in matches:
            try:walk([float(v) for v in match],'pixel' if re.search('pixel|像素',text,re.I) else None)
            except ValueError:pass
    return result
def overlap(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])
def hit(boxes,target):
    # A full-image rectangle is not a focused visual locator; alternative real crops remain allowed.
    return any((box[2]-box[0])*(box[3]-box[1])<.8 and overlap(box,target) for box in boxes)
def mean(items):
    values=list(items);return sum(values)/len(values) if values else 0.
