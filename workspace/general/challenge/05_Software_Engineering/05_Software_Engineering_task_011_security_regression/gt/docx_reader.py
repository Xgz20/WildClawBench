import re,zipfile,xml.etree.ElementTree as ET
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
class ProfileUnsupported(RuntimeError):pass
def text(node):
 values=[]
 for run in node.findall('.//w:r',N):
  hidden=any(x.attrib.get('{'+N['w']+'}val','true').lower() not in ('0','false','off') for tag in ('vanish','webHidden') for x in run.findall('w:rPr/w:'+tag,N))
  if not hidden:values.extend(x.text or '' for x in run.findall('w:t',N))
 return ''.join(values)
def load(path):
 with zipfile.ZipFile(path) as z:
  info=z.infolist()
  if len(info)>1000 or sum(x.file_size for x in info)>10*1024*1024:raise ProfileUnsupported('native DOCX beyond1000 members/10MiB profile')
  names={x.filename for x in info}
  if not {'[Content_Types].xml','word/document.xml'}<=names:raise ValueError('not native DOCX')
  if any(x.startswith('/') or '..' in x.split('/') for x in names):raise ValueError('unsafe native package')
  doc=ET.fromstring(z.read('word/document.xml'))
  if any(node.tag.rsplit('}',1)[-1] in {'txbxContent','textFill','textOutline','textpath'} for node in doc.iter()):raise ProfileUnsupported('textbox/transparent text effects outside native table visibility profile')
  records=[]
  for table in doc.findall('.//w:tbl',N):
   rows=table.findall('w:tr',N)
   if not rows:continue
   header=[text(c).strip() for c in rows[0].findall('w:tc',N)]
   if header!=['plan_id','decision','reason_code','modules']:continue
   for row in rows[1:]:
    cells=row.findall('w:tc',N)
    if len(cells)!=4:continue
    for cell in cells:
     for run in cell.findall('.//w:r',N):
      color=run.find('w:rPr/w:color',N)
      if color is not None and color.attrib.get('{'+N['w']+'}val','').upper() in ('FFFFFF','FFFFFFFF'):raise ProfileUnsupported('white/transparent decision fields outside supported visibility profile')
    values=[text(c).strip() for c in cells]
    records.append(dict(zip(header,values)))
  paragraphs=[text(p) for p in doc.findall('.//w:p',N)];plain='\n'.join(paragraphs)
  def one(name):
   values=re.findall(r'(?m)^'+re.escape(name)+r'\s*=\s*([A-Fa-f0-9]{64}|false)\s*$',plain,flags=re.I)
   return values[0] if len(values)==1 else None
  return {'plans':records,'source_digest':one('source_digest'),'regression_sha256':one('regression_sha256'),'real_Harness':one('real_Harness'),'real_spreadsheet_app':one('real_spreadsheet_app'),'native_text_present':bool(plain.strip()),'semantic_quality_assessed':False}
