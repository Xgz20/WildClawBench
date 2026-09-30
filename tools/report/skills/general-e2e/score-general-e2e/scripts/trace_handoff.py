"""Freeze a complete per-task trace bundle inside an independent scoring attempt."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, shutil, subprocess, sys

SCHEMA = 'wildclawbench.scoring-trace-handoff/v1'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def require(ok, code):
    if not ok:raise ValueError(code)

def child(root, name):
    require(isinstance(name,str) and name and '\\' not in name,'TRACE_HANDOFF_PATH')
    p=PurePosixPath(name);require(not p.is_absolute() and not any(x in ('.','..') for x in p.parts),'TRACE_HANDOFF_PATH')
    path=Path(root).joinpath(*p.parts)
    require(path.resolve().is_relative_to(Path(root).resolve()),'TRACE_HANDOFF_ESCAPE')
    require(path.is_file() and not path.is_symlink(),'TRACE_HANDOFF_FILE')
    return path

def copy_file(src,dst):
    src,dst=Path(src),Path(dst)
    dst.parent.mkdir(parents=True,exist_ok=True)
    if sys.platform=='darwin':
        subprocess.run(['/bin/cp','-c',str(src),str(dst)],check=True,capture_output=True)
    else:shutil.copy2(src,dst)
    return str(dst)

def freeze(unit_root, execution, attempt_root, *, required=False):
    index_name=execution.get('evidence',{}).get('trace_index_path')
    if not index_name:
        require(not required,'SCORING_TRACE_BUNDLE_REQUIRED')
        return None
    index_path=child(unit_root,index_name);index=json.loads(index_path.read_text())
    require(index.get('identity')==execution['identity'],'TRACE_HANDOFF_IDENTITY')
    for k in ('thread_id','turn_id','session_id','cwd'):
        if k in execution.get('session',{}):require(index.get('session',{}).get(k)==execution['session'][k],'TRACE_HANDOFF_SESSION')
    refs=[index.get('transcript',{}),*index.get('raw_trace',[]),*index.get('binding_evidence',[])]
    require(index.get('raw_trace') and all(r.get('path') for r in refs),'TRACE_HANDOFF_EMPTY')
    unique={}
    for r in refs:
        require(r['path'] not in ('trace-index.json','bundle-manifest.json'),'TRACE_HANDOFF_DUPLICATE')
        if r['path'] in unique:
            require(all(unique[r['path']][k]==r[k] for k in ('sha256','size')),'TRACE_HANDOFF_DUPLICATE_DRIFT')
        unique[r['path']]=r
    refs=list(unique.values())
    original_transcript=child(unit_root,execution['evidence']['transcript_path'])
    require(original_transcript==child(index_path.parent,index['transcript']['path']),'TRACE_HANDOFF_TRANSCRIPT_BINDING')
    dest=Path(attempt_root)/'trace';require(not dest.exists(),'TRACE_HANDOFF_EXISTS');dest.mkdir()
    artifacts=[]
    for ref in [{'path':'trace-index.json','sha256':sha(index_path),'size':index_path.stat().st_size},*refs]:
        src=index_path if ref['path']=='trace-index.json' else child(index_path.parent,ref['path'])
        require(src.stat().st_size==ref['size'] and sha(src)==ref['sha256'],'TRACE_HANDOFF_SOURCE_DRIFT')
        target=dest/ref['path'];copy_file(src,target)
        require(target.stat().st_size==ref['size'] and sha(target)==ref['sha256'],'TRACE_HANDOFF_COPY_DRIFT')
        artifacts.append({k:ref[k] for k in ('path','sha256','size')})
    manifest={'schema_version':SCHEMA,'identity':execution['identity'],'trace_index':'trace-index.json',
              'transcript':index['transcript']['path'],'raw_trace':[r['path'] for r in index['raw_trace']],
              'binding_evidence':[r['path'] for r in index.get('binding_evidence',[])],'artifacts':artifacts}
    p=dest/'bundle-manifest.json';p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return {'path':'trace/bundle-manifest.json','sha256':sha(p),'schema_version':SCHEMA}

def verify(root, ref, execution):
    p=child(root,ref['path']);require(sha(p)==ref['sha256'],'TRACE_HANDOFF_MANIFEST_DRIFT')
    m=json.loads(p.read_text());require(m['schema_version']==SCHEMA and m['identity']==execution['identity'],'TRACE_HANDOFF_IDENTITY')
    require(len({r['path'] for r in m['artifacts']})==len(m['artifacts']),'TRACE_HANDOFF_DUPLICATE')
    for r in m['artifacts']:
        f=child(p.parent,r['path']);require(f.stat().st_size==r['size'] and sha(f)==r['sha256'],'TRACE_HANDOFF_ARTIFACT_DRIFT')
    index=json.loads(child(p.parent,m['trace_index']).read_text())
    expected={r['path']:r for r in [index['transcript'],*index['raw_trace'],*index.get('binding_evidence',[])]}
    actual={r['path']:r for r in m['artifacts'] if r['path']!=m['trace_index']}
    require(set(actual)==set(expected),'TRACE_HANDOFF_MEMBER_SCOPE')
    for name,r in expected.items():require(all(actual[name][k]==r[k] for k in ('sha256','size')),'TRACE_HANDOFF_INDEX_DRIFT')
    require(index['identity']==execution['identity'],'TRACE_HANDOFF_IDENTITY')
    return m

def copy_frozen(source, dest, ref, execution):
    verify(source,ref,execution)
    shutil.copytree(Path(source)/'trace',Path(dest)/'trace',copy_function=copy_file)
    verify(dest,ref,execution)
    return dict(ref)
