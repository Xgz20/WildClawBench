"""Bounded OOXML record reader. No candidate code or external relationships executed."""
from pathlib import Path
import io,zipfile,xml.etree.ElementTree as ET,re,unicodedata,posixpath,math
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
class CandidateError(ValueError):pass
class UnsupportedRepresentation(RuntimeError):pass
def norm(v):return re.sub(r'[\s_\-]+','',unicodedata.normalize('NFKC','' if v is None else str(v)).strip()).casefold()
def candidate_path(root,rel):
 p=Path(root)/rel
 if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=Path(root).parent):raise CandidateError('candidate symlink unsupported by output contract')
 if not p.is_file():raise CandidateError('missing '+rel)
 if p.stat().st_size>32*1024*1024:raise UnsupportedRepresentation('H053_UNSUPPORTED_REPRESENTATION: artifact exceeds bounded 32 MiB reader')
 return p
def package(path):
 try:z=zipfile.ZipFile(io.BytesIO(Path(path).read_bytes()))
 except (OSError,zipfile.BadZipFile) as e:raise CandidateError('invalid native ZIP') from e
 infos=z.infolist()
 if len(infos)>5000 or sum(i.file_size for i in infos)>80*1024*1024:raise UnsupportedRepresentation('H053_UNSUPPORTED_REPRESENTATION: native ZIP exceeds bounded reader')
 if len({i.filename for i in infos})!=len(infos):raise CandidateError('duplicate native ZIP members')
 for i in infos:
  parts=i.filename.rstrip('/').split('/')
  if i.flag_bits&1 or i.filename.startswith('/') or '\\' in i.filename or any(v in {'','.','..'} for v in parts):raise CandidateError('unsafe ZIP member')
  if any(v in i.filename.casefold() for v in ['vbaproject','activex/','altchunk','afchunk']):raise UnsupportedRepresentation('H053_UNSUPPORTED_REPRESENTATION: active or alternative Office representation')
 return z
def xml(z,name):
 try:
  raw=z.read(name)
  if len(raw)>16*1024*1024 or b'<!ENTITY' in raw.upper() or b'<!DOCTYPE' in raw.upper():raise CandidateError('unsafe XML')
  return ET.fromstring(raw)
 except (KeyError,ET.ParseError,zipfile.BadZipFile) as e:raise CandidateError('missing/malformed native XML: '+name) from e
def column(s):
 n=0
 for c in s:n=n*26+ord(c)-64
 return n
def read_book(path):
 with package(path) as z:
  names=set(z.namelist());wb=xml(z,'xl/workbook.xml');rels=xml(z,'xl/_rels/workbook.xml.rels');rr={r.get('Id'):r for r in rels};strings=[]
  if len(rr)!=len(list(rels)):raise CandidateError('ambiguous workbook relations')
  if 'xl/sharedStrings.xml' in names:strings=[''.join(n.text or '' for n in si.iter(S+'t')) for si in xml(z,'xl/sharedStrings.xml')]
  sheets=[]
  for sh in wb.findall(S+'sheets/'+S+'sheet'):
   rel=rr.get(sh.get(R+'id'))
   if rel is None:raise CandidateError('missing sheet relation')
   if rel.get('TargetMode')=='External':raise UnsupportedRepresentation('H053_UNSUPPORTED_REPRESENTATION: external worksheet')
   t=rel.get('Target','');part=t.lstrip('/') if t.startswith('/') else posixpath.normpath('xl/'+t)
   if '..' in part.split('/') or not part.startswith('xl/'):raise CandidateError('invalid sheet target')
   node=xml(z,part);cells={};hiddenrows={int(row.get('r','0')) for row in node.iter(S+'row') if row.get('hidden') in {'1','true'}};hiddencols=[]
   for c in node.findall(S+'cols/'+S+'col'):
    if c.get('hidden') in {'1','true'}:hiddencols.append((int(c.get('min')),int(c.get('max'))))
   for c in node.iter(S+'c'):
    address=c.get('r','');match=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})',address)
    if not match:raise CandidateError('invalid cell address')
    row,col=int(match[2]),column(match[1]);kind=c.get('t','n');v=c.find(S+'v');value=v.text if v is not None else None
    if kind=='s':
     try:value=strings[int(value)]
     except (ValueError,TypeError,IndexError) as e:raise CandidateError('invalid shared string') from e
    elif kind=='inlineStr':value=''.join(t.text or '' for t in c.iter(S+'t'))
    elif kind=='n' and value is not None:
     try:value=float(value)
     except (ValueError,TypeError) as e:raise CandidateError('invalid numeric cell') from e
    if (row,col) in cells:raise CandidateError('duplicate cell')
    f=c.find(S+'f');cells[(row,col)]={'value':value,'formula':f is not None,'expression':f.text if f is not None else None,'address':address,'sheet':sh.get('name'),'visible':sh.get('state','visible')=='visible' and row not in hiddenrows and not any(lo<=col<=hi for lo,hi in hiddencols),'kind':kind}
   sheets.append({'name':sh.get('name'),'cells':cells,'visible':sh.get('state','visible')=='visible'})
  return sheets
def tables(book,contract):
 result={k:[] for k in contract['tables']}
 for kind,headers in contract['tables'].items():
  aliases={norm(alias):key for key,vals in headers.items() for alias in [key,*vals]}
  for sheet in book:
   if not sheet['visible']:continue
   byrow={}
   for (row,col),cell in sheet['cells'].items():
    if cell['visible']:byrow.setdefault(row,{})[col]=cell
   for row,cells in sorted(byrow.items()):
    positions={}
    for col,c in cells.items():
     key=aliases.get(norm(c['value']))
     if key is not None:
      if key in positions:continue
      positions[key]=col
    if set(positions)!=set(headers):continue
    anchor=list(headers)[0];r=row+1
    while r in byrow:
     values=byrow[r]
     ac=values.get(positions[anchor],{})
     if ac.get('value') in {None,''} or norm(ac.get('value')) in aliases:break
     record={k:values.get(c,{}).get('value') for k,c in positions.items()};record['_cells']={k:values.get(c,{'sheet':sheet['name'],'address':'','formula':False}) for k,c in positions.items()};result[kind].append(record);r+=1
 return result
def read_docx(path):
 with package(path) as z:
  node=xml(z,'word/document.xml')
  if node.find('.//'+W+'altChunk') is not None:raise UnsupportedRepresentation('H053_UNSUPPORTED_REPRESENTATION: Word altChunk')
  # Deleted/hidden text cannot serve as a delivered fact table.
  for parent in node.iter():
   for child in list(parent):
    if child.tag==W+'del' or child.tag==W+'r' and child.find('.//'+W+'vanish') is not None:parent.remove(child)
  text='\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in node.iter(W+'p'));facts={}
  for tab in node.iter(W+'tbl'):
   rows=[[''.join(t.text or '' for t in c.iter(W+'t')).strip() for c in row.findall(W+'tc')] for row in tab.findall(W+'tr')]
   if rows and len(rows[0])>=2 and norm(rows[0][0]) in {'factid','事实编号'} and norm(rows[0][1]) in {'value','数值','值'}:
    for row in rows[1:]:
     if len(row)>=2:facts.setdefault(norm(row[0]),[]).append(row[1])
  return {'text':text,'facts':facts}
def number(v):
 if isinstance(v,bool):return None
 try:
  if isinstance(v,str):
   t=unicodedata.normalize('NFKC',v).strip();n=float(t[:-1])/100 if t.endswith('%') else float(t)
  else:n=float(v)
  return n if math.isfinite(n) else None
 except (ValueError,TypeError,OverflowError):return None
def unknown(v):return v is None or norm(v) in {'','unknown','未知','待测','na','#n/a','不详'}
