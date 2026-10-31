"""Managed discovery and immutable native rulings for declared rule ambiguities."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
import rule_review


def _load(rt, root):
    manifest=rt._read_json(root/'attempt-manifest.json')
    contract=rt._read_json(root/manifest['paths']['contract'])
    if (manifest.get('runtime',{}).get('rule_review_profile') is None
            or manifest['runtime']['rule_review_profile']!=rule_review.profile_for(contract,manifest['digests']['contract_sha256'],frozen_profile=manifest['runtime']['rule_review_profile'])
            or manifest.get('judge',{}).get('protocol')!='codex-agent-judge-v1'):
        raise rt.ScoringRuntimeError('RULE_REVIEW_PROFILE_MISMATCH')
    return manifest,contract


def _locks(manifest):
    return {key:manifest['digests'][key] for key in ['candidate_original_sha256','contract_sha256',
        'task_sha256','private_gt_workspace_sha256','transcript_sha256','execution_record_sha256','judge_config_sha256']}


def _checked_request(rt,root,manifest):
    base=root/'rule-review'
    request=rt._read_json(base/'request.json',code='RULE_REVIEW_REQUEST_INVALID')
    audit=rt._read_json(base/'discovery-audit.json',code='RULE_REVIEW_DISCOVERY_INVALID')
    profile=manifest['runtime']['rule_review_profile']
    if (request.get('schema_version')!=rule_review.REQUEST_SCHEMA or request.get('profile')!=profile
            or request.get('identity')!=manifest['identity'] or request.get('judge')!=manifest['judge']
            or request.get('input_locks')!=_locks(manifest)
            or request.get('public_candidate_root')!=manifest['paths']['candidate_original']
            or request.get('private_reference_root')!=manifest['paths']['gt']
            or audit.get('request_sha256')!=rt._sha256_file(base/'request.json')
            or audit.get('provisional_scores_published') is not False):
        raise rt.ScoringRuntimeError('RULE_REVIEW_SOURCE_DRIFT')
    for name,key in [('request.json','worker_request_sha256'),('result.json','worker_result_sha256')]:
        if rt._sha256_file(base/'discovery/worker'/name)!=audit.get(key):
            raise rt.ScoringRuntimeError('RULE_REVIEW_DISCOVERY_DRIFT',name)
    worker_request=rt._read_json(base/'discovery/worker/request.json')
    worker_result=rt._read_json(base/'discovery/worker/result.json')
    contract=rt._read_json(root/manifest['paths']['contract'])
    source,correction=rt._effective_rule_source(manifest,contract['automated_checks'])
    observed=worker_result.get('rule_review',{})
    if (worker_request.get('automated_checks')!=source
            or worker_request.get('rule_review')!=rule_review.worker_configuration('discover',profile=profile)
            or request.get('source_correction')!=correction
            or observed.get('mode')!='discover' or observed.get('provisional_scores_suppressed') is not True
            or worker_result.get('result')!={} or 'raw_result' in worker_result
            or request.get('contexts')!=[{'id':k,'context':v} for k,v in sorted(observed.get('contexts',{}).items())]):
        raise rt.ScoringRuntimeError('RULE_REVIEW_DISCOVERY_INVALID')
    return request


def prepare(rt, *, attempt_root, runtime_python, playwright_browsers_path=None):
    root=attempt_root.expanduser().resolve(strict=True)
    rt.verify_attempt(root)
    manifest,contract=_load(rt,root)
    runtime_python=rt._absolute_executable(runtime_python,'RUNTIME_PYTHON_UNAVAILABLE')
    target=root/'rule-review'
    if target.exists():
        request=_checked_request(rt,root,manifest)
        return {'status':'PASS','context_count':len(request['contexts']),
                'request_sha256':rt._sha256_file(target/'request.json'),'review_request':str(target/'request.json')}
    target.mkdir()
    discovery=target/'discovery';discovery.mkdir()
    original=rt._resolve_within(root,manifest['paths']['runtime_workspace'],'runtime workspace')
    workspace=discovery/'runtime/workspace'
    workspace.parent.mkdir(parents=True)
    shutil.copytree(original,workspace,symlinks=True)
    suffix=Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace'])
    argument=workspace/suffix
    rt._import_grading_core()
    from wildclawbench_grading_core import inspect_rule_dependencies
    source,correction=rt._effective_rule_source(manifest,contract['automated_checks'])
    transcript=rt._read_transcript(root/manifest['paths']['transcript'])
    completion=None
    if rt._extended_evaluator_inputs(manifest):
        transcript,completion=rt._formal_completion_rule_input(root,manifest,rt._canonical_rule_view(transcript))
        transcript,_=rt._native_context_rule_input(root,manifest,contract,transcript)
    executor=rt._WorkerExecutor(attempt_root=discovery,runtime_python=runtime_python,
        runtime_lock_path=root/manifest['paths']['runtime_lock'],timeout_seconds=120,
        playwright_browsers_path=playwright_browsers_path,
        rule_result_adapter=contract.get('rule_result_adapter'),
        rule_review_configuration=rule_review.worker_configuration('discover',profile=manifest['runtime']['rule_review_profile']))
    executor(source,{'dependencies':inspect_rule_dependencies(source),
                     'workspace_path':str(argument),'transcript':transcript})
    raw=rt._read_json(discovery/'worker/result.json')
    review=raw.get('rule_review',{})
    if (review.get('mode')!='discover' or review.get('provisional_scores_suppressed') is not True
            or raw.get('result')!={} or 'raw_result' in raw or not isinstance(review.get('contexts'),dict)):
        raise rt.ScoringRuntimeError('RULE_REVIEW_DISCOVERY_INVALID')
    contexts=[{'id':key,'context':value} for key,value in sorted(review['contexts'].items())]
    if any(rt._sha256_bytes(json.dumps(item['context'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))!=item['id'] for item in contexts):
        raise rt.ScoringRuntimeError('RULE_REVIEW_CONTEXT_DIGEST_INVALID')
    profile=manifest['runtime']['rule_review_profile']
    instructions='仅复核原规则无法确定的字段等价性/影响关系和补充来源相关性。每项给出passed布尔值和中文证据理由；不直接给规则分、不改变参考要求或候选文件。'
    if profile=='office001-numeric-extraction-semantic-review/v1':
        instructions='仅复核原规则明确无法抽取的任务ID/数值字段。每项根据完整候选、原参考与实际位置判断：原期望数值被明确陈述且全部重复陈述一致为passed=true；可确认遗漏或错误为false；证据不足为unresolved/null。不得把未解析当遗漏，不改分母/权重或已确定比较；控制器不代判。'
    if profile in {'escrow-status-equivalence-review/v1','escrow-status-equivalence-review/v2','escrow-status-equivalence-review/v3'}:
        instructions='只复核原规则声明的逐行状态用语等价性，不把候选错误状态修成GT事实。每个group_id恰一选项true：等价于某个原状态，或保留原词（公开口径下含义明确且不同，供原比较扣分）。含义不明时保留unresolved/null，不猜测、不补值。全部context需实际分页查询并写中文证据理由。'
        if profile in {'escrow-status-equivalence-review/v2','escrow-status-equivalence-review/v3'}:instructions+=' 同表/字段/原词合并的问题列出全部出现位置，必须核对全部使用而不是取多数；同组含义不一致仍unresolved。'
    request={'schema_version':rule_review.REQUEST_SCHEMA,'profile':profile,
        'identity':manifest['identity'],'judge':manifest['judge'],'input_locks':_locks(manifest),
        'contexts':contexts,'source_correction':correction,
        'public_candidate_root':manifest['paths']['candidate_original'],
        'private_reference_root':manifest['paths']['gt'],
        'runtime_python':str(runtime_python),'runtime_python_sha256':rt._sha256_file(runtime_python),
        'playwright_browsers_path':str(playwright_browsers_path) if playwright_browsers_path else None,
        'instructions':instructions}
    rt._write_new_json(target/'request.json',request)
    rt._write_new_json(target/'query-log.json',{'schema_version':'general-e2e-rule-review-query-log/v1','queries':[]})
    rt._write_new_json(target/'response-template.json',{'schema_version':rule_review.RESPONSE_SCHEMA,
        'identity':manifest['identity'],'judge':manifest['judge'],
        'locks':{'request_sha256':rt._sha256_file(target/'request.json'),'input_locks':_locks(manifest)},
        'decisions':[{'context_id':item['id'],'status':'unresolved','passed':None,'reason':'','query_ids':[],
            **({'evidence_locations':[]} if profile=='office001-numeric-extraction-semantic-review/v1' else {})} for item in contexts]})
    rt._remove_tree(discovery/'runtime')
    rt._write_new_json(target/'discovery-audit.json',{'profile':profile,'identity':manifest['identity'],
        'request_sha256':rt._sha256_file(target/'request.json'),'worker_request_sha256':rt._sha256_file(discovery/'worker/request.json'),
        'worker_result_sha256':rt._sha256_file(discovery/'worker/result.json'),'worker':executor.audit,
        'completion':completion,'provisional_scores_published':False,'discovery_runtime_removed':True})
    rt.verify_attempt(root)
    return {'status':'PASS','context_count':len(contexts),'review_request':str(target/'request.json'),
            'request_sha256':rt._sha256_file(target/'request.json')}


def query(rt, *, attempt_root, offset=0, limit=10):
    root=attempt_root.expanduser().resolve(strict=True);rt.verify_attempt(root)
    manifest,_=_load(rt,root);base=root/'rule-review'
    request=_checked_request(rt,root,manifest)
    if request.get('identity')!=manifest['identity'] or request.get('input_locks')!=_locks(manifest):
        raise rt.ScoringRuntimeError('RULE_REVIEW_SOURCE_DRIFT')
    if isinstance(offset,bool) or isinstance(limit,bool) or offset<0 or not 1<=limit<=50:
        raise rt.ScoringRuntimeError('RULE_REVIEW_QUERY_RANGE_INVALID')
    if (base/'audit.json').exists():
        raise rt.ScoringRuntimeError('RULE_REVIEW_ALREADY_TERMINAL')
    items=request['contexts'][offset:offset+limit]
    log=rt._read_json(base/'query-log.json');qid=f"rule-review-query-{len(log['queries'])+1:04d}"
    log['queries'].append({'query_id':qid,'context_ids':[i['id'] for i in items],
                          'request_sha256':rt._sha256_file(base/'request.json')})
    rt._atomic_write_json(base/'query-log.json',log)
    return {'status':'PASS','query_id':qid,'offset':offset,'total':len(request['contexts']),
        'has_more':offset+len(items)<len(request['contexts']),'next_offset':offset+len(items),
        'identity':request['identity'],'judge':request['judge'],'items':items,
        'input_paths':{'candidate':request['public_candidate_root'],'private_reference':request['private_reference_root']}}


def _validate_response(rt, root, manifest, request, response, query_log):
    if (response.get('schema_version')!=rule_review.RESPONSE_SCHEMA
            or response.get('identity')!=manifest['identity'] or response.get('judge')!=manifest['judge']
            or response.get('locks')!={'request_sha256':rt._sha256_file(root/'rule-review/request.json'),
                                      'input_locks':_locks(manifest)}):
        raise rt.ScoringRuntimeError('RULE_REVIEW_RESPONSE_LOCK_MISMATCH')
    rows=response.get('decisions');expected={i['id'] for i in request['contexts']}
    if (not isinstance(rows,list) or len(rows)!=len(expected)
            or {r.get('context_id') for r in rows if isinstance(r,dict)}!=expected):
        raise rt.ScoringRuntimeError('RULE_REVIEW_RESPONSE_SCOPE_MISMATCH')
    queries={q['query_id']:q for q in query_log['queries']}
    for row in rows:
        ids=row.get('query_ids')
        valid_decision=(isinstance(row.get('passed'),bool) and row.get('status','judged')=='judged')
        unavailable=(row.get('passed') is None and row.get('status')=='unresolved')
        if (not (valid_decision or unavailable) or not rt._contains_chinese_explanation(row.get('reason'))
                or not isinstance(ids,list) or not ids or len(ids)!=len(set(ids))
                or any(qid not in queries for qid in ids)
                or row['context_id'] not in {cid for qid in ids for cid in queries[qid]['context_ids']}):
            raise rt.ScoringRuntimeError('RULE_REVIEW_RESPONSE_INVALID',str(row.get('context_id')))
        if request['profile']=='office001-numeric-extraction-semantic-review/v1':
            locations=row.get('evidence_locations')
            if (not isinstance(locations,list) or (valid_decision and not locations)
                    or any(not isinstance(p,str) or not p.strip() or len(p)>1000 for p in locations)):
                raise rt.ScoringRuntimeError('RULE_REVIEW_RESPONSE_INVALID','Office001 requires concrete evidence_locations')
    decisions={row['context_id']:row['passed'] for row in rows}
    if request['profile'] in {'escrow-status-equivalence-review/v1','escrow-status-equivalence-review/v2','escrow-status-equivalence-review/v3'}:
        import escrow_state_review
        try:escrow_state_review.validate_choices(request,decisions)
        except ValueError as exc:raise rt.ScoringRuntimeError('RULE_REVIEW_RESPONSE_INVALID',str(exc)) from exc
    return decisions


def record(rt, *, attempt_root, response_path):
    root=attempt_root.expanduser().resolve(strict=True);rt.verify_attempt(root)
    manifest,_=_load(rt,root);base=root/'rule-review'
    if (base/'audit.json').exists() or (root/'rule-component.json').exists():
        raise rt.ScoringRuntimeError('RULE_REVIEW_ALREADY_TERMINAL')
    request=_checked_request(rt,root,manifest);log=rt._read_json(base/'query-log.json')
    response=rt._read_json(response_path,code='RULE_REVIEW_RESPONSE_INVALID')
    if request.get('input_locks')!=_locks(manifest):
        raise rt.ScoringRuntimeError('RULE_REVIEW_SOURCE_DRIFT')
    decisions=_validate_response(rt,root,manifest,request,response,log)
    unresolved=[key for key,value in decisions.items() if value is None]
    rt._write_new_json(base/'response.json',response)
    rt._write_new_json(base/'audit.json',{'schema_version':'general-e2e-rule-review-audit/v1','profile':manifest['runtime']['rule_review_profile'],
        'identity':manifest['identity'],'status':'unresolved' if unresolved else 'completed','request_sha256':rt._sha256_file(base/'request.json'),
        'response_sha256':rt._sha256_file(base/'response.json'),'query_log_sha256':rt._sha256_file(base/'query-log.json'),
        'discovery_audit_sha256':rt._sha256_file(base/'discovery-audit.json'),
        'reviewed_context_count':len(decisions),'unresolved_context_ids':unresolved,
        'input_locks':_locks(manifest),'numeric_score_assigned':False})
    return {'status':'NEEDS_ATTENTION' if unresolved else 'PASS','reviewed_context_count':len(decisions),
            'unresolved_context_ids':unresolved,'numeric_score_assigned':False}


def application_configuration(rt,root,manifest,contract):
    profile=manifest.get('runtime',{}).get('rule_review_profile')
    if profile is None:return None
    _load(rt,root);base=root/'rule-review'
    audit=rt._read_json(base/'audit.json',code='RULE_REVIEW_NOT_READY')
    if audit.get('status')=='unresolved':
        raise rt.ScoringRuntimeError('RULE_REVIEW_EVIDENCE_INSUFFICIENT',str(audit.get('unresolved_context_ids')))
    request=_checked_request(rt,root,manifest);response=rt._read_json(base/'response.json');log=rt._read_json(base/'query-log.json')
    if (audit.get('status')!='completed' or audit.get('identity')!=manifest['identity']
            or audit.get('input_locks')!=_locks(manifest) or request.get('input_locks')!=_locks(manifest)):
        raise rt.ScoringRuntimeError('RULE_REVIEW_SOURCE_DRIFT')
    for name,key in [('request.json','request_sha256'),('response.json','response_sha256'),
                     ('query-log.json','query_log_sha256'),('discovery-audit.json','discovery_audit_sha256')]:
        if rt._sha256_file(base/name)!=audit.get(key):
            raise rt.ScoringRuntimeError('RULE_REVIEW_AUDIT_DRIFT',name)
    discovery=rt._read_json(base/'discovery-audit.json')
    for name,key in [('request.json','worker_request_sha256'),('result.json','worker_result_sha256')]:
        if rt._sha256_file(base/'discovery/worker'/name)!=discovery.get(key):
            raise rt.ScoringRuntimeError('RULE_REVIEW_DISCOVERY_DRIFT',name)
    decisions=_validate_response(rt,root,manifest,request,response,log)
    return {**rule_review.worker_configuration('apply',decisions,profile=profile),
            'decision_response_sha256':audit['response_sha256'],'decision_audit_sha256':rt._sha256_file(base/'audit.json')}
