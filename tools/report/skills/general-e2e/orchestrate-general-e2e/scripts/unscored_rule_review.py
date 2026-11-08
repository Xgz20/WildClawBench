"""Close a completed native judge's declared unresolved review without a score."""
import hashlib
import stat
import re

ERROR_KIND = 'native-declared-rule-review-unresolved/v1'
LOCK_KEYS = ('candidate_original_sha256', 'contract_sha256', 'task_sha256', 'private_gt_workspace_sha256',
             'transcript_sha256', 'execution_record_sha256', 'judge_config_sha256')

SOURCE_TASK='03_Data_Analysis_task_010_contract_escrow_refund_reconciliation'
SOURCE_CONTRACT='c93e50e83a8ac8eb9d6ba9e02510a762952b4011e8495c763073029a42bfff75'
SOURCE_SHA='a16b0e1b172dd17536f754d1f5c506a3220facfec584a0d6efc16ed85006c22d'
SOURCE_WORKER='71b0371f8a5aacc70126ca5d962d5cf18daea1280f0150fcf3c176e779f50b58'
SOURCE_ERROR='3ad48f9061f30c6aeb4b6b2365d1b58949b2d00b438a849a1311503f2922ea51'

def _declared_source_review(rt,attempt,manifest,audit):
    if (manifest.get('identity',{}).get('task_id')!=SOURCE_TASK
        or manifest.get('runtime',{}).get('rule_review_profile')!='escrow-status-equivalence-review/v6'
        or manifest.get('digests',{}).get('contract_sha256')!=SOURCE_CONTRACT
        or audit.get('status')!='completed'):return None
    request_contexts=rt._read_json(attempt/'rule-review/request.json').get('contexts')
    if (not isinstance(request_contexts,list) or not request_contexts
        or audit.get('reviewed_context_count')!=len(request_contexts)):return None
    contract=rt._read_json(attempt/manifest['paths']['contract'])
    if hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE_SHA:return None
    worker=rt._read_json(attempt/'worker/result.json');request=rt._read_json(attempt/'worker/request.json')
    failed=rt._read_json(attempt/'rule-audit.json');error=worker.get('error') or {}
    error_sha=hashlib.sha256(error.get('message','').encode()).hexdigest()
    legacy=(len(request_contexts)==2276 and error_sha==SOURCE_ERROR)
    prefix='评测不可判定，禁止形成正式综合分：'
    parts=error.get('message','').removeprefix(prefix).split('；')
    ellipsis=(error.get('message','').startswith(prefix) and parts
        and all(re.fullmatch(r'无法安全识别来源等价表示：…另[1-9][0-9]*处（见来源索引）',part) for part in parts))
    if (audit.get('status')!='completed'
        or audit.get('unresolved_context_ids')!=[] or worker.get('ok') is not False or worker.get('result') is not None
        or error.get('type')!='RuntimeError' or not (legacy or ellipsis)
        or hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=SOURCE_WORKER
        or failed.get('status')!='failed' or failed.get('identity')!=manifest['identity']
        or failed.get('worker',{}).get('request_sha256')!=rt._sha256_file(attempt/'worker/request.json')
        or failed.get('worker',{}).get('return_code')!=1
        or failed.get('worker',{}).get('process_tree_cleanup',{}).get('remaining') is not False):
        raise ValueError('DECLARED_SOURCE_REVIEW_FAILURE_SIGNATURE_INVALID')
    workspace=attempt/manifest['runtime']['workspace_argument']
    output=workspace/'评分证据'
    expected={'分析与验收.json','汇总与差异.json','规则核验.json'}
    if output.is_symlink() or not output.is_dir() or {p.name for p in output.iterdir()}!=expected:
        raise ValueError('DECLARED_SOURCE_REVIEW_OUTPUT_SCOPE_INVALID')
    output_locks=[]
    for p in sorted(output.iterdir()):
        if p.is_symlink() or not p.is_file():raise ValueError('DECLARED_SOURCE_REVIEW_OUTPUT_UNSAFE')
        rt._read_json(p)
        output_locks.append({'path':p.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(p)})
    digest=hashlib.sha256()
    def walk(directory,prefix=''):
        for p in sorted(directory.iterdir(),key=lambda p:p.name):
            relative=prefix+p.name
            if not prefix and p.name=='评分证据':continue
            mode=p.lstat().st_mode
            if stat.S_ISDIR(mode):walk(p,relative+'/')
            elif stat.S_ISREG(mode):
                digest.update(relative.encode());digest.update(b'\0file\0');digest.update(rt._sha256_file(p).encode());digest.update(b'\n')
            else:raise ValueError('DECLARED_SOURCE_REVIEW_RUNTIME_UNSAFE')
    walk(workspace)
    if digest.hexdigest()!=manifest['digests']['runtime_initial_sha256']:
        raise ValueError('DECLARED_SOURCE_REVIEW_BUSINESS_RUNTIME_DRIFT')
    if legacy:
        attention=rt._read_json(attempt/'scoring-attention-report.json')
        if (attention.get('task_id')!=SOURCE_TASK or attention.get('scoring_attempt_id')!=manifest['identity']['scoring_attempt_id']
            or attention.get('formal_score_published') is not False or attention.get('candidate_original_modified') is not False):
            raise ValueError('DECLARED_SOURCE_REVIEW_NATIVE_REPORT_INVALID')
    return {'profile':'declared-source-locator-ambiguity/v1' if legacy else 'ellipsis-source-locator-ambiguity/v1',
            **({} if legacy else {'record_origin':'deterministic controller proof of the bound original worker error; not a native agent message or score'}),
            'worker_source_sha256':SOURCE_WORKER,
            'worker_error_sha256':SOURCE_ERROR if legacy else error_sha,'source_reference_ambiguity_count':3 if legacy else len(parts),
            'business_runtime_unchanged_sha256':digest.hexdigest(),'original_runtime_drift_flag':failed['runtime_workspace']['drifted'],
            'declared_grader_output_files':output_locks}


def evidence(rt, root, state, task):
    attempt = root / task['attempt_path']
    manifest = rt._read_json(attempt / 'attempt-manifest.json')
    if ((task.get('thread') or {}).get('status') != 'COMPLETED'
            or task.get('score') is not None
            or any((attempt / p).exists() for p in ['score.json', 'rule-component.json', 'semantic/semantic-component.json'])):
        raise ValueError('UNRESOLVED_REVIEW_HAS_SCORE_OR_ACTIVE_JUDGE')
    folder = attempt / 'rule-review'
    request = rt._read_json(folder / 'request.json')
    response = rt._read_json(folder / 'response.json')
    audit = rt._read_json(folder / 'audit.json')
    source_review = _declared_source_review(rt,attempt,manifest,audit)
    expected_locks = {k: manifest['digests'][k] for k in LOCK_KEYS}
    if (audit.get('status') != ('completed' if source_review else 'unresolved') or audit.get('numeric_score_assigned') is not False
            or audit.get('identity') != manifest['identity']
            or request.get('identity') != manifest['identity'] or response.get('identity') != manifest['identity']
            or request.get('judge') != manifest['judge'] or response.get('judge') != manifest['judge']
            or request.get('profile') != manifest.get('runtime', {}).get('rule_review_profile')
            or audit.get('profile') != request.get('profile')
            or request.get('input_locks') != expected_locks or audit.get('input_locks') != expected_locks
            or response.get('locks') != {'input_locks': expected_locks,
                                         'request_sha256': rt._sha256_file(folder / 'request.json')}
            or request.get('public_candidate_root') != manifest['paths']['candidate_original']
            or request.get('private_reference_root') != manifest['paths']['gt']):
        raise ValueError('UNRESOLVED_REVIEW_IDENTITY_OR_STATUS_INVALID')
    for key, name in [('request_sha256', 'request.json'), ('response_sha256', 'response.json'),
                      ('query_log_sha256', 'query-log.json'), ('discovery_audit_sha256', 'discovery-audit.json')]:
        if audit.get(key) != rt._sha256_file(folder / name):
            raise ValueError('UNRESOLVED_REVIEW_AUDIT_HASH_MISMATCH')
    expected = [c['id'] for c in request['contexts']]
    decisions = response['decisions']
    observed = [d['context_id'] for d in decisions]
    if (len(set(expected)) != len(expected) or sorted(observed) != sorted(expected)
            or audit.get('reviewed_context_count') != len(expected)):
        raise ValueError('UNRESOLVED_REVIEW_CONTEXT_RANGE_INVALID')
    unresolved = []
    queries = rt._read_json(folder / 'query-log.json')['queries']
    by_query = {q['query_id']: q for q in queries}
    if (len(by_query) != len(queries)
            or any(q.get('request_sha256') != audit['request_sha256'] for q in queries)):
        raise ValueError('UNRESOLVED_REVIEW_QUERY_BINDING_INVALID')
    for decision in decisions:
        ids = decision.get('query_ids', [])
        if (not ids or any(q not in by_query for q in ids)
                or not any(decision['context_id'] in by_query[q]['context_ids'] for q in ids)
                or not isinstance(decision.get('reason'), str) or not decision['reason'].strip()):
            raise ValueError('UNRESOLVED_REVIEW_CITATION_INVALID')
        if decision.get('status') == 'unresolved' and decision.get('passed') is None:
            unresolved.append(decision['context_id'])
        elif decision.get('status') != 'judged' or not isinstance(decision.get('passed'), bool):
            raise ValueError('UNRESOLVED_REVIEW_DECISION_INVALID')
    if (not source_review and not unresolved or source_review and unresolved
            or sorted(unresolved) != sorted(audit.get('unresolved_context_ids', []))):
        raise ValueError('UNRESOLVED_REVIEW_UNRESOLVED_IDS_INVALID')
    discovery = rt._read_json(folder / 'discovery-audit.json')
    if (discovery.get('identity') != manifest['identity'] or discovery.get('profile') != request['profile']
            or discovery.get('provisional_scores_published') is not False
            or discovery.get('request_sha256') != audit['request_sha256']):
        raise ValueError('UNRESOLVED_REVIEW_DISCOVERY_BINDING_INVALID')
    for name, key in [('request.json', 'worker_request_sha256'), ('result.json', 'worker_result_sha256')]:
        if rt._sha256_file(folder / 'discovery/worker' / name) != discovery.get(key):
            raise ValueError('UNRESOLVED_REVIEW_DISCOVERY_HASH_INVALID')
    paths = [attempt / 'attempt-manifest.json', root / task['prompt_path']]
    paths += [p for p in folder.rglob('*') if p.is_file() and 'runtime' not in p.relative_to(folder).parts]
    if source_review:
        paths += [attempt/name for name in ['rule-audit.json','rule-source-correction.json']]
        if source_review['profile']=='declared-source-locator-ambiguity/v1':
            paths.append(attempt/'scoring-attention-report.json')
        paths += [p for p in (attempt/'worker').rglob('*') if p.is_file()]
        paths += [attempt/x['path'] for x in source_review['declared_grader_output_files']]
    locks = []
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('UNRESOLVED_REVIEW_UNSAFE_EVIDENCE')
        locks.append({'path': path.relative_to(root).as_posix(), 'sha256': rt._sha256_file(path)})
    return {'identity': manifest['identity'], 'profile': request['profile'], 'locks': locks,
            'reviewed_context_count': len(expected), 'unresolved_context_count': len(unresolved),
            **({'declared_source_review':source_review} if source_review else {})}


def verify(rt, root, state, task):
    record = task['rule_review_unscored']
    path = root / record['path']
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('UNRESOLVED_REVIEW_PROOF_UNSAFE')
    proof = rt._read_json(path)
    observed = evidence(rt, root, state, task)
    native = proof.get('native_context', {})
    if (task['phase'] != 'UNSCORED' or record.get('kind') != ERROR_KIND
            or proof.get('kind') != ERROR_KIND or rt._sha256_file(path) != record['sha256']
            or any(proof.get(k) != v for k, v in observed.items())
            or proof.get('thread') != task['thread'] or proof.get('score_published') is not False
            or native.get('status') != 'PASS' or native.get('unfinished_turns') != []
            or native.get('thread_id') != task['thread']['thread_id']
            or native.get('model') != state['judge']['model']
            or native.get('effort') != state['judge']['reasoning_effort']
            or native.get('prompt_sha256') != task['prompt_sha256']):
        raise ValueError('UNRESOLVED_REVIEW_PROOF_DRIFT')
    return proof


def record(rt, orchestration_root, *, task_id, reason, sdk_file, now=None):
    root = rt._state_root(orchestration_root)
    state = rt._verify_state(root)
    task = rt._task_by_id(state, rt._identifier(task_id, 'task_id'))
    if task['phase'] != 'SCORE_VERIFICATION_PENDING':
        raise ValueError('UNRESOLVED_REVIEW_PHASE_INVALID')
    observed = evidence(rt, root, state, task)
    rt._run_score_command(state['score_skill'], ['verify', '--attempt-root', str(root / task['attempt_path'])])
    from verify_judge_context import verify_context
    native = verify_context(sdk_file, thread_id=task['thread']['thread_id'],
                            cwd=str((root / task['attempt_path']).resolve()), model=state['judge']['model'],
                            effort=state['judge']['reasoning_effort'],
                            prompt=(root / task['prompt_path']).read_text(encoding='utf-8'))
    proof = {'kind': ERROR_KIND, **observed, 'thread': task['thread'], 'native_context': native,
             'reason': rt._required_string(reason, 'reason'), 'at': rt._timestamp(now or rt._now()),
             'score_published': False, 'original_review_retained': True, 'numeric_score_assigned': False}
    target = root / 'unscored-rule-reviews' / (task['scoring_attempt_id'] + '.json')
    target.parent.mkdir(exist_ok=True)
    rt._write_new_json(target, proof)
    task['rule_review_unscored'] = {'kind': ERROR_KIND, 'path': target.relative_to(root).as_posix(),
                                   'sha256': rt._sha256_file(target)}
    task['phase'] = 'UNSCORED'
    task['history'].append({'at': proof['at'], 'event': 'DECLARED_NATIVE_REVIEW_RETAINED_UNSCORED',
                            **task['rule_review_unscored']})
    verify(rt, root, state, task)
    return rt._save(root, state, now or rt._now())
