"""H038 local Python audit profile. This is not an OS security sandbox."""
import argparse,collections,csv,hashlib,json,os,pathlib,shutil,sys,unicodedata,typing,io,stat,re,math,time,datetime,tempfile,runpy,pkgutil,codecs,encodings,resource,importlib,_strptime
sys.dont_write_bytecode=True
def main():
    request=json.loads(pathlib.Path(sys.argv[1]).read_text());workspace=pathlib.Path(request['workspace']).resolve();result=(workspace/'results').resolve();script=pathlib.Path(request['script']).resolve()
    if not script.is_relative_to(result) or not script.is_file() or script.is_symlink():raise RuntimeError('ENTRY_NOT_LOCAL')
    resource.setrlimit(resource.RLIMIT_CPU,(2,2));resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024));resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
    allowed={'argparse','collections','csv','hashlib','json','os','pathlib','shutil','sys','unicodedata','typing','io','stat','re','math','time','datetime','tempfile'}
    preloaded=set(sys.modules);stdlib=[(pathlib.Path(sys.base_prefix)/'lib').resolve(),(pathlib.Path(sys.prefix)/'lib').resolve()]
    def resolved(v):
        if isinstance(v,int):return None
        try:return pathlib.Path(os.fsdecode(v)).absolute().resolve()
        except (TypeError,ValueError,OSError):raise PermissionError('H038_PROFILE_INVALID_PATH')
    def check(v,write=False):
        p=resolved(v)
        if p is None:return
        ok=p==result or p.is_relative_to(result) if write else p==workspace or p.is_relative_to(workspace) or any(p==r or p.is_relative_to(r) for r in stdlib)
        if not ok:raise PermissionError('H038_PROFILE_PATH_DENIED: '+str(p))
    def audit(event,args):
        if event.startswith(('socket.','subprocess.','ctypes.')) or event in {'os.system','os.exec','os.posix_spawn','os.spawn','os.fork','os.forkpty','resource.setrlimit'}:raise PermissionError('H038_PROFILE_OPERATION_DENIED: '+event)
        if event=='import':
            name=args[0]
            if name not in preloaded and name.split('.')[0] not in allowed and not name.startswith('encodings.'):raise PermissionError('H038_PROFILE_IMPORT_DENIED: '+name)
        elif event=='open':
            mode=args[1];flags=args[2];write=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
            check(args[0],write)
        elif event in {'os.listdir','os.scandir','os.chdir'}:check(args[0])
        elif event in {'os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate'}:check(args[0],True)
        elif event in {'os.rename','os.link','os.symlink'}:
            if event in {'os.link','os.symlink'}:raise PermissionError('H038_PROFILE_LINK_DENIED')
            check(args[0],True);check(args[1],True)
    os.chdir(workspace);sys.argv=[str(script),'--workspace',str(workspace),*request.get('args',[])];sys.addaudithook(audit)
    try:runpy.run_path(str(script),run_name='__main__')
    except PermissionError as exc:
        print(json.dumps({'profile':'h038-python-audit/v1','status':'candidate_policy_failure','error':str(exc)}),file=sys.stderr);raise SystemExit(91)
if __name__=='__main__':main()
