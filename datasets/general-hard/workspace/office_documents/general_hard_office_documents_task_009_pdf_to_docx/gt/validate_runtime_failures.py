"""Supplemental real dependency/lock failures; never fabricate a candidate zero."""
from pathlib import Path
import argparse,hashlib,json,os,runpy,shutil

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path);parser.add_argument('--gt-root',required=True,type=Path)
    parser.add_argument('--render-lock',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=False)
    lock=json.loads(args.render_lock.read_text(encoding='utf-8'));results={}
    for name in ['missing_render_lock','engine_unavailable','font_drift']:
        root=args.output_dir/name;workspace=root/'workspace';shutil.copytree(args.exec_root,workspace)
        shutil.copytree(args.gt_root,workspace/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(args.gt_root/'reference/results',workspace/'results')
        path=root/'render-lock.json';value=json.loads(json.dumps(lock))
        if name=='engine_unavailable':value['office_runtime']['executable']=str(root/'absent-soffice')
        elif name=='font_drift':
            font=value['fonts'][0];copy=root/'changed-font.ttf';copy.write_bytes(Path(font['path']).read_bytes()+b'author-drift-control')
            font['path']=str(copy)
        if name!='missing_render_lock':path.write_text(json.dumps(value),encoding='utf-8')
        before={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob('*') if p.is_file()}
        os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(path);os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(root/'evidence')
        try:runpy.run_path(str(workspace/'gt/grader.py'))['grade'](workspace)
        except (FileNotFoundError,RuntimeError) as error:
            result={'error_type':type(error).__name__,'error':str(error),'score_created':False}
            if name=='engine_unavailable':assert getattr(error,'code',None)=='OFFICE_EXECUTABLE_UNAVAILABLE'
            if name=='font_drift':assert getattr(error,'code',None)=='OFFICE_RENDER_FONT_DRIFT'
        else:raise AssertionError('Infrastructure failure became a score: '+name)
        after={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob('*') if p.is_file()}
        assert before==after;result['workspace_unchanged']=True;results[name]=result
    report={'schema_version':'h009-runtime-failure-controls/v1','status':'pass','control_count':3,'controls':results,
        'limit':'Author real lock/dependency failure probes, not Harness execution or semantic judgments.'}
    (args.output_dir/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'pass','controls':results},ensure_ascii=False))
if __name__=='__main__':main()
