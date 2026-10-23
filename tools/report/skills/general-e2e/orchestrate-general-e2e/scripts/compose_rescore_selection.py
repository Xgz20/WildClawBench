"""Compose an explicit rescore into a complete, verified submission.

Does not score, pick best attempts, mutate orchestration state, or shrink scope.
Source and replacement orchestrations must already have locked submissions.
"""
import argparse, copy, datetime, hashlib, importlib.util, json, pathlib, shutil, sys, uuid

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plan_selection(source, replacement, allowed):
    if not allowed or len(allowed)!=len(set(allowed)):
        raise ValueError('EXPLICIT_UNIQUE_TASK_SELECTION_REQUIRED')
    if source['scope']!=replacement['scope'] or source['dataset']!=replacement['dataset']:
        raise ValueError('SCOPE_OR_DATASET_MISMATCH')
    original=source['task_ids']
    if len(original)!=len(set(original)) or original!=[t['task_id'] for t in source['tasks']]:
        raise ValueError('SOURCE_TASK_ORDER_INVALID')
    actual=[t['task_id'] for t in replacement['tasks']]
    if len(actual)!=len(set(actual)) or set(actual)!=set(allowed) or not set(actual)<=set(original):
        raise ValueError('REPLACEMENT_SELECTION_MISMATCH')
    selected={t['task_id']:t for t in replacement['tasks']}
    rows=[]
    for old in source['tasks']:
        new=selected.get(old['task_id'])
        if new:
            for key in ('execution_attempt_id','candidate_sha256','execution_status'):
                if old[key]!=new[key]:raise ValueError('FROZEN_EXECUTION_CHANGED:'+key)
            if new['scoring_attempt_id']==old['scoring_attempt_id']:
                raise ValueError('NEW_SCORING_ATTEMPT_REQUIRED')
            if new['score_status'] not in ('valid','evaluation_error'):
                raise ValueError('TERMINAL_LEGAL_SCORE_REQUIRED')
            rows.append(copy.deepcopy(new))
        else:rows.append(copy.deepcopy(old))
    return rows

def copy_attempt(source,target):
    target.mkdir(parents=True,exist_ok=False)
    for child in source.iterdir():
        if child.name=='runtime':continue
        dest=target/child.name
        if child.is_symlink():dest.symlink_to(child.readlink())
        elif child.is_dir():shutil.copytree(child,dest,symlinks=True)
        else:shutil.copy2(child,dest)

def compose(args, *, frozen=None):
    script=pathlib.Path(__file__).resolve().with_name('orchestrate_general_e2e.py')
    requested=getattr(args,'orchestrator_script',None)
    if requested is not None and requested.resolve(strict=True)!=script:
        raise ValueError('ORCHESTRATOR_MUST_MATCH_FROZEN_SKILL')
    expected=getattr(args,'orchestrator_sha256',None)
    if expected is not None and digest(script)!=expected:raise ValueError('ORCHESTRATOR_SHA_MISMATCH')
    if frozen is None:
        spec=importlib.util.spec_from_file_location('_frozen_orchestrator_for_selection',script)
        frozen=importlib.util.module_from_spec(spec);sys.modules[spec.name]=frozen;spec.loader.exec_module(frozen)
    src=args.source.resolve(strict=True);rep=args.replacement.resolve(strict=True)
    ss=frozen._verify_state(src);rs=frozen._verify_state(rep)
    if not ss.get('submission') or not rs.get('submission') or rs.get('kind')!='rescore':
        raise ValueError('LOCKED_SOURCE_AND_RESCORE_SUBMISSIONS_REQUIRED')
    if rs['sources']['source_state_sha256']!=digest(src/'orchestration-state.json') or rs['sources']['source_submission_sha256']!=digest(src/'submission.json'):
        raise ValueError('RESCORE_SOURCE_LINEAGE_MISMATCH')
    if ss['judge']!=rs['judge']:raise ValueError('JUDGE_CONFIG_CHANGED')
    source=json.loads((src/'submission.json').read_text(encoding='utf-8'))
    replacement=json.loads((rep/'submission.json').read_text(encoding='utf-8'))
    rows=plan_selection(source,replacement,args.task_id)
    old_by={t['task_id']:t for t in ss['tasks']}
    for task in rs['tasks']:
        old=old_by[task['task_id']]
        if task['source']['score_sha256']!=old['score']['sha256'] or task['source']['scoring_attempt_id']!=old['scoring_attempt_id']:
            raise ValueError('TASK_SOURCE_LINEAGE_MISMATCH')
        original=json.loads((src/old['attempt_path']/'attempt-manifest.json').read_text(encoding='utf-8'))
        adopted=json.loads((rep/task['attempt_path']/'attempt-manifest.json').read_text(encoding='utf-8'))
        for key in ('candidate','contract','dataset','execution','task'):
            if key in original and original[key]!=adopted.get(key):raise ValueError('FROZEN_INPUT_CHANGED:'+key)
    output=args.output_root.resolve()
    if output.exists():raise ValueError('OUTPUT_EXISTS')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=output.parent/('.'+output.name+'.staging-'+uuid.uuid4().hex)
    stage.mkdir()
    locks=[{'path':str(path),'sha256':digest(path)} for root in (src,rep) for path in (root/'orchestration-state.json',root/'submission.json')]
    shutil.copytree(src/'execution-records',stage/'execution-records')
    allowed=set(args.task_id)
    for row in rows:
        relative=pathlib.PurePosixPath(row['score_path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0]!='attempts' or relative.name!='score.json':
            raise ValueError('UNSAFE_SCORE_PATH')
        root=rep if row['task_id'] in allowed else src
        selected=root.joinpath(*relative.parts).parent
        target=stage.joinpath(*relative.parts).parent
        copy_attempt(selected,target)
        frozen._run_score_command(ss['score_skill'],['verify-score','--attempt-root',str(target),'--archived'])
        if digest(target/'score.json')!=row['score_sha256']:raise ValueError('COPIED_SCORE_SHA_MISMATCH')
    document=copy.deepcopy(source)
    document.update(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),tasks=rows)
    frozen._validate_contract(document,expected_schema_id=frozen.SUBMISSION_SCHEMA)
    (stage/'submission.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lineage={'kind':'explicit-full-scope-rescore-selection/v1','source_orchestration':str(src),'replacement_orchestration':str(rep),'selected_replacements':args.task_id,'unchanged_task_count':len(rows)-len(allowed),'task_count':len(rows),'source_locks':locks,'operator_sha256':digest(pathlib.Path(__file__)),'orchestrator':{'path':str(script),'sha256':digest(script)},'old_files_unchanged':True,'score_creation_performed':False,'scope_shrunk':False,'submission_sha256':digest(stage/'submission.json')}
    for lock in locks:
        if digest(pathlib.Path(lock['path']))!=lock['sha256']:raise ValueError('SOURCE_CHANGED_DURING_COMPOSITION')
    (stage/'selection-lineage.json').write_text(json.dumps(lineage,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    stage.rename(output)
    return {'status':'PASS','output_root':str(output),'task_count':len(rows),'replacement_count':len(allowed),'unchanged_task_count':len(rows)-len(allowed),'submission_sha256':lineage['submission_sha256']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=pathlib.Path,required=True)
    parser.add_argument('--replacement',type=pathlib.Path,required=True)
    parser.add_argument('--task-id',action='append',required=True)
    parser.add_argument('--orchestrator-script',type=pathlib.Path)
    parser.add_argument('--orchestrator-sha256')
    parser.add_argument('--output-root',type=pathlib.Path,required=True)
    print(json.dumps(compose(parser.parse_args())))
