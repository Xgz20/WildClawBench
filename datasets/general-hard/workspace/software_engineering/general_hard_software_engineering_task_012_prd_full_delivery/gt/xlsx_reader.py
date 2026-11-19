"""Native OOXML cell reader; no calculation claims or third-party Worker dependency."""
from pathlib import PurePosixPath
import posixpath,zipfile,xml.etree.ElementTree as ET
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
class ProfileUnsupported(RuntimeError):pass
def load(path):
 with zipfile.ZipFile(path) as z:
  info=z.infolist()
  if len(info)>1000 or sum(x.file_size for x in info)>10*1024*1024:raise ProfileUnsupported('workbook package beyond declared 1000-member/10MiB reader profile')
  names={x.filename for x in info}
  if not {'[Content_Types].xml','xl/workbook.xml','xl/_rels/workbook.xml.rels'}<=names:raise ValueError('not native XLSX')
  for x in info:
   if x.filename.startswith('/') or '..' in PurePosixPath(x.filename).parts:raise ValueError('unsafe workbook member')
  strings=[]
  if 'xl/sharedStrings.xml' in names:
   strings=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
  relations={x.attrib['Id']:x.attrib['Target'] for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
  sheets=[]
  for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
   if sheet.attrib.get('state','visible')!='visible':continue
   target=relations[sheet.attrib['{'+NS['r']+'}id']]
   target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
   tree=ET.fromstring(z.read(target));cells={};hidden=set()
   for row in tree.findall('s:sheetData/s:row',NS):
    number=int(row.attrib['r'])
    if row.attrib.get('hidden')=='1' or row.attrib.get('ht') in ('0','0.0'):hidden.add(number)
    for cell in row.findall('s:c',NS):
     kind=cell.attrib.get('t');value=cell.find('s:v',NS)
     if kind=='inlineStr':v=''.join(cell.find('s:is',NS).itertext())
     elif kind=='s':v=strings[int(value.text)] if value is not None else ''
     else:v=value.text if value is not None else ''
     cells[cell.attrib['r']]=v
   hidden_columns=any(x.attrib.get('hidden')=='1' and int(x.attrib['min'])<=5 for x in tree.findall('s:cols/s:col',NS))
   headers=[cells.get(chr(65+i)+'6') for i in range(5)]
   if headers==['id','priority','implementation_paths','test_ids','status'] and 6 not in hidden and not hidden_columns:
    rows=[]
    for number in sorted({int(k.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')) for k in cells if k[0] in 'ABCDE' and int(k.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))>=7}):
     if number in hidden:continue
     rows.append({'id':cells.get('A'+str(number)), 'priority':cells.get('B'+str(number)), 'implementation_paths':cells.get('C'+str(number)), 'test_ids':cells.get('D'+str(number)), 'status':cells.get('E'+str(number))})
    sheets.append({'sheet':sheet.attrib['name'],'source_digest':cells.get('B2'),'tests_sha256':cells.get('B3'),'rows':rows})
  if len(sheets)!=1:raise ValueError('require exactly one visible native trace table with declared headers')
  return sheets[0]
