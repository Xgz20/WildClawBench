"""Passive bounded OOXML cell observations and semantic table discovery."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from collections import defaultdict
import csv,io,math,posixpath,re,zipfile
import xml.etree.ElementTree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
D='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
class CandidateError(ValueError):pass
def integer(v,label):
    try:return int(v)
    except (TypeError,ValueError) as error:raise CandidateError('invalid integer '+label) from error
def point(address):
    match=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address or '')
    if not match:raise CandidateError('invalid cell address')
    col=0
    for c in match[1]:col=col*26+ord(c)-64
    row=integer(match[2],'row')
    if not 1<=col<=512 or not 1<=row<=50000:raise CandidateError('candidate table coordinate limit')
    return row,col
def canon(v):return re.sub(r'[\s_()（）/、:：-]','',str(v or '')).casefold()
def sid(value,prefix):
    if not isinstance(value,str):return None
    result=value.strip().upper()
    return result if re.fullmatch(prefix+r'[0-9]+',result) else None
def blank(v):return v is None or isinstance(v,str) and not v.strip()
def equal(value,expected,tolerance=0):
    if expected is None:return blank(value)
    if isinstance(expected,(int,float)):
        if isinstance(value,bool) or blank(value):return False
        try:a=Decimal(str(value));b=Decimal(str(expected))
        except InvalidOperation:return False
        return a.is_finite() and abs(a-b)<=Decimal(str(tolerance))+Decimal('1e-12')
    return value==expected
def read_book(path):
    p=Path(path)
    try:archive=zipfile.ZipFile(p)
    except zipfile.BadZipFile as error:raise CandidateError('invalid XLSX ZIP') from error
    with archive as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in z.infolist())>100000000:raise CandidateError('XLSX package limit or duplicates')
        def xml(name):
            try:raw=z.read(name)
            except KeyError as error:raise CandidateError('missing XLSX part '+name) from error
            if len(raw)>16000000 or b'<!DOCTYPE' in raw.replace(b'\0',b'').upper() or b'<!ENTITY' in raw.replace(b'\0',b'').upper():raise CandidateError('unsafe XLSX XML')
            try:return E.fromstring(raw)
            except E.ParseError as error:raise CandidateError('invalid XLSX XML '+name) from error
        strings=[]
        if 'xl/sharedStrings.xml' in names:strings=[''.join(n.text or '' for n in s.iter(X+'t')) for s in xml('xl/sharedStrings.xml')]
        font_defs=[];fill_defs=[];formats={};xfs=[]
        if 'xl/styles.xml' in names:
            styles=xml('xl/styles.xml');font_defs=styles.findall(X+'fonts/'+X+'font');fill_defs=styles.findall(X+'fills/'+X+'fill');xfs=styles.findall(X+'cellXfs/'+X+'xf')
            formats={integer(n.get('numFmtId'),'format id'):n.get('formatCode','') for n in styles.findall(X+'numFmts/'+X+'numFmt')}
        def invisible(style):
            if style>=len(xfs):return False
            xf=xfs[style];fid=integer(xf.get('fontId','0'),'font id');fillid=integer(xf.get('fillId','0'),'fill id');fmt=integer(xf.get('numFmtId','0'),'numFmt id')
            font=font_defs[fid] if 0<=fid<len(font_defs) else None;fill=fill_defs[fillid] if 0<=fillid<len(fill_defs) else None
            if formats.get(fmt,'').replace(' ','') in {';;;',';;;;'}:return True
            if font is None:return False
            size=font.find(X+'sz');color=font.find(X+'color');fg=fill.find(X+'patternFill/'+X+'fgColor') if fill is not None else None
            try:tiny=size is not None and float(size.get('val','11'))<6
            except ValueError as error:raise CandidateError('invalid font size') from error
            white=color is not None and color.get('rgb','').upper().endswith('FFFFFF')
            white_background=fg is None or fg.get('rgb','').upper().endswith('FFFFFF')
            return tiny or white and white_background
        rels={n.get('Id'):n.get('Target') for n in xml('xl/_rels/workbook.xml.rels') if n.get('TargetMode')!='External'}
        out=[];seen_names=set();workbook=xml('xl/workbook.xml');sheets=workbook.find(X+'sheets');properties=workbook.find(X+'workbookPr');date1904=properties is not None and properties.get('date1904','0') in {'1','true'}
        if sheets is None:raise CandidateError('missing XLSX worksheets')
        for sheet in sheets:
            name=sheet.get('name');target=rels.get(sheet.get(D+'id'))
            if not name or name in seen_names or not target:raise CandidateError('ambiguous worksheet identity')
            seen_names.add(name);part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if part.startswith('../') or part not in names:raise CandidateError('missing worksheet relationship')
            doc=xml(part);cells={};hidden_rows=set();hidden_cols=[];errors=[]
            for row in doc.findall(X+'sheetData/'+X+'row'):
                rn=integer(row.get('r'),'row')
                if row.get('hidden','0') in {'1','true'} or row.get('ht')=='0':hidden_rows.add(rn)
                for c in row.findall(X+'c'):
                    pos=point(c.get('r'));kind=c.get('t');v=c.find(X+'v');value=v.text if v is not None else None
                    if pos in cells:raise CandidateError('duplicate cell address')
                    if kind=='s':
                        i=integer(value,'shared string')
                        if not 0<=i<len(strings):raise CandidateError('invalid shared string index')
                        value=strings[i]
                    elif kind=='inlineStr':value=''.join(t.text or '' for t in c.iter(X+'t'))
                    elif kind=='b':value=value=='1'
                    elif kind=='e':errors.append({'cell':c.get('r'),'error':value})
                    elif kind not in {'str','d'} and value is not None:
                        try:value=float(value)
                        except ValueError as error:raise CandidateError('invalid numeric cell') from error
                        if not math.isfinite(value):raise CandidateError('nonfinite numeric cell')
                    cells[pos]={'value':value,'kind':kind,'cell':c.get('r'),'row':pos[0],'col':pos[1],'style':integer(c.get('s','0'),'cell style'),'formula':c.find(X+'f') is not None}
            if len(cells)>100000:raise CandidateError('XLSX cell limit')
            for col in doc.findall(X+'cols/'+X+'col'):
                if col.get('hidden','0') in {'1','true'} or col.get('width')=='0':hidden_cols.append((integer(col.get('min'),'column min'),integer(col.get('max'),'column max')))
            for m in doc.findall(X+'mergeCells/'+X+'mergeCell'):
                parts=m.get('ref','').split(':')
                if len(parts)!=2:raise CandidateError('invalid merged range')
                (r1,c1),(r2,c2)=map(point,parts)
                if r2<r1 or c2<c1 or (r2-r1+1)*(c2-c1+1)>10000:raise CandidateError('merged range limit')
                anchor=cells.get((r1,c1))
                if anchor:
                    for r in range(r1,r2+1):
                        for c in range(c1,c2+1):
                            if (r,c)==(r1,c1):continue
                            old=cells.get((r,c))
                            if old is not None and not blank(old['value']) and old['value']!=anchor['value']:raise CandidateError('conflicting merged cells')
                            cells[r,c]={**anchor,'row':r,'col':c,'merged_from':(r1,c1)}
                if len(cells)>100000:raise CandidateError('expanded cell limit')
            state=sheet.get('state','visible')
            for (r,c),cell in cells.items():cell['visible']=bool(state=='visible' and r not in hidden_rows and not any(a<=c<=b for a,b in hidden_cols) and not invisible(cell['style']))
            out.append({'name':name,'state':state,'cells':cells,'errors':errors,'date1904':date1904})
        return out

def discover(book,aliases,kind):
    lookup={canon(alias):field for field,names in aliases.items() for alias in names};rows=[];headers=[]
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        candidates=[]
        for r,values in grid.items():
            found=defaultdict(list)
            for c,cell in values.items():
                field=lookup.get(canon(cell['value']))
                if field and not cell.get('merged_from'):found[field].append(c)
            if set(found)==set(aliases) and all(len(v)==1 for v in found.values()):candidates.append((r,{k:v[0] for k,v in found.items()}))
        candidates.sort()
        for i,(r,cols) in enumerate(candidates):
            end=candidates[i+1][0] if i+1<len(candidates) else 50001
            header_ok=all(sheet['cells'][r,c]['visible'] for c in cols.values());headers.append({'sheet':sheet['name'],'row':r,'visible':header_ok})
            for rn,cells in sorted(grid.items()):
                if not r<rn<end:continue
                values={field:cells.get(col,{}).get('value') for field,col in cols.items()}
                identifier=sid(values.get('target_id'),'T') if kind=='target' else sid(values.get('record_id'),'[ST]')
                if identifier is None:continue
                visible=header_ok and all(cells.get(col,{'visible':True}).get('visible',True) for col in cols.values())
                rows.append({**values,'_id':identifier,'_sheet':sheet['name'],'_row':rn,'_visible':visible,'_columns':cols})
    return {'rows':rows,'headers':headers}
def read_csv(path,headers):
    try:text=Path(path).read_text(encoding='utf-8-sig')
    except UnicodeDecodeError as error:raise CandidateError('CSV must be UTF-8') from error
    try:
        reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
        if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)) or set(reader.fieldnames)!=set(headers):raise CandidateError('audit CSV headers mismatch')
        rows=list(reader)
    except csv.Error as error:raise CandidateError('invalid CSV') from error
    if len(rows)>10000 or any(None in row or any(v is None for v in row.values()) for row in rows):raise CandidateError('malformed or excessive CSV rows')
    return rows
