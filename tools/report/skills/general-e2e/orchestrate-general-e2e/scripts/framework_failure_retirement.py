"""Retain two registered infrastructure failures without editing judge evidence."""
from pathlib import Path
import subprocess
import escrow_state_review
import escrow_grouped_review
import release_baseline_text
import declared_public_snapshots
import public_snapshot_sidecar
import sterilization_quote_layout
import native_writer_cleanup_failure
import registered_rule_source_failures as source_failures

KINDS={source_failures.ERROR_KIND,escrow_grouped_review.ERROR_KIND,release_baseline_text.ERROR_KIND,declared_public_snapshots.ERROR_KIND,public_snapshot_sidecar.ERROR_KIND,sterilization_quote_layout.ERROR_KIND,native_writer_cleanup_failure.ERROR_KIND}

def failure_kind(rt,root,state,task):
    attempt=root/task['attempt_path'];m=rt._read_json(attempt/'attempt-manifest.json')
    contract=rt._read_json(attempt/m['paths']['contract'])
    if task.get('score') is not None or (attempt/'score.json').exists():raise ValueError('FRAMEWORK_FAILURE_HAS_SCORE')
    if contract.get('task_id') in source_failures.ROWS:
        source_failures.evidence(rt,attempt,m,contract,task)
        return source_failures.ERROR_KIND
    if contract.get('task_id')==native_writer_cleanup_failure.TASK:
        if (task.get('thread') or {}).get('status')!='COMPLETED':raise ValueError('NATIVE_CLEANUP_FAILURE_NOT_COMPLETED')
        native_writer_cleanup_failure.evidence(rt,attempt,m,contract)
        return native_writer_cleanup_failure.ERROR_KIND
    if contract.get('task_id')==sterilization_quote_layout.TASK:
        if ((task.get('thread') or {}).get('status')!='COMPLETED' or not (attempt/'semantic/query-log.json').exists()
                or (attempt/'semantic/semantic-component.json').exists() or not (attempt/'rule-component.json').exists()
                or rt._read_json(attempt/'rule-audit.json').get('status')!='completed'):
            raise ValueError('QUOTE_LAYOUT_NATIVE_FAILURE_INVALID')
        sterilization_quote_layout.validate_blocker(attempt,m,contract,rt._read_json(attempt/'scoring-infrastructure-blocker.json'))
        return sterilization_quote_layout.ERROR_KIND
    if contract.get('task_id')==public_snapshot_sidecar.TASK and (attempt/'rule-audit.json').exists():
        audit=rt._read_json(attempt/'rule-audit.json')
        if audit.get('status')=='failed':
            if task.get('thread') is not None or (attempt/'semantic').exists() or (attempt/'rule-component.json').exists():raise ValueError('PUBLIC_SNAPSHOT_BUDGET_FAILURE_HAS_JUDGE_OR_COMPONENT')
            public_snapshot_sidecar.failure_evidence(attempt,m,contract,audit,rt._read_json(attempt/'worker/result.json'))
            return public_snapshot_sidecar.ERROR_KIND
    if declared_public_snapshots.marker(contract,m['digests']['contract_sha256'],m['dataset']) is not None:
        audit=rt._read_json(attempt/'rule-audit.json');worker=rt._read_json(attempt/'worker/result.json')
        if (task.get('thread') is not None or (attempt/'semantic').exists() or audit.get('status')!='completed'
                or not (attempt/'rule-component.json').is_file()
                or not declared_public_snapshots.original_failure(attempt,m,contract,worker)):
            raise ValueError('PUBLIC_SNAPSHOT_ORIGINAL_FAILURE_INVALID')
        return declared_public_snapshots.ERROR_KIND
    if escrow_state_review.matches(contract,m['digests']['contract_sha256']):
        if (m.get('runtime',{}).get('rule_review_profile')!=escrow_state_review.PROFILE
                or task.get('thread') is not None):raise ValueError('DISCOVERY_FAILURE_PROFILE_INVALID')
        absent=['worker/result.json','rule-audit.json','rule-component.json','semantic',
            'rule-review/request.json','rule-review/discovery-audit.json']
        if any((attempt/p).exists() for p in absent):raise ValueError('DISCOVERY_FAILURE_ALREADY_PUBLISHED')
        request=rt._read_json(attempt/'rule-review/discovery/worker/request.json')
        result=rt._read_json(attempt/'rule-review/discovery/worker/result.json')
        source,_=escrow_state_review.effective_source(m,contract['automated_checks'],contract['automated_checks'],None)
        if (request.get('automated_checks')!=source or request.get('rule_review')!={'schema_version':'wildclawbench.general-e2e-rule-review-worker/v1',
                'profile':escrow_state_review.PROFILE,'mode':'discover','decisions':{}}
                or result.get('ok') is not False or result.get('result') is not None
                or result.get('error',{}).get('type')!='RuntimeError'
                or result.get('error',{}).get('message')!='RULE_REVIEW_CONTEXT_LIMIT'):
            raise ValueError('DISCOVERY_FAILURE_UNREGISTERED')
        return escrow_grouped_review.ERROR_KIND
    release_baseline_text.check_original(attempt,m,contract)
    audit=rt._read_json(attempt/'rule-audit.json');worker=rt._read_json(attempt/'worker/result.json')
    raw=worker.get('raw_result',{});diagnostic=raw.get('diagnostics',{})
    if (task.get('thread',{}).get('status')!='COMPLETED'
            or audit.get('status')!='completed' or worker.get('ok') is not True
            or sorted(diagnostic.get('changed_protected_files',[]))!=sorted(r['path'] for r in release_baseline_text.registry()['files'])
            or diagnostic.get('admission_conditions',{}).get('trusted_basis') is not False
            or not (attempt/'semantic/semantic-component.json').is_file()):
        raise ValueError('RELEASE_BASELINE_FAILURE_UNREGISTERED')
    return release_baseline_text.ERROR_KIND

def locks(rt,root,task):
    attempt=root/task['attempt_path'];paths=[attempt/'attempt-manifest.json',root/task['prompt_path']]
    for folder in ['worker','semantic','rule-review','infrastructure-evidence']:
        base=attempt/folder
        if base.exists():paths.extend(p for p in base.rglob('*') if p.is_file() and 'runtime' not in p.relative_to(base).parts)
    paths.extend(p for p in [attempt/'rule-audit.json',attempt/'rule-component.json',attempt/'rule-source-correction.json'] if p.exists())
    if task['task_id']==sterilization_quote_layout.TASK:paths.append(attempt/'scoring-infrastructure-blocker.json')
    if task['task_id']==native_writer_cleanup_failure.TASK:
        m=rt._read_json(attempt/'attempt-manifest.json');contract=rt._read_json(attempt/m['paths']['contract'])
        paths.extend(native_writer_cleanup_failure.evidence(rt,attempt,m,contract))
    result=[]
    for p in sorted(set(paths)):
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise ValueError('FRAMEWORK_FAILURE_UNSAFE_EVIDENCE')
        result.append({'path':p.relative_to(root).as_posix(),'sha256':rt._sha256_file(p)})
    return result

def verify(rt,root,state,task):
    record=task['framework_failure'];path=root/record['path'];proof=rt._read_json(path)
    if (not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or rt._sha256_file(path)!=record['sha256']
            or task['phase']!='UNSCORED' or proof.get('kind') not in KINDS
            or proof.get('kind')!=failure_kind(rt,root,state,task)
            or proof.get('identity')!=rt._read_json(root/task['attempt_path']/'attempt-manifest.json')['identity']
            or proof.get('thread')!=task.get('thread') or proof.get('locks')!=locks(rt,root,task)
            or proof.get('original_evidence_unchanged') is not True):raise ValueError('FRAMEWORK_FAILURE_PROOF_DRIFT')
    if proof['kind'] in {escrow_grouped_review.ERROR_KIND,source_failures.ERROR_KIND}:
        result=(source_failures.evidence(rt,root/task['attempt_path'],rt._read_json(root/task['attempt_path']/'attempt-manifest.json'),
            rt._read_json(root/task['attempt_path']/rt._read_json(root/task['attempt_path']/'attempt-manifest.json')['paths']['contract']),task)
            if proof['kind']==source_failures.ERROR_KIND else rt._read_json(root/task['attempt_path']/'rule-review/discovery/worker/result.json'))
        if result.get('worker_never_started') is True:
            if proof.get('owner_exit')!={'worker_never_started':True,'process_created':False}:
                raise ValueError('RULE_SOURCE_PREWORKER_OWNER_INVALID')
        elif (proof.get('owner_exit',{}).get('pid')!=result.get('worker',{}).get('pid')
                or proof.get('owner_exit',{}).get('ps_no_process') is not True):raise ValueError('DISCOVERY_OWNER_EXIT_PROOF_INVALID')
    elif proof['kind'] in {release_baseline_text.ERROR_KIND,sterilization_quote_layout.ERROR_KIND,native_writer_cleanup_failure.ERROR_KIND}:
        native=proof.get('native_context',{})
        if (native.get('status')!='PASS' or native.get('unfinished_turns')!=[]
                or native.get('thread_id')!=task['thread']['thread_id']
                or native.get('model')!=state['judge']['model'] or native.get('effort')!=state['judge']['reasoning_effort']
                or native.get('prompt_sha256')!=task['prompt_sha256']):raise ValueError('NATIVE_FAILURE_CONTEXT_INVALID')
    return proof

def record(rt,orchestration_root,*,task_id,reason,sdk_file=None,now=None):
    root=rt._state_root(orchestration_root);state=rt._verify_state(root);task=rt._task_by_id(state,rt._identifier(task_id,'task_id'))
    if task.get('phase') not in {'RULES_RUNNING','SCORE_VERIFICATION_PENDING','AWAITING_PROJECT','RULES_NEEDS_ATTENTION'}:raise ValueError('FRAMEWORK_FAILURE_PHASE_INVALID')
    kind=failure_kind(rt,root,state,task);attempt=root/task['attempt_path']
    expected_phase={source_failures.ERROR_KIND:source_failures.expected_phase(task_id) if task_id in source_failures.ROWS else None,escrow_grouped_review.ERROR_KIND:'RULES_RUNNING',release_baseline_text.ERROR_KIND:'SCORE_VERIFICATION_PENDING',
        declared_public_snapshots.ERROR_KIND:'AWAITING_PROJECT',public_snapshot_sidecar.ERROR_KIND:'RULES_NEEDS_ATTENTION',
        sterilization_quote_layout.ERROR_KIND:'SCORE_VERIFICATION_PENDING',native_writer_cleanup_failure.ERROR_KIND:'SCORE_VERIFICATION_PENDING'}[kind]
    if task['phase']!=expected_phase:raise ValueError('FRAMEWORK_FAILURE_KIND_PHASE_MISMATCH')
    rt._run_score_command(state['score_skill'],['verify','--attempt-root',str(attempt)])
    if kind==public_snapshot_sidecar.ERROR_KIND:
        manifest=rt._read_json(attempt/'attempt-manifest.json');contract=rt._read_json(attempt/manifest['paths']['contract'])
        public_snapshot_sidecar.preserve_failure(attempt,manifest,contract,rt._read_json(attempt/'rule-audit.json'),rt._read_json(attempt/'worker/result.json'))
    proof={'kind':kind,'identity':rt._read_json(attempt/'attempt-manifest.json')['identity'],
        'reason':rt._required_string(reason,'reason'),'thread':task.get('thread'),'locks':locks(rt,root,task),
        'at':rt._timestamp(now or rt._now()),'original_evidence_unchanged':True,'semantic_judging_performed':False}
    if kind in {escrow_grouped_review.ERROR_KIND,source_failures.ERROR_KIND}:
        manifest=rt._read_json(attempt/'attempt-manifest.json')
        result=(source_failures.evidence(rt,attempt,manifest,rt._read_json(attempt/manifest['paths']['contract']),task)
            if kind==source_failures.ERROR_KIND else rt._read_json(attempt/'rule-review/discovery/worker/result.json'))
        if result.get('worker_never_started') is True:
            proof['owner_exit']={'worker_never_started':True,'process_created':False}
        else:
            pid=result.get('worker',{}).get('pid')
            if isinstance(pid,bool) or not isinstance(pid,int) or pid<=0:raise ValueError('DISCOVERY_OWNER_PID_INVALID')
            process=subprocess.run(['ps','-p',str(pid),'-o','pid=,lstart=,command='],capture_output=True,text=True)
            if process.returncode!=1 or process.stdout.strip():raise ValueError('DISCOVERY_OWNER_NOT_PROVEN_EXITED')
            proof['owner_exit']={'pid':pid,'ps_no_process':True,'observed_at':proof['at']}
    elif kind in {release_baseline_text.ERROR_KIND,sterilization_quote_layout.ERROR_KIND,native_writer_cleanup_failure.ERROR_KIND}:
        if sdk_file is None:raise ValueError('COMPLETED_NATIVE_SDK_REQUIRED')
        from verify_judge_context import verify_context
        proof['native_context']=verify_context(sdk_file,thread_id=task['thread']['thread_id'],cwd=str(attempt.resolve()),
            model=state['judge']['model'],effort=state['judge']['reasoning_effort'],prompt=(root/task['prompt_path']).read_text(encoding='utf-8'))
    target=root/'framework-failures'/(task['scoring_attempt_id']+'.json');target.parent.mkdir(exist_ok=True);rt._write_new_json(target,proof)
    task['framework_failure']={'kind':kind,'path':target.relative_to(root).as_posix(),'sha256':rt._sha256_file(target)}
    task['phase']='UNSCORED';task['history'].append({'at':proof['at'],'event':'REGISTERED_FRAMEWORK_FAILURE_RETAINED',**task['framework_failure']})
    verify(rt,root,state,task)
    return rt._save(root,state,now or rt._now())
