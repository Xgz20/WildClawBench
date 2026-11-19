"""Offline browser observations on original HTML and bounded public resources.

This standalone helper may be copied with html_observer.mjs into frozen GT.
Observations expose actual DOM/SVG/Canvas and pixels, not business verdicts.
"""
from __future__ import annotations
import hashlib,json,mimetypes,os,platform,re,shutil,signal,subprocess,tempfile,math
from pathlib import Path

LOCK_SCHEMA='wildclawbench.html-runtime-lock/v1'
AUDIT_SCHEMA='wildclawbench.html-observation-audit/v1'
OBSERVATION_SCHEMA='wildclawbench.html-observation/v1'
PROFILE='offline-html-dom-svg-canvas-observation/v1'
ORIGIN='http://html-evidence.invalid'
MAX_HTML_BYTES=5*1024*1024
MAX_RESOURCE_BYTES=64*1024*1024
MAX_OBSERVATION_BYTES=32*1024*1024
SETTINGS={'viewport':{'width':1280,'height':960},'device_scale_factor':1,'locale':'zh-CN','timezone':'Asia/Shanghai','color_scheme':'light','reduced_motion':'reduce','max_height':20000,'max_shapes':4000,'max_canvas_paints':10000,'max_text_fragments':30000,'quiet_ms':250,'settle_timeout_ms':8000}
class HtmlRuntimeError(RuntimeError):
    def __init__(self,code,message):self.code,self.message=code,message;super().__init__(code+': '+message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def _file(path,code):
    p=Path(path)
    if p.is_symlink() or not p.is_file():raise HtmlRuntimeError(code,'regular file required')
    return p.resolve()
def _env(temporary=None):
    env={k:v for k,v in os.environ.items() if k in {'SYSTEMROOT','WINDIR','COMSPEC','LANG','LC_ALL'}}
    if temporary is not None:env.update(TMPDIR=str(temporary),TMP=str(temporary),TEMP=str(temporary))
    return env
def _probe(command):
    try:r=subprocess.run(command,capture_output=True,text=True,env=_env(),timeout=20)
    except (OSError,subprocess.TimeoutExpired) as e:raise HtmlRuntimeError('HTML_RUNTIME_UNAVAILABLE',str(e)) from e
    if r.returncode:raise HtmlRuntimeError('HTML_RUNTIME_UNAVAILABLE',r.stderr[-1000:])
    return r.stdout.strip()
def _tree(root):
    root=Path(root).resolve();rows=[]
    if not root.is_dir():raise HtmlRuntimeError('HTML_LIBRARY_UNAVAILABLE','Playwright core directory missing')
    size=0
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise HtmlRuntimeError('HTML_LIBRARY_UNSUPPORTED','library symlink requires another asset profile')
        if not p.is_file():continue
        size+=p.stat().st_size
        if len(rows)>=10000 or size>256*1024*1024:raise HtmlRuntimeError('HTML_LIBRARY_UNSUPPORTED','library asset limit')
        rows.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':sha(p)})
    return rows
def create_html_lock(node_executable,playwright_core_root,browser_executable,*,font_files=()):
    node=_file(node_executable,'HTML_NODE_UNAVAILABLE');browser=_file(browser_executable,'HTML_BROWSER_UNAVAILABLE');root=Path(playwright_core_root).resolve();assets=_tree(root);observer=Path(__file__).with_name('html_observer.mjs')
    try:package=json.loads((root/'package.json').read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError) as exc:raise HtmlRuntimeError('HTML_LIBRARY_UNSUPPORTED','playwright-core package required') from exc
    if not isinstance(package,dict) or package.get('name')!='playwright-core' or not isinstance(package.get('version'),str):raise HtmlRuntimeError('HTML_LIBRARY_UNSUPPORTED','playwright-core package required')
    fonts=[]
    for p in font_files:
        p=_file(p,'HTML_FONT_UNAVAILABLE');fonts.append({'path':str(p),'size':p.stat().st_size,'sha256':sha(p)})
    lock={'schema_version':LOCK_SCHEMA,'profile':PROFILE,'node':{'executable':str(node),'sha256':sha(node),'version':_probe([str(node),'--version'])},'browser':{'executable':str(browser),'sha256':sha(browser),'version':_probe([str(browser),'--version'])},'playwright_core':{'root':str(root),'version':package['version'],'files':assets,'content_sha256':digest(assets)},'observer_sha256':sha(observer),'font_files':fonts,'platform':{'system':platform.system(),'machine':platform.machine()},'settings':json.loads(json.dumps(SETTINGS))}
    validate_html_lock(lock);return lock
def validate_html_lock(lock,*,require_assets=True):
    fail=lambda msg:HtmlRuntimeError('HTML_RUNTIME_LOCK_INVALID',msg)
    keys={'schema_version','profile','node','browser','playwright_core','observer_sha256','font_files','platform','settings'}
    if not isinstance(lock,dict) or set(lock)!=keys or lock.get('schema_version')!=LOCK_SCHEMA or lock.get('profile')!=PROFILE or lock.get('settings')!=SETTINGS:raise fail('schema, profile or observation settings differ')
    def checksum(value):return isinstance(value,str) and bool(re.fullmatch('[0-9a-f]{64}',value))
    if not checksum(lock['observer_sha256']) or not isinstance(lock['platform'],dict) or lock['platform'].keys()!={'system','machine'} or not all(isinstance(v,str) and v for v in lock['platform'].values()):raise fail('observer/platform binding')
    for kind in ['node','browser']:
        record=lock[kind]
        if not isinstance(record,dict) or set(record)!={'executable','sha256','version'} or not isinstance(record['executable'],str) or not Path(record['executable']).is_absolute() or not checksum(record['sha256']) or not isinstance(record['version'],str) or not record['version']:raise fail(kind+' identity')
        if require_assets:
            p=_file(record['executable'],'HTML_'+kind.upper()+'_UNAVAILABLE')
            if sha(p)!=record['sha256']:raise HtmlRuntimeError('HTML_'+kind.upper()+'_DRIFT','executable bytes changed')
            if _probe([str(p),'--version'])!=record['version']:raise HtmlRuntimeError('HTML_'+kind.upper()+'_DRIFT','executable version changed')
    library=lock['playwright_core']
    if not isinstance(library,dict) or set(library)!={'root','version','files','content_sha256'} or not isinstance(library['root'],str) or not Path(library['root']).is_absolute() or not isinstance(library['version'],str) or not library['version'] or not isinstance(library['files'],list) or not 1<=len(library['files'])<=10000:raise fail('library identity')
    seen=set();size=0
    for row in library['files']:
        if not isinstance(row,dict) or set(row)!={'path','size','sha256'} or not isinstance(row['path'],str) or not _relative(row['path']) or row['path'] in seen or type(row['size']) is not int or row['size']<0 or not checksum(row['sha256']):raise fail('library member')
        seen.add(row['path']);size+=row['size']
    if size>256*1024*1024 or not checksum(library['content_sha256']) or digest(library['files'])!=library['content_sha256']:raise fail('library digest')
    if not isinstance(lock['font_files'],list) or len(lock['font_files'])>512:raise fail('fonts')
    seen_fonts=set()
    for row in lock['font_files']:
        if not isinstance(row,dict) or set(row)!={'path','size','sha256'} or not isinstance(row['path'],str) or not Path(row['path']).is_absolute() or row['path'] in seen_fonts or type(row['size']) is not int or row['size']<0 or not checksum(row['sha256']):raise fail('font member')
        seen_fonts.add(row['path'])
        if require_assets and (sha(_file(row['path'],'HTML_FONT_UNAVAILABLE'))!=row['sha256'] or Path(row['path']).stat().st_size!=row['size']):raise HtmlRuntimeError('HTML_FONT_DRIFT','font bytes changed')
    if require_assets:
        if lock['platform']!={'system':platform.system(),'machine':platform.machine()}:raise HtmlRuntimeError('HTML_PLATFORM_DRIFT','re-bootstrap on this scoring platform')
        if _tree(library['root'])!=library['files']:raise HtmlRuntimeError('HTML_LIBRARY_DRIFT','Playwright core asset tree changed')
    return lock
def html_lock_digest(lock):validate_html_lock(lock,require_assets=False);return digest(lock)
def _relative(value):return not value.startswith('/') and not re.match(r'^[A-Za-z]:',value) and '\\' not in value and all(p not in {'','.','..'} for p in value.split('/'))
def _resources(root,source):
    original=Path(root)
    if original.is_symlink():raise HtmlRuntimeError('HTML_RESOURCE_UNSUPPORTED','resource root symlink')
    root=original.resolve();rows=[];total=0
    if not source.is_relative_to(root):raise HtmlRuntimeError('HTML_RESOURCE_ROOT_INVALID','source outside public resource root')
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root).as_posix()
        if not _relative(rel):raise HtmlRuntimeError('HTML_RESOURCE_UNSUPPORTED','resource path')
        if p.is_symlink():raise HtmlRuntimeError('HTML_RESOURCE_UNSUPPORTED','resource symlinks require another profile')
        if not p.is_file() or p==source:continue
        if any(x in {'.git','.agents','gt','private','worker','runtime'} for x in p.relative_to(root).parts):continue
        total+=p.stat().st_size
        if len(rows)>=256 or total>MAX_RESOURCE_BYTES:raise HtmlRuntimeError('HTML_RESOURCE_UNSUPPORTED','public resource limit')
        rows.append({'path':rel,'sha256':sha(p),'size':p.stat().st_size,'content_type':mimetypes.guess_type(rel)[0] or 'application/octet-stream'})
    return rows
def _probes(probes):
    if not isinstance(probes,list) or len(probes)>512:raise HtmlRuntimeError('HTML_PROBE_INVALID','at most512 geometry probes')
    ids=set()
    for row in probes:
        if not isinstance(row,dict) or set(row)-{'id','x','y','radius','targets'} or not {'id','x','y'}<=set(row) or not isinstance(row['id'],str) or not row['id'] or row['id'] in ids:raise HtmlRuntimeError('HTML_PROBE_INVALID','probe identity')
        ids.add(row['id'])
        for key in ['x','y','radius']:
            v=row.get(key,1)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not -20000<=v<=20000 or key=='radius' and not 0<=v<=8:raise HtmlRuntimeError('HTML_PROBE_INVALID','bounded finite coordinates')
        if 'targets' in row and (not isinstance(row['targets'],list) or len(row['targets'])>100 or any(not isinstance(x,str) for x in row['targets'])):raise HtmlRuntimeError('HTML_PROBE_INVALID','target IDs')
    return probes
def _terminate(process,process_info):
    # Playwright's browser has its own process group. Only IDs reported by our
    # live renderer, bound to its exact node PID, may be cleaned here.
    browser_pid=None
    try:
        info=json.loads(process_info.read_text())
        if info.get('node_pid')==process.pid and type(info.get('browser_pid')) is int and info['browser_pid']>1:browser_pid=info['browser_pid']
    except (OSError,ValueError):pass
    if os.name=='nt':
        for pid in [browser_pid,process.pid]:
            if pid:subprocess.run([str(Path(os.environ.get('SYSTEMROOT','C:/Windows'))/'System32/taskkill.exe'),'/PID',str(pid),'/T','/F'],capture_output=True,timeout=10)
    else:
        for pid in [browser_pid,process.pid]:
            if not pid:continue
            try:
                if os.getpgid(pid)==pid:os.killpg(pid,signal.SIGTERM)
                else:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:pass
        # BrowserServer owns another process group. Node exiting on TERM does
        # not imply that its browser group exited as well.
        for pid in [browser_pid,process.pid]:
            if not pid:continue
            try:
                if os.getpgid(pid)==pid:os.killpg(pid,signal.SIGKILL)
                else:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
def observe_html(source,lock,output_dir,*,resource_root=None,probes=None,timeout_seconds=60):
    source=_file(source,'HTML_INPUT_INVALID')
    if source.stat().st_size>MAX_HTML_BYTES:raise HtmlRuntimeError('HTML_INPUT_LIMIT','HTML source limit')
    try:source.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError as e:raise HtmlRuntimeError('HTML_INPUT_INVALID','UTF-8 HTML required') from e
    if isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,(int,float)) or not math.isfinite(timeout_seconds) or not 0<timeout_seconds<=600:raise HtmlRuntimeError('HTML_TIMEOUT_INVALID','finite positive timeout up to600 seconds')
    validate_html_lock(lock);observer=Path(__file__).with_name('html_observer.mjs')
    if sha(observer)!=lock['observer_sha256']:raise HtmlRuntimeError('HTML_OBSERVER_DRIFT','observer script differs from frozen runtime')
    resource_root=Path(resource_root or source.parent);resources=_resources(resource_root,source);resource_root=resource_root.resolve();probes=_probes([] if probes is None else probes);source_sha=sha(source);output_path=Path(output_dir)
    if output_path.is_symlink():raise HtmlRuntimeError('HTML_OUTPUT_INVALID','derived directory symlink')
    output=output_path.resolve()
    if output==source.parent or output.is_relative_to(resource_root):raise HtmlRuntimeError('HTML_OUTPUT_INVALID','derived directory must be outside public source/resources')
    output.mkdir(parents=True,exist_ok=False);shutil.copyfile(source,output/'source.html');shutil.copyfile(observer,output/'observer.mjs')
    for row in resources:
        p=output/'resources'/(row['sha256']+'.bin');p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():shutil.copyfile(resource_root/row['path'],p)
        if sha(p)!=row['sha256']:raise HtmlRuntimeError('HTML_SOURCE_DRIFT','resource changed while copying')
    request={'schema_version':'wildclawbench.html-observer-request/v1','profile':PROFILE,'source_sha256':source_sha,'runtime':lock,'resources':resources,'source_resource_path':source.relative_to(resource_root).as_posix(),'probes':probes};(output/'request.json').write_text(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='general-html-') as tmp:
        command=[lock['node']['executable'],str(output/'observer.mjs'),'--request',str(output/'request.json'),'--output',str(output)]
        kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)}
        try:
            process=subprocess.Popen(command,cwd=tmp,env=_env(Path(tmp)),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
            try:stdout,stderr=process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as e:_terminate(process,output/'process-info.json');stdout,stderr=process.communicate();raise HtmlRuntimeError('HTML_OBSERVATION_TIMEOUT','browser/renderer process tree terminated') from e
        except OSError as e:raise HtmlRuntimeError('HTML_RUNTIME_UNAVAILABLE',str(e)) from e
    if process.returncode:
        code='HTML_OBSERVATION_FAILED'
        if (output/'renderer-error.json').is_file():code=json.loads((output/'renderer-error.json').read_text()).get('code',code)
        raise HtmlRuntimeError(code,stderr.decode(errors='replace')[-1500:])
    observed=output/'observation.json'
    if not observed.is_file() or observed.stat().st_size>MAX_OBSERVATION_BYTES:raise HtmlRuntimeError('HTML_OBSERVATION_INVALID','missing/oversized observation')
    value=json.loads(observed.read_text(encoding='utf-8'));
    if value.get('schema_version')!=OBSERVATION_SCHEMA or value.get('source_sha256')!=source_sha or value.get('settings')!=SETTINGS:raise HtmlRuntimeError('HTML_OBSERVATION_INVALID','observation context mismatch')
    if sha(source)!=source_sha or any(sha(resource_root/r['path'])!=r['sha256'] for r in resources):raise HtmlRuntimeError('HTML_SOURCE_DRIFT','source/resources changed')
    validate_html_lock(lock)
    artifacts=[{'path':p.relative_to(output).as_posix(),'size':p.stat().st_size,'sha256':sha(p)} for p in sorted(output.rglob('*')) if p.is_file() and p.name!='html-audit.json']
    audit={'schema_version':AUDIT_SCHEMA,'profile':PROFILE,'source_sha256':source_sha,'source_unchanged':True,'runtime_lock_sha256':html_lock_digest(lock),'request_sha256':sha(output/'request.json'),'observation_sha256':sha(observed),'resources':resources,'artifacts':artifacts};(output/'html-audit.json').write_text(json.dumps(audit,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return {'path':str(observed),'audit_path':str(output/'html-audit.json'),'audit':audit,'screenshot':str(output/'page.png')}
def verify_html_observation(source,output_dir,audit,lock,*,resource_root=None,archived=False):
    validate_html_lock(lock,require_assets=not archived);source=_file(source,'HTML_AUDIT_INVALID');out=Path(output_dir);root=Path(resource_root or source.parent).resolve();invalid=lambda m:HtmlRuntimeError('HTML_AUDIT_INVALID',m)
    if out.is_symlink() or not out.is_dir():raise invalid('ordinary derived directory required')
    out=out.resolve()
    keys={'schema_version','profile','source_sha256','source_unchanged','runtime_lock_sha256','request_sha256','observation_sha256','resources','artifacts'}
    if not isinstance(audit,dict) or set(audit)!=keys or audit.get('schema_version')!=AUDIT_SCHEMA or audit.get('profile')!=PROFILE or audit.get('source_unchanged') is not True or audit.get('source_sha256')!=sha(source) or audit.get('runtime_lock_sha256')!=html_lock_digest(lock):raise invalid('source/runtime binding')
    artifacts=audit['artifacts']
    if not isinstance(artifacts,list) or not 5<=len(artifacts)<=1024:raise invalid('artifact inventory')
    seen=set()
    for row in artifacts:
        if not isinstance(row,dict) or set(row)!={'path','size','sha256'} or not isinstance(row['path'],str) or not _relative(row['path']) or row['path'] in seen or type(row['size']) is not int or row['size']<0 or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise invalid('artifact member')
        seen.add(row['path']);p=out/row['path']
        if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=out and out in x.parents) or not p.is_file() or p.stat().st_size!=row['size'] or sha(p)!=row['sha256']:raise invalid('artifact bytes: '+row['path'])
    actual={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.name!='html-audit.json'}
    if seen!=actual or not {'source.html','observer.mjs','request.json','observation.json','page.png'}<=seen:raise invalid('artifact set')
    if sha(out/'source.html')!=sha(source) or sha(out/'observer.mjs')!=lock['observer_sha256'] or sha(out/'request.json')!=audit['request_sha256'] or sha(out/'observation.json')!=audit['observation_sha256']:raise invalid('context bytes')
    try:req=json.loads((out/'request.json').read_text(encoding='utf-8'));obs=json.loads((out/'observation.json').read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as exc:raise invalid('invalid JSON context') from exc
    if not isinstance(req,dict) or not isinstance(obs,dict):raise invalid('object context required')
    if req.get('schema_version')!='wildclawbench.html-observer-request/v1' or req.get('runtime')!=lock or req.get('profile')!=PROFILE or req.get('source_sha256')!=sha(source) or req.get('resources')!=audit['resources'] or not isinstance(req.get('source_resource_path'),str) or not _relative(req['source_resource_path']) or not source.is_relative_to(root) or source.relative_to(root).as_posix()!=req['source_resource_path']:raise invalid('request context')
    _probes(req.get('probes'))
    if obs.get('schema_version')!=OBSERVATION_SCHEMA or obs.get('profile')!=PROFILE or obs.get('source_sha256')!=sha(source) or obs.get('settings')!=SETTINGS or obs.get('probes_requested')!=req['probes']:raise invalid('observation context')
    if not isinstance(audit['resources'],list) or len(audit['resources'])>256:raise invalid('resource inventory')
    for row in audit['resources']:
        if not isinstance(row,dict) or set(row)!={'path','size','sha256','content_type'} or not isinstance(row['path'],str) or not _relative(row['path']) or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']) or type(row['size']) is not int or row['size']<0 or not isinstance(row['content_type'],str):raise invalid('resource binding')
        original=root/row['path'];copy=out/'resources'/(row['sha256']+'.bin')
        if original.is_symlink() or any(x.is_symlink() for x in original.parents if x!=root and root in x.parents) or not original.is_file() or original.stat().st_size!=row['size'] or sha(original)!=row['sha256'] or not copy.is_file() or sha(copy)!=row['sha256']:raise invalid('resource source bytes')
    if _resources(root,source)!=audit['resources']:raise invalid('public resource inventory changed')
    return audit
