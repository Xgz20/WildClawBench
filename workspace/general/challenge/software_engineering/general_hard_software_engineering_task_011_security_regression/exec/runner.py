"""Actual captured module calls and CSV parse; no OS sandbox or spreadsheet-app claim."""
from pathlib import Path
import ast,copy,csv,decimal,hashlib,importlib,io,json,re,sys
EDITABLE=('project/authorization.py','project/exporter.py','project/routes.py')
class Unsupported(RuntimeError):pass
def profile(root):
 allowed={'csv','io','decimal','copy','json','re','hashlib','typing','__future__','project','project.authorization','project.exporter','project.health'}
 for rel in EDITABLE:
  try:tree=ast.parse((root/rel).read_text(encoding='utf-8-sig'))
  except SyntaxError:continue
  for node in ast.walk(tree):
   if isinstance(node,ast.Import) and any(x.name not in allowed for x in node.names):raise Unsupported('Python import outside declared profile')
   if isinstance(node,ast.ImportFrom) and not node.level and node.module not in allowed:raise Unsupported('Python from-import outside declared profile')
   if isinstance(node,(ast.Global,ast.Nonlocal)):raise Unsupported('global/nonlocal cache outside profile')
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'open','exec','eval','compile','__import__'}:raise Unsupported('IO/dynamic execution outside profile')
  for top in tree.body:
   if isinstance(top,(ast.Assign,ast.AnnAssign)):
    try:v=ast.literal_eval(top.value)
    except Exception:raise Unsupported('dynamic module cache outside profile')
    if isinstance(v,(dict,list,set)):raise Unsupported('mutable module cache outside profile')

def normalize(response):
 status=response['status'];headers={str(k).lower():v for k,v in response['headers'].items()};body=response['body']
 if status>=400:return {'status':status,'kind':'error','body':body,'headers':headers}
 content=str(headers.get('content-type','')).split(';')[0].strip().lower()
 if content!='text/csv':return {'status':status,'kind':'json','body':body,'headers':headers}
 if not isinstance(body,str):raise ValueError('CSV body must be native JSON string')
 text=body[1:] if body.startswith('\ufeff') else body
 rows=list(csv.reader(io.StringIO(text,newline='')))
 if not rows:raise ValueError('CSV missing header')
 columns=rows[0]
 for values in rows[1:]:
  if len(values)!=len(columns):raise ValueError('CSV row width mismatch')
  for i,column in enumerate(columns):
   if column=='amount':
    if not re.fullmatch(r'[+-]?[0-9]+\.[0-9]{2}',values[i]):raise ValueError('amount not fixed2 numeric')
    d=decimal.Decimal(values[i]);values[i]='0.00' if not d else format(d,'.2f')
 return {'status':status,'kind':'csv','columns':columns,'rows':rows[1:]}
def public(state):return {'actors':copy.deepcopy(state['actors']),'records':copy.deepcopy(state['records']),'permissions':copy.deepcopy(state['permissions']),'job_ids':sorted(state['jobs'])}
def equal(a,b):
 if isinstance(b,bool) or b is None:return type(a)==type(b) and a==b
 if isinstance(b,(int,float)):return isinstance(a,(int,float)) and not isinstance(a,bool) and a==b
 if isinstance(b,dict):return isinstance(a,dict) and all(k in a and equal(a[k],v) for k,v in b.items())
 if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 return type(a)==type(b) and a==b

def replay(root,cases):
 profile(root);sys.path.insert(0,str(root));out=[]
 for case in cases:
  for name in list(sys.modules):
   if name=='project' or name.startswith('project.'):del sys.modules[name]
  state=copy.deepcopy(case['state']);trace=[];row={'case_id':case['case_id'],'status':'completed'}
  try:
   handle=importlib.import_module('project.routes').handle
   for step in case['steps']:
    response=None;normalized=None;unchanged=True
    if step['op']=='actor':state['actors'][step['id']].update(step['patch'])
    elif step['op']=='record':next(r for r in state['records'] if r['id']==step['id']).update(step['patch'])
    elif step['op']=='permission':state['permissions'][step['role']].update(step['patch'])
    else:
     params=copy.deepcopy(step.get('params',{}));before=copy.deepcopy([state,params])
     response,new_state=handle(state,step['actor'],step['method'],step['path'],params)
     unchanged=before==[state,params];state=new_state;normalized=normalize(response)
    trace.append({'response':response,'normalized_response':normalized,'public_state':public(state),'inputs_unchanged':unchanged})
   row['trace']=trace
  except Unsupported:raise
  except Exception as exc:row.update(status='candidate_error',error=type(exc).__name__+': '+str(exc),trace=trace)
  out.append(row)
 hashes={rel:hashlib.sha256((root/rel).read_bytes()).hexdigest() for rel in EDITABLE};digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return {'schema_version':'h051-actual-calls/v1','source_sha256':hashes,'source_digest':digest,'cases':out,'scope':'Actual Python service/module state calls and CSV parsing, not HTTP/browser/spreadsheet/Harness/OS sandbox.'}
if __name__=='__main__':
 request=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2])
 try:result=replay(Path(request['root']),request['cases'])
 except Unsupported as exc:result={'unassessed':True,'error':str(exc),'candidate_zero':False}
 out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
