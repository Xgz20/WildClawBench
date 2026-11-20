"""Trusted actual HTTP + SQLite + JS controller replay, not an OS security sandbox."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import ast,hashlib,json,os,shutil,sqlite3,subprocess,sys,threading,time,urllib.request,urllib.error
EDITABLE=('project/api.py','project/service.py','project/repository.py','project/client.mjs')
class Unsupported(RuntimeError):pass
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_digest(hashes):return hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def equal(a,b):
 if isinstance(b,bool) or b is None:return type(a)==type(b) and a==b
 if isinstance(b,(int,float)):return isinstance(a,(int,float)) and not isinstance(a,bool) and a==b
 if isinstance(b,dict):return isinstance(a,dict) and all(k in a and equal(a[k],v) for k,v in b.items())
 if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 return type(a)==type(b) and a==b

def satisfies(case,actual,wanted):
 if actual.get('status')!='completed':return False
 value=actual.get('output');requirement=case['requirement']
 if case['kind']=='client':
  if not isinstance(value,dict):return False
  left={k:v for k,v in value.items() if k!='db'};right={k:v for k,v in wanted.items() if k!='db'}
  return equal(left,right) and equal(value.get('db',{}).get('members'),wanted['db']['members']) and len(value.get('db',{}).get('audit',[]))<=len(wanted['db']['audit'])
 for variant in wanted['variants']:
  if not isinstance(value,list) or len(value)!=len(variant):continue
  okay=True
  for step,got,expected in zip(case['steps'],value,variant):
   keys=('members','schema_version') if requirement=='R01' else ('responses',) if requirement=='R02' else ('responses','members','audit') if requirement=='R09' else ('responses','members')
   projected_got=dict(got);projected_expected=dict(expected)
   if requirement!='R09' and step.get('op')=='request' and step.get('method')=='GET' and step.get('path')=='/audit' and expected['responses'] and expected['responses'][0]['status']<400:
    for projected in (projected_got,projected_expected):
     projected['responses']=[dict(response,body=dict(response['body'],data=None)) for response in projected['responses']]
   if not all(key in projected_got and equal(projected_got[key],projected_expected[key]) for key in keys):okay=False;break
   # Positive audit completeness/content belongs to R09. Other requirements
   # still reject added writes on denial/read/replay without charging a missing
   # positive audit to every successful business transaction.
   if requirement!='R09' and len(got.get('audit',[]))>len(expected['audit']):okay=False;break
  if okay:return True
 return False

def profile(root):
 allowed={'sqlite3','json','hashlib','re','copy','contextlib','unicodedata','collections','functools','typing','urllib.parse','__future__','project','project.repository','project.service','project.legacy'}
 for rel in EDITABLE:
  if not rel.endswith('.py'):continue
  try:tree=ast.parse((root/rel).read_text(encoding='utf-8-sig'))
  except SyntaxError:continue # Actual candidate syntax/startup failure is capability evidence.
  for node in ast.walk(tree):
   if isinstance(node,ast.Import) and any(a.name not in allowed for a in node.names):raise Unsupported('candidate Python import outside declared profile')
   if isinstance(node,ast.ImportFrom) and not node.level and node.module not in allowed:raise Unsupported('candidate Python from-import outside declared profile')
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'eval','exec','compile','__import__','open'}:raise Unsupported('dynamic execution or nonSQLite IO outside profile')

def db_snapshot(path):
 db=sqlite3.connect(path)
 try:
  keys=('id','email','name','role','status','version');members=[dict(zip(keys,r)) for r in db.execute('SELECT id,email,name,role,status,version FROM members ORDER BY id')]
  exists=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit'").fetchone()
  keys=('seq','actor','action','target','before_version','after_version','request_key')
  audit=[dict(zip(keys,r)) for r in db.execute('SELECT seq,actor,action,target,before_version,after_version,request_key FROM audit ORDER BY seq')] if exists else []
  return {'members':members,'audit':audit,'schema_version':db.execute('PRAGMA user_version').fetchone()[0]}
 finally:db.close()

class Markup(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.rows=[];self.current=None;self.cell=None;self.depth=0;self.buttons={};self.create=None;self.error=None;self.in_error=False;self.script=0
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='script':self.script+=1
  if tag=='tr' and 'data-id' in a:self.current={'id':a['data-id'],'cells':[],'buttons':{}};self.rows.append(self.current)
  if tag=='td' and self.current is not None:self.cell=''
  if tag=='button' and 'data-action' in a:
   enabled='disabled' not in a
   if a['data-action']=='create':self.create=enabled
   elif self.current is not None:self.current['buttons'][a['data-action']]=enabled
  if 'data-error' in a:self.in_error=True;self.error=''
 def handle_endtag(self,tag):
  if tag=='td' and self.current is not None and self.cell is not None:self.current['cells'].append(self.cell.strip());self.cell=None
  if tag=='tr':self.current=None
  if tag in ('p','div','span') and self.in_error:self.in_error=False
 def handle_data(self,data):
  if self.cell is not None:self.cell+=data
  if self.in_error:self.error+=data
 def semantic(self):return {'rows':self.rows,'create':self.create,'error':self.error or None,'script_tags':self.script}

class Server:
 def __init__(self,folder,db,python):self.folder,self.db,self.python,self.process=folder,db,python,None;self.index=0
 def start(self):
  self.index+=1;self.ready=self.folder/('ready-'+str(self.index)+'.json');self.stdout=(self.folder/('server-'+str(self.index)+'.stdout.log')).open('w');self.stderr=(self.folder/('server-'+str(self.index)+'.stderr.log')).open('w')
  command=[self.python,'-I','-B','-X','utf8',str(self.folder/'app.py'),'--db',str(self.db),'--port','0','--ready-file',str(self.ready)]
  self.process=subprocess.Popen(command,cwd=self.folder/'unrelated-cwd',stdout=self.stdout,stderr=self.stderr,env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','PYTHONUTF8'}})
  (self.folder/('server-'+str(self.index)+'.invocation.json')).write_text(json.dumps({'argv':command,'cwd':str(self.folder/'unrelated-cwd'),'loopback_only':True,'pid':self.process.pid},indent=2)+'\n')
  deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   if self.ready.is_file():self.base='http://127.0.0.1:'+str(read(self.ready)['port']);return True
   if self.process.poll() is not None:return False
   time.sleep(.01)
  raise Unsupported('server readiness protection deadline, unassessed')
 def stop(self):
  if self.process and self.process.poll() is None:
   self.process.terminate()
   try:self.process.wait(timeout=3)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
  if self.process:
   self.stdout.close();self.stderr.close()
   (self.folder/('server-'+str(self.index)+'.cleanup.json')).write_text(json.dumps({'pid':self.process.pid,'returncode':self.process.returncode,'terminated':self.process.poll() is not None})+'\n')
 def request(self,step):
  body=step.get('body',{});method=step['method'];url=self.base+step['path']
  request=urllib.request.Request(url,data=None if method=='GET' else json.dumps(body).encode(),method=method,headers={'Content-Type':'application/json','X-Actor':step.get('actor','m-admin')})
  try:
   with urllib.request.urlopen(request,timeout=8) as r:return {'status':r.status,'body':json.loads(r.read())}
  except urllib.error.HTTPError as exc:return {'status':exc.code,'body':json.loads(exc.read())}
  except (TimeoutError,ConnectionError,OSError) as exc:raise Unsupported('local HTTP transport infrastructure: '+str(exc)) from exc

def replay(request,response_path):
 root=Path(request['candidate_root']);trusted=Path(request['trusted_root']);work=Path(request['work_root']);work.mkdir(parents=True,exist_ok=False)
 runtime=read(trusted/'runtime.json');node=Path(runtime['node']['path'])
 if not node.is_file() or sha(node)!=runtime['node']['sha256']:raise Unsupported('frozen Node unavailable or drift')
 profile(root);hashes={p:sha(root/p) for p in EDITABLE}
 result={'schema_version':'h052-actual-replay/v1','source_sha256':hashes,'source_digest':source_digest(hashes),'runtime':{'python':sys.version.split()[0],'node':runtime['node']},'scope':'actual localhost HTTP/SQLite + JS controller/HTML semantics; no browser/Harness/OS sandbox claim','cases':[]}
 for case in request['cases']:
  folder=work/case['case_id'];folder.mkdir();(folder/'unrelated-cwd').mkdir()
  shutil.copytree(trusted/'project',folder/'project');(folder/'fixtures').mkdir();shutil.copy2(trusted/'fixtures/seed.json',folder/'fixtures/seed.json')
  for p in ('app.py','index.html'):shutil.copy2(trusted/p,folder/p)
  for rel in EDITABLE:shutil.copy2(root/rel,folder/rel)
  db=folder/'state.sqlite';conn=sqlite3.connect(db);conn.execute('CREATE TABLE members(id TEXT PRIMARY KEY,email TEXT,name TEXT,role TEXT,status TEXT,version INTEGER)')
  for row in case['seed']:conn.execute('INSERT INTO members VALUES(:id,:email,:name,:role,:status,:version)',row)
  conn.commit();conn.close();server=Server(folder,db,sys.executable);row={'case_id':case['case_id'],'status':'completed'}
  try:
   if not server.start():row.update(status='candidate_startup_error');result['cases'].append(row);continue
   if case['kind']=='backend':
    observations=[]
    for step in case['steps']:
     responses=[]
     if step['op']=='request':responses=[server.request(step)]
     elif step['op']=='restart':server.stop();assert server.start()
     elif step['op']=='parallel':
      barrier=threading.Barrier(len(step['requests']))
      def one(q):barrier.wait(timeout=5);return server.request(q)
      with ThreadPoolExecutor(max_workers=len(step['requests'])) as pool:responses=list(pool.map(one,step['requests']))
     elif step['op']=='audit_failure':
      conn=sqlite3.connect(db)
      if step['enabled']:conn.execute("CREATE TRIGGER h052_injected_audit_failure BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'controlled audit fault'); END")
      else:conn.execute('DROP TRIGGER h052_injected_audit_failure')
      conn.commit();conn.close()
     observations.append(dict(responses=responses,**db_snapshot(db)))
    row['output']=observations
   else:
    query=folder/'client-request.json';response=folder/'client-response.json';query.write_text(json.dumps({'steps':case['steps'],'actor':case['actor'],'base_url':server.base}))
    command=[str(node),'--experimental-vm-modules','--disable-warning=ExperimentalWarning',str(trusted/'client_runner.mjs'),str(folder/'project/client.mjs'),str(query),str(response)]
    r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
    (folder/'client-invocation.json').write_text(json.dumps({'argv':command,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n')
    if r.returncode or not response.is_file():raise Unsupported('trusted client process failure')
    actual=read(response)
    if actual['status']=='unassessed':raise Unsupported(actual.get('error','client profile unsupported'))
    if actual['status']!='completed':row.update(status='candidate_error',error=actual.get('error'));result['cases'].append(row);continue
    for observed in actual['observations']:
     parser=Markup();parser.feed(observed.pop('html'));observed['semantic']=parser.semantic()
    row['output']={'observations':actual['observations'],'requests':actual['requests'],'db':db_snapshot(db),'all_inflight_loading':actual['all_inflight_loading'] and not actual.get('snapshot_alias',False)}
  except Unsupported:raise
  except Exception as exc:row.update(status='candidate_error',error=type(exc).__name__+': '+str(exc))
  finally:server.stop()
  result['cases'].append(row)
 response_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 return result

if __name__=='__main__':
 request_path=Path(sys.argv[1]);response_path=Path(sys.argv[2])
 try:replay(read(request_path),response_path)
 except Unsupported as exc:response_path.write_text(json.dumps({'unassessed':True,'error':str(exc),'candidate_zero':False})+'\n')
