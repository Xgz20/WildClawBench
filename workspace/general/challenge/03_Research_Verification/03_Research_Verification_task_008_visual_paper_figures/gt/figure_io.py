"""Read native logical records; no source truth or reference layout in this module."""
from pathlib import Path
import json,math,re,runpy,unicodedata
BASE=runpy.run_path(str(Path(__file__).with_name('native_base.py')))
CandidateError=BASE['CandidateError'];TrustedEvidenceError=BASE['TrustedEvidenceError']
read_book=BASE['read_book'];read_docx=BASE['read_docx'];sha=BASE['sha'];mean=BASE['mean']
class SemanticReviewRequired(TrustedEvidenceError):pass
def text(v):return unicodedata.normalize('NFKC',str('' if v is None else v)).strip()
def norm(v):return re.sub(r'[\s_\-()（）:：/]+','',text(v)).casefold()
ALIASES={
 'claim_id':['编号','论述','论述编号','原论述','claim','claim id','id'],
 'claim':['待核论述','原命题','主张','claim text'],
 'target':['实际判断对象','判断对象','assessment target','target'],
 'verdict':['判定','判断','结论','verdict','decision','assessment'],
 'values':['图形读数与单位','读数','实际读数','values','readout','observations'],
 'axes':['坐标尺度和图例绑定','轴与图例','轴尺度','axes','axis legend','scale'],
 'method':['方法段','节选','method','text reference'],
 'region_refs':['局部定位编号','区域编号','source regions','region refs','regions'],
 'limits':['解释与限制','限制','理由','说明','rationale','limitations','reason'],
 'point_id':['读数对象','point id','reading id','readout object'],
 'figure':['图号','figure','figure id'], 'series':['方法或组别','方法或组','series','method or group'],
 'x':['设置值','设置','x','setting'], 'x_unit':['设置单位','x unit'],
 'value':['图示约值','约值','值','value','mean','observed value'],
 'low':['可读下界','读数下界','lower','low','readable lower'],
 'high':['可读上界','读数上界','upper','high','readable upper'],
 'unit':['读数单位','单位','unit'],
 'sd_low_low':['SD下端读数下界','sd lower low'], 'sd_low_high':['SD下端读数上界','sd lower high'],
 'sd_high_low':['SD上端读数下界','sd upper low'], 'sd_high_high':['SD上端读数上界','sd upper high'],
 'region_id':['定位编号','定位','region id','evidence id'],
 'file':['原始图源','原始图像','源图','source file','file','image'],
 'object':['具体对象','对象','object','evidence object'], 'kind':['证据类型','类型','kind','type'],
 'x1':['x1','x0','left'], 'y1':['y1','y0','top'], 'x2':['x2','right'], 'y2':['y2','bottom'],
 'geometry':['定位说明或点框集合','局部像素框或点框集合','像素框','bbox','geometry','coordinates','point boxes'],
 'field':['字段','属性','field','attribute'],
}
HEAD={norm(v):k for k,vs in ALIASES.items() for v in [k,*vs]}
def identity(v,prefix='C'):
 m=re.fullmatch(prefix+r'0*(\d+)',text(v),re.I)
 return prefix+f'{int(m[1]):02}' if m else None
def point_id(v):
 m=re.fullmatch(r'F0*([1-4])[-_\s]+(A|B|G1|G2)(?:[-_\s]+(\d+))?',text(v),re.I)
 return f'F{int(m[1]):02}-{m[2].upper()}'+('-'+str(int(m[3])) if m[3] else '') if m else None
def number(v):
 if isinstance(v,bool) or v is None:return None
 try:n=float(text(v).rstrip('%').replace(',',''));return n if math.isfinite(n) else None
 except ValueError:return None
def filename(v):
 n=text(v).replace('\\','/').split('/')[-1]
 return 'figures/'+n if re.fullmatch(r'F0[1-4]_[a-z]+\.png',n,re.I) else None
def scan(book):
 out={'claims':{},'points':{},'regions':{},'headers':[],'native_rows':[]}
 for sh in book:
  for transpose in [False,True]:
   grid={(c,r) if transpose else (r,c):v for (r,c),v in sh['cells'].items() if v['visible']}
   active={};header=None
   for row in sorted({r for r,c in grid}):
    cells={c:v for (r,c),v in grid.items() if r==row};mapping={}
    for col,cell in cells.items():
     key=HEAD.get(norm(cell['value']))
     if key:mapping.setdefault(key,[]).append(col)
    if len(mapping)>=2 and (any(k in mapping for k in ['claim_id','point_id','region_id']) or all(k in mapping for k in ['figure','series']) and any(k in mapping for k in ['value','low','high'])):
     active={k:cs[0] for k,cs in mapping.items() if len(cs)==1};header=row
     out['headers'].append({'sheet':sh['name'],'row':row,'transposed':transpose,'mapping':active});continue
    if not active:continue
    record={k:cells[c]['value'] for k,c in active.items() if c in cells and cells[c]['value'] not in [None,'']}
    if 'field'in record and 'value'in record:
     canonical=HEAD.get(norm(record['field']))
     if canonical:record[canonical]=record['value']
    loc={'sheet':sh['name'],'row':row,'header':header,'transposed':transpose}
    for fld,kind,func in [('claim_id','claims',identity),('point_id','points',point_id),('region_id','regions',lambda v:text(v))]:
     ident=func(record.get(fld,''))
     if kind=='points' and not ident and all(k in record for k in ['figure','series']):
      fm=re.search(r'F?0*([1-4])',text(record['figure']),re.I);sm=re.search(r'(G[12]|[AB])$',text(record['series']),re.I);setting=number(record.get('x'))
      if fm and sm and (fm[1]=='2' or setting is not None and setting.is_integer()):ident=f'F{int(fm[1]):02}-{sm[1].upper()}'+('' if fm[1]=='2' else '-'+str(int(setting)))
     if ident and (kind!='regions' or any(k in record for k in ['geometry','x1'])):
      item={'record':record,'location':loc,'cells':{k:cells[c] for k,c in active.items() if c in cells}};out[kind].setdefault(ident,[]).append(item);out['native_rows'].append(item)
 return out
def verdict(v):
 s=norm(v)
 groups={'supported':['支持','supported','成立','与图一致','图形支持','有证据支持','描述成立'],
 'refuted':['反驳','refuted','不成立','与图不符','推论无效','不能成立','图形反证','否定该推论'],
 'insufficient':['证据不足','insufficient','unknown','未知','无法判断','尚不能确定','未报告','未测量','未证实']}
 for k,vs in groups.items():
  if s in {norm(x) for x in vs}:return k
 # An open prose route is not rejected as a wrong label. Unhandled semantics
 # requires independent review; this must never silently become0 or1.
 return None
def collect_claim(rows):
 if not rows:return None
 combined={};orig=[]
 for row in rows:
  r=row['record'];orig.append(row['location'])
  for k,v in r.items():
   if k not in combined:combined[k]=v
   elif text(v)!=text(combined[k]):combined[k]=text(combined[k])+'\n'+text(v)
 combined['_locations']=orig
 return combined
def region_geometry(record):
 raw=record.get('geometry',record.get('region_refs',''));shapes=[]
 def add(vals,kind='bbox',mode=None):
  vals=[number(n) for n in vals]
  if any(n is None for n in vals):return
  if kind=='point':
   if max(abs(n) for n in vals)<=1 and mode!='pixel':vals=[vals[0]*1800,vals[1]*1260]
   vals=[vals[0]-8,vals[1]-8,vals[0]+8,vals[1]+8]
  if len(vals)!=4:return
  if max(abs(n) for n in vals)<=1 and mode!='pixel':vals=[vals[0]*1800,vals[1]*1260,vals[2]*1800,vals[3]*1260]
  if 0<=vals[0]<vals[2]<=1800 and 0<=vals[1]<vals[3]<=1260:shapes.append(vals)
 def walk(obj,mode=None):
  if isinstance(obj,dict):
   mode=obj.get('coordinate_system',obj.get('coordinates',mode))
   if 'xywh'in obj:
    a=obj['xywh'];add([a[0],a[1],a[0]+a[2],a[1]+a[3]],mode=mode)
   elif 'point'in obj:add(obj['point'],'point',mode)
   elif 'polygon'in obj:
    pts=obj['polygon']
    if len(pts)>=3 and all(len(p)==2 and all(number(n) is not None for n in p) for p in pts):
     pts=[[float(n) for n in p] for p in pts]
     if max(abs(n) for p in pts for n in p)<=1 and mode!='pixel':pts=[[p[0]*1800,p[1]*1260] for p in pts]
     bb=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]
     if 0<=bb[0]<bb[2]<=1800 and 0<=bb[1]<bb[3]<=1260:shapes.append({'bbox':bb,'polygon':pts})
   else:
    for k in ['bbox','boxes','regions','point_bboxes_xyxy_px']:
     if k in obj:walk(obj[k],mode)
  elif isinstance(obj,list):
   if len(obj)==4 and all(number(n) is not None for n in obj):add(obj,mode=mode)
   else:
    for n in obj:walk(n,mode)
 if all(k in record for k in ['x1','y1','x2','y2']):add([record[k] for k in ['x1','y1','x2','y2']])
 if isinstance(raw,(list,dict)):walk(raw)
 else:
  try:walk(json.loads(text(raw)))
  except ValueError:
   for group in re.findall(r'[\[(]\s*([-+\d.,\s]+)\s*[\])]',text(raw)):
    nums=[number(n) for n in group.split(',')]
    if len(nums)==4 and all(n is not None for n in nums):add(nums)
 return shapes
def hit(boxes,target):
 tx=(target[0]+target[2])/2;ty=(target[1]+target[3])/2
 area=(target[2]-target[0])*(target[3]-target[1]);small=target[2]-target[0]<=50 and target[3]-target[1]<=50
 def overlap(bb):return max(0,min(bb[2],target[2])-max(bb[0],target[0]))*max(0,min(bb[3],target[3])-max(bb[1],target[1]))
 def accepts(shape):
  bb=shape['bbox'] if isinstance(shape,dict) else shape
  if isinstance(shape,dict):
   pts=shape['polygon'];inside=False
   for a,b in zip(pts,pts[1:]+pts[:1]):
    if (a[1]>ty)!=(b[1]>ty) and tx<(b[0]-a[0])*(ty-a[1])/(b[1]-a[1])+a[0]:inside=not inside
   if not inside:return False
  return (bb[2]-bb[0])*(bb[3]-bb[1])<.8*1800*1260 and bb[0]<=tx<=bb[2] and bb[1]<=ty<=bb[3] and (small or overlap(bb)>=.2*area)
 return any(accepts(bb) for bb in boxes)
def normalized_number(row,field,want_unit):
 r=row['record'];v=number(r.get(field));unit=norm(r.get('unit'))
 if v is None:return None
 if want_unit=='ms':factor={'ms':1.,'毫秒':1.,'s':1000.,'seconds':1000.,'秒':1000.}.get(unit)
 else:
  factor=1. if unit in {'%','percent','百分比','百分点'} else 100. if unit in {'fraction','比例','ratio','0–1','01'} else None
  cell=row.get('cells',{}).get(field,{})
  if not unit and (text(r.get(field)).endswith('%') or '%'in cell.get('number_format','')):factor=1. if text(r.get(field)).endswith('%') else 100.
  if factor==1. and '%' in cell.get('number_format','') and not text(r.get(field)).endswith('%'):factor=100.
 return v*factor if factor is not None else None
def bounds(row,want_unit):
 r=row['record'];lo=normalized_number(row,'low' if 'low'in r else 'value',want_unit);hi=normalized_number(row,'high' if 'high'in r else 'value',want_unit)
 return (lo,hi) if lo is not None and hi is not None else None

def inline_points(claims):
 """Read explicit role-linked native prose, without answer numbers/cell maps.

 This is deliberately bounded extraction. Unknown legal syntax is deferred by
 the caller; neither OCR nor the claim's quoted question is used as an answer.
 """
 out={}
 def emit(pid,record,owner):
  out.setdefault(pid,[]).append({'record':record,'cells':{},'location':{'native_claim':owner,'source_locations':claims[owner].get('_locations',[]),'representation':'explicit inline role-linked readout'}})
 for owner,fig,x in [('C01','F01',10),('C03','F02',None),('C05','F03',8)]:
  row=claims.get(owner)
  if not row:continue
  value=text(row.get('values'));labels=list(re.finditer(r'(?<![A-Za-z/])(?:Method\s*)?([AB])(?![A-Za-z/])',value,re.I))
  for i,m in enumerate(labels):
   segment=value[m.end():labels[i+1].start() if i+1<len(labels) else len(value)]
   first=re.search(r'^[^0-9]{0,60}([0-9]+(?:\.[0-9]+)?)\s*(%|ms|s|毫秒|秒)?',segment,re.I)
   if not first:continue
   unit=first[2] or text(row.get('unit'))
   if not unit and fig!='F03' and ('%'in value or '百分比'in text(row.get('axes'))):unit='%'
   record={'series':'Method '+m[1].upper(),'x':x,'value':float(first[1]),'unit':unit}
   readable=re.search(r'(?:可读|readable)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(?:%|ms|s|毫秒|秒)?\s*(?:[~～–—-]|至|to)\s*([0-9]+(?:\.[0-9]+)?)',segment,re.I)
   if readable:record.update(low=float(readable[1]),high=float(readable[2]))
   if fig=='F02':
    sd=re.search(r'(?:SD|标准差|范围)[^0-9]{0,16}([0-9]+(?:\.[0-9]+)?)\s*%?\s*(?:[~～–—-]|至|to)\s*([0-9]+(?:\.[0-9]+)?)',segment,re.I)
    if sd:record.update(sd_low_low=float(sd[1]),sd_low_high=float(sd[1]),sd_high_low=float(sd[2]),sd_high_high=float(sd[2]))
   emit(fig+'-'+m[1].upper()+('' if x is None else '-'+str(x)),record,owner)
 for owner in ['C07','C08']:
  row=claims.get(owner)
  if not row:continue
  value=text(row.get('values'));groups=list(re.finditer(r'(?<![A-Za-z])G([12])(?![A-Za-z0-9])',value,re.I))
  for i,m in enumerate(groups):
   segment=value[m.end():groups[i+1].start() if i+1<len(groups) else len(value)];group='G'+m[1]
   pairs=list(re.finditer(r'[（(]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:步|steps?)?\s*[,，]\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*[)）]',segment,re.I))
   for p in pairs:
    xx=float(p[1])
    if xx.is_integer():emit('F04-'+group+'-'+str(int(xx)),{'series':'Group '+group,'x':xx,'value':float(p[2]),'unit':'%'},owner)
   if not pairs:
    ns=re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*%',segment)
    if len(ns)==2:
     for xx,yy in zip([1,5] if group=='G1' else [8,12],ns):emit('F04-'+group+'-'+str(xx),{'series':'Group '+group,'x':xx,'value':float(yy),'unit':'%'},owner)
 return out
