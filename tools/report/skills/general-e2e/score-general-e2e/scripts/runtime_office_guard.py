"""Audit/seal completed disposable runtime Office copies, retaining CWM drift.

Recovery must reconstruct the EXACT original full post-rule tree digest. It
never changes a candidate original, manifest, audit, rubric, component or score.
"""
import argparse,hashlib,importlib.util,json,os,stat,sys
from pathlib import Path
from datetime import datetime,timezone
import office_input_compat
OFFICE={'.docx','.xlsx','.pptx','.docm','.xlsm','.pptm'}
def sha(data):return hashlib.sha256(data).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
def seal_file(path):
    if hasattr(os,'chflags'):os.chflags(path,path.stat().st_flags|stat.UF_IMMUTABLE,follow_symlinks=False)
def tree_digest(entries):
    digest=hashlib.sha256()
    for row in entries:
        if row['type']!='directory':digest.update((row['path']+'\0'+row['type']+'\0'+row['sha256']+'\n').encode())
    return digest.hexdigest()
def load(rt,attempt):
    root=Path(attempt).resolve(strict=True);m=rt._read_json(root/'attempt-manifest.json');audit=rt._read_json(root/'rule-audit.json')
    require(m.get('schema_version')==rt.ATTEMPT_SCHEMA and audit.get('identity')==m.get('identity'),'RUNTIME_GUARD_IDENTITY')
    require(audit.get('status')=='completed','RUNTIME_GUARD_REQUIRES_COMPLETED_RULE')
    runtime=rt._resolve_within(root,m['paths']['runtime_workspace'],'runtime_workspace')
    entries,current=rt._inventory_tree(runtime)
    return root,m,audit,runtime,entries,current
def guard(rt,attempt,output):
    root,m,audit,runtime,entries,current=load(rt,attempt)
    require(current==audit['runtime_workspace']['final_sha256'],'RUNTIME_GUARD_SOURCE_DRIFT')
    protected=[]
    for entry in entries:
        if entry['type']=='file' and Path(entry['path']).suffix.lower() in OFFICE:
            path=runtime/entry['path'];seal_file(path)
            require(sha(path.read_bytes())==entry['sha256'],'RUNTIME_GUARD_COPY_CHANGED')
            protected.append({'path':entry['path'],'sha256':entry['sha256']})
    require(rt._inventory_tree(runtime)[1]==current,'RUNTIME_GUARD_TREE_CHANGED')
    result={'profile':'completed-runtime-office-byte-guard/v1','status':'PASS','at':datetime.now(timezone.utc).isoformat(),
        'attempt_root':str(root),'rule_audit_sha256':sha((root/'rule-audit.json').read_bytes()),'full_runtime_sha256':current,
        'files':protected,'candidate_originals_modified':False,'scores_modified':False}
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    return result
def recover(rt,attempt,output):
    root,m,audit,runtime,entries,current=load(rt,attempt);expected=audit['runtime_workspace']['final_sha256']
    require(current!=expected,'RUNTIME_RECOVERY_NO_DRIFT')
    original=rt._resolve_within(root,m['paths']['candidate_original'],'candidate_original')
    original_entries,original_digest=rt._inventory_tree(original)
    require(original_digest==m['digests']['candidate_original_sha256'],'RUNTIME_RECOVERY_CANONICAL_DRIFT')
    canonical={r['path']:r for r in original_entries if r['type']=='file'}
    proposed=[dict(r) for r in entries];changes=[]
    for row in proposed:
        ref=canonical.get(row['path'])
        if not ref or Path(row['path']).suffix.lower() not in OFFICE or row['sha256']==ref['sha256']:continue
        path=runtime/row['path'];before=path.read_bytes();source=(original/row['path']).read_bytes()
        proof=office_input_compat.compare_office_cwm(source,before,ref['sha256'])
        require(proof is not None,'RUNTIME_RECOVERY_NOT_CWM_ONLY')
        changes.append({'path':path,'relative':row['path'],'before':before,'source':source,'proof':proof,'mode':int(row['mode'],8)})
        row.update(sha256=ref['sha256'],size=ref['size'])
    require(changes and tree_digest(proposed)==expected,'RUNTIME_RECOVERY_EXACT_FINAL_TREE_NOT_PROVEN')
    out=Path(output).absolute();require(out.resolve().is_relative_to(root/'infrastructure-evidence/runtime-office-recoveries'),'RUNTIME_RECOVERY_OUTPUT_SCOPE')
    require(not out.exists(),'RUNTIME_RECOVERY_OUTPUT_EXISTS');out.mkdir(parents=True)
    locked={name:sha((root/name).read_bytes()) for name in ['attempt-manifest.json','rule-audit.json','rule-component.json','score.json'] if (root/name).is_file()}
    records=[]
    for i,item in enumerate(changes):
        variant=out/('%03d-variant.bin'%i)
        with variant.open('xb') as handle:handle.write(item['before'])
        seal_file(variant)
        records.append({'path':item['relative'],'canonical_sha256':sha(item['source']),'variant_sha256':sha(item['before']),'variant_path':str(variant),'cwm_proof':item['proof']})
    (out/'intent.json').write_text(json.dumps({'profile':'exact-post-rule-runtime-cwm-recovery/v1','expected_runtime_sha256':expected,'before_runtime_sha256':current,'files':records,'unchanged_frozen_files':locked},ensure_ascii=False,indent=2),encoding='utf-8')
    for i,item in enumerate(changes):
        path=item['path'];require(path.read_bytes()==item['before'],'RUNTIME_RECOVERY_RACE')
        temporary=path.with_name(path.name+'.canonical-recovery')
        with temporary.open('xb') as handle:handle.write(item['source'])
        os.chmod(temporary,item['mode']);path.rename(out/('%03d-original-location.bin'%i));seal_file(out/('%03d-original-location.bin'%i))
        temporary.rename(path);seal_file(path)
    require(rt._inventory_tree(runtime)[1]==expected,'RUNTIME_RECOVERY_AFTER_HASH_MISMATCH')
    for name,digest in locked.items():require(sha((root/name).read_bytes())==digest,'RUNTIME_RECOVERY_FROZEN_FILE_CHANGED')
    result={'profile':'exact-post-rule-runtime-cwm-recovery/v1','status':'PASS','runtime_sha256':expected,'files':records,'unchanged_frozen_files':locked,'candidate_originals_modified':False,'scores_modified':False}
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['guard','recover']);parser.add_argument('--attempt-root',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();path=Path(__file__).parent/'score_general_e2e.py';spec=importlib.util.spec_from_file_location('runtime_guard_frozen_score',path);rt=importlib.util.module_from_spec(spec);sys.modules[spec.name]=rt;spec.loader.exec_module(rt)
    result=(guard if args.command=='guard' else recover)(rt,args.attempt_root,args.output);print(json.dumps({'status':result['status'],'profile':result['profile'],'file_count':len(result['files'])}))
