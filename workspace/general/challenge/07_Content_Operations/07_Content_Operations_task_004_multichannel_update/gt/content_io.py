"""Bounded native/text extraction; no candidate Python, JS, macros or network code run here."""
from pathlib import Path
from html.parser import HTMLParser
import io,json,re,unicodedata,zipfile,xml.etree.ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
class CandidateError(ValueError):pass
class UnsupportedRepresentation(RuntimeError):pass
def norm(v):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(v or ''))).casefold()
def path(root,rel):
 p=Path(root)/rel
 if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=Path(root).parent):raise CandidateError('candidate symlink')
 if not p.is_file():raise CandidateError('missing '+rel)
 if p.stat().st_size>5*1024*1024:raise UnsupportedRepresentation('H060_UNSUPPORTED_REPRESENTATION: file above bounded5MiB reader')
 return p
def json_read(p):
 def pairs(values):
  d={}
  for k,v in values:
   if k in d:raise ValueError('duplicate key')
   d[k]=v
  return d
 try:
  v=json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
  if not isinstance(v,dict):raise ValueError('object required')
  return v
 except (OSError,ValueError,UnicodeError) as e:raise CandidateError('invalid JSON') from e
def text_read(p):
 try:return p.read_text(encoding='utf-8-sig')
 except (OSError,UnicodeError) as e:raise CandidateError('UTF-8 text required') from e
class StaticHTML(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.text=[];self.headings=0;self.main=False;self.active=[];self.external=[];self.ids=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs);self.stack.append(tag)
  if attrs.get('id'):self.ids.append(attrs['id'])
  if tag=='h1':self.headings+=1
  if tag in ['main','article']:self.main=True
  if tag in ['script','iframe','frame','object','embed','form','input','textarea'] or any(k.lower().startswith('on') for k in attrs):self.active.append(tag)
  for key,value in attrs.items():
   if key in ['src','href','action','poster'] and value and not value.startswith(('#','data:')):self.external.append(value)
  if tag=='style':return
 def handle_endtag(self,tag):
  if tag in self.stack:self.stack=self.stack[:len(self.stack)-self.stack[::-1].index(tag)-1]
 def handle_data(self,data):
  if not set(self.stack)&{'head','script','style','template','noscript'} and data.strip():self.text.append(data)
def html_static(raw):
 v=StaticHTML()
 try:v.feed(raw);v.close()
 except Exception as e:raise CandidateError('malformed HTML') from e
 css_external=bool(re.search(r'@import|url\(\s*["\']?(?:https?:|//|file:)',raw,re.I));return {'raw':raw,'text':'\n'.join(v.text),'h1':v.headings,'semantic_container':v.main,'active':v.active,'external':v.external,'css_external':css_external,'duplicate_ids':len(v.ids)!=len(set(v.ids))}
def html_visible(observation):
 texts=[];hidden=[]
 for row in observation['projection']['texts']:
  style=row.get('style',{});size=re.search(r'[0-9.]+',style.get('fontSize',''));rects=row.get('rects',[]);inbounds=any(r['width']>0 and r['height']>0 and r['x']+r['width']>0 and r['y']+r['height']>0 and r['x']<observation['projection']['document_size']['width'] for r in rects);visible=row.get('visible') and size is not None and float(size[0])>=10 and inbounds
  if style.get('clipPath','none')!='none' or style.get('mask','none')!='none':raise UnsupportedRepresentation('H060_UNSUPPORTED_REPRESENTATION: clipped/masked text needs independent review')
  if re.fullmatch(r'rgba?\(255,\s*255,\s*255(?:,\s*1)?\)',style.get('color','')) and style.get('backgroundColor') in {'rgb(255, 255, 255)','rgba(0, 0, 0, 0)'}:visible=False
  (texts if visible else hidden).append(row['text'])
 return {'text':'\n'.join(texts),'paragraphs':texts,'excluded_fragments':hidden,'visibility_limit':'NativeDOM display/opacity/geometry/font-size plus bounded simplewhite-text guard, not full visual-composition or semantic proof'}
def word(p):
 try:z=zipfile.ZipFile(io.BytesIO(p.read_bytes()))
 except (OSError,zipfile.BadZipFile) as e:raise CandidateError('invalid Word ZIP') from e
 with z:
  infos=z.infolist()
  if len(infos)>3000 or sum(i.file_size for i in infos)>40*1024*1024:raise UnsupportedRepresentation('H060_UNSUPPORTED_REPRESENTATION: bounded Word reader limit')
  if len({i.filename for i in infos})!=len(infos):raise CandidateError('duplicate Word member')
  for i in infos:
   if i.flag_bits&1 or i.filename.startswith('/') or '\\' in i.filename or '..' in i.filename.split('/'):raise CandidateError('unsafe Word package')
  try:raw=z.read('word/document.xml')
  except KeyError as e:raise CandidateError('missing Word document part') from e
  if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise CandidateError('unsafe WordXML')
  try:node=ET.fromstring(raw)
  except ET.ParseError as e:raise CandidateError('malformed WordXML') from e
  if node.find('.//'+W+'altChunk') is not None:raise UnsupportedRepresentation('H060_UNSUPPORTED_REPRESENTATION: alternate Word chunks')
  for parent in node.iter():
   for child in list(parent):
    remove=child.tag==W+'del'
    if child.tag==W+'r':
     for name in ['vanish','webHidden']:
      v=child.find('.//'+W+name)
      if v is not None and v.get(W+'val','true') not in ['0','false','off']:remove=True
     size=child.find('.//'+W+'sz');color=child.find('.//'+W+'color');shade=child.find('.//'+W+'shd')
     if size is not None and size.get(W+'val','').isdigit() and int(size.get(W+'val'))<16:remove=True
     if color is not None and color.get(W+'val','').upper()=='FFFFFF' and (shade is None or shade.get(W+'fill','').upper() in ['','FFFFFF','AUTO']):remove=True
    if remove:parent.remove(child)
  paragraphs=[''.join(t.text or '' for t in p.iter(W+'t')).strip() for p in node.iter(W+'p')];paragraphs=[p for p in paragraphs if p];return {'text':'\n'.join(paragraphs),'paragraphs':paragraphs}
def markdown(raw):
 text=re.sub(r'<!--[\s\S]*?-->','',raw);text=re.sub(r'(?ms)^\s*```[^\n]*\n.*?^\s*```\s*','',text);text=re.sub(r'!\[[^\]]*\]\([^)]*\)','',text);text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text);text=re.sub(r'<(?:script|style)\b[\s\S]*?</(?:script|style)>','',text,flags=re.I);text=re.sub(r'<[^>]+>','',text);text=re.sub(r'(?m)^\s{0,3}#{1,6}\s*','',text);text=re.sub(r'[*`_]','',text);paragraphs=[p.strip() for p in re.split(r'\n\s*\n',text) if p.strip()];return {'text':'\n'.join(paragraphs),'paragraphs':paragraphs,'raw':raw}
def natural(quote):
 s=quote.strip()
 if not s:return False
 if s.startswith(('{','[')) or re.search(r'"[A-Za-z_][A-Za-z_0-9]*"\s*:',s):return False
 return len(s)>=2 and not re.fullmatch(r'[A-Z0-9_{}\[\]":,.\s]+',s)
def bind(channel,location):
 if not isinstance(location,dict) or not isinstance(location.get('quote'),str) or not natural(location['quote']):return False
 quote=norm(location['quote']);locator=location.get('locator') or {'kind':'quote','occurrence':1};kind=locator.get('kind') if isinstance(locator,dict) else None
 if kind=='paragraph':
  index=locator.get('index');paras=channel.get('paragraphs',[])
  return type(index) is int and 1<=index<=len(paras) and quote in norm(paras[index-1])
 if kind=='quote':
  number=locator.get('occurrence',1);return type(number) is int and number>=1 and norm(channel.get('text','')).count(quote)>=number
 raise UnsupportedRepresentation('H060_UNSUPPORTED_REPRESENTATION: legal unimplemented content locator requires evaluator review')
