"""Prepare an existing return as an original-identity, report-only source.

No production run-state initialization, execution, rule worker or Judge.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def require(ok,code):
    if not ok:raise ValueError(code)
def write(p,value):p.open('x',encoding='utf-8').write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def prepare(args):
    require(not args.model_display_label or bool(args.display_reason),'DISPLAY_OVERRIDE_REASON_REQUIRED')
    require(not any(p.expanduser().is_symlink() for p in [args.source_batch_root,args.archive,args.receipt]),'SOURCE_INPUT_SYMLINK')
    source=args.source_batch_root.resolve(strict=True)
    archive=args.archive.resolve(strict=True);receipt=args.receipt.resolve(strict=True)
    output=args.output_root.resolve();require(not output.exists(),'SOURCE_OUTPUT_EXISTS')
    originals=[source/'manifest.json',source/'report-config.json',archive,receipt]
    require(all(f.is_file() and not f.is_symlink() for f in originals),'SOURCE_INPUT_NOT_REGULAR')
    locks=[{'path':str(f),'sha256':sha(f),'size':f.stat().st_size} for f in originals]
    output.mkdir(parents=True,exist_ok=False);batch=output/'source-batch';batch.mkdir();logs=output/'logs';logs.mkdir()
    for name in ['manifest.json','report-config.json']:shutil.copy2(source/name,batch/name)
    run=Path(__file__).resolve().with_name('run_general_e2e.py')
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',GENERAL_E2E_NODE=args.node)
    def invoke(arguments,label):
        argv=[sys.executable,'-X','utf8',str(run),*map(str,arguments)]
        write(logs/(label+'.argv.json'),argv)
        completed=subprocess.run(argv,capture_output=True,env=environment)
        (logs/(label+'.stdout')).write_bytes(completed.stdout);(logs/(label+'.stderr')).write_bytes(completed.stderr)
        require(completed.returncode==0,label+':'+completed.stderr.decode('utf-8',errors='replace')[-2000:])
        return json.loads(completed.stdout)
    imported=invoke(['import-return','--batch-root',batch,'--archive',archive,'--receipt',receipt],'import-return')
    package=load(Path(imported['target'])/'package-manifest.json');identity=package['identity'];uid=identity['unit_id'];pid=package['package_id']
    invoke(['select-import','--batch-root',batch,'--unit-id',uid,'--package-id',pid],'select-import')
    root=Path(imported['target']);submission=load(root/'scoring/submission.json')
    require(submission['task_ids']==identity['task_ids'] and [t['task_id'] for t in submission['tasks']]==identity['task_ids'],'SOURCE_TASK_SCOPE_DRIFT')
    indexes=output/'indexes';indexes.mkdir()
    source_index={'schema_version':'wildclawbench.general-e2e-developer-sources/v1','imports':{uid:{'packages':[{'package_id':pid,'target':str(root),'package_manifest_sha256':sha(root/'package-manifest.json')}]}}}
    write(indexes/'source-index.json',source_index);rows=[]
    for task in submission['tasks']:
        score=root/'scoring'/task['score_path'] if task['score_path'] is not None else None
        if score is not None:require(sha(score)==task['score_sha256'],'SOURCE_SCORE_SHA_DRIFT')
        else:require(task['score_status']=='unscored','SOURCE_NULL_SCORE_STATUS_DRIFT')
        rows.append({'unit_id':uid,'task_id':task['task_id'],'source_package_id':pid,
            'execution_record':str(root/'scoring/execution-records'/(task['task_id']+'.json')),
            'score_file':str(score) if score else None})
    write(indexes/'task-index.json',{'schema_version':'wildclawbench.general-e2e-developer-selection/v1','source_index_sha256':sha(indexes/'source-index.json'),'selected_tasks':rows})
    replay=[sys.executable,'-X','utf8',str(run.parents[2]/'report-general-e2e/scripts/selected_report.py'),'--workspace-root',str(output),'--batch-root',str(batch),'--source-index',str(indexes/'source-index.json'),'--task-index',str(indexes/'task-index.json'),'--target-unit',uid,'--node',args.node,'--data-output',str(output/'verified-source-report-data.json')]
    if args.model_display_label:
        display=indexes/'display-config.json';write(display,{'unit_model_labels':{uid:{'label':args.model_display_label,'reason':args.display_reason}}});replay+=['--display-config',str(display)]
    for item in locks:require(sha(Path(item['path']))==item['sha256'],'ORIGINAL_SOURCE_CHANGED')
    require(sha(batch/'manifest.json')==sha(source/'manifest.json') and sha(batch/'report-config.json')==sha(source/'report-config.json'),'SOURCE_CONTEXT_CHANGED')
    result={'status':'PASS','workspace_root':str(output),'batch_root':str(batch),'unit_id':uid,'package_id':pid,'task_count':len(rows),'source_index':str(indexes/'source-index.json'),'task_index':str(indexes/'task-index.json'),'source_only_replay_argv':replay,'input_locks':locks,'original_identity_preserved':True,'production_run_state_initialized':False,'no_harness_rule_worker_or_judge_called':True}
    write(output/'PREPARE_RECEIPT.json',result);return result

def add_arguments(parser):
    parser.add_argument('--source-batch-root',required=True,type=Path)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--node',default='node')
    parser.add_argument('--model-display-label')
    parser.add_argument('--display-reason')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);add_arguments(parser)
    print(json.dumps(prepare(parser.parse_args()),ensure_ascii=False,indent=2))
