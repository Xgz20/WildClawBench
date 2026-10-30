"""Response-bound arithmetic checks through the existing managed rule Worker."""
from pathlib import Path
import json
import os
import sys
import business_capability


def _inputs(rt, root, response_path):
    rt.verify_attempt(root)
    manifest = rt._read_json(root/'attempt-manifest.json')
    contract = rt._read_json(root/manifest['paths']['contract'])
    policy = business_capability.policy(manifest, contract)
    if policy is None or policy['profile'] != 'independent-business-capability/v2':
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_PROFILE_REQUIRED')
    supplied=Path(os.path.abspath(response_path.expanduser()))
    if supplied.is_symlink() or not supplied.is_file():
        raise rt.ScoringRuntimeError('SEMANTIC_RESPONSE_PATH_INVALID')
    response_path = supplied.resolve(strict=True)
    if root not in response_path.parents:
        raise rt.ScoringRuntimeError('SEMANTIC_RESPONSE_PATH_INVALID')
    raw = response_path.read_bytes(); response = json.loads(raw.decode('utf-8'))
    request = rt._read_json(root/'semantic/request.json')
    if (response.get('identity') != manifest['identity'] or response.get('judge') != manifest['judge']
            or request.get('completion_policy') != policy):
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_IDENTITY_MISMATCH')
    general = business_capability.general_module()
    catalog=rt._read_json(root/'semantic/evidence-catalog.json');queries=rt._read_json(root/'semantic/query-log.json')['queries']
    expected_locks={'request_sha256':rt._sha256_file(root/'semantic/request.json'),
                    'evidence_catalog_sha256':rt._sha256_file(root/'semantic/evidence-catalog.json'),
                    'evidence_index_digest':catalog['evidence_index']['digest'],'rubric_sha256':request['rubric']['sha256']}
    if response.get('locks')!=expected_locks:
        raise rt.ScoringRuntimeError('SEMANTIC_RESPONSE_LOCK_MISMATCH')
    general.validate_auxiliary(response,response['criteria'],catalog,queries,policy)
    arguments, placeholders = general.helper_arguments(policy, response)
    source = general.worker_source(contract['automated_checks'], arguments)
    locks = {'response_sha256':rt._sha256_bytes(raw),
             'attempt_manifest_sha256':rt._sha256_file(root/'attempt-manifest.json'),
             'request_sha256':rt._sha256_file(root/'semantic/request.json'),
             'query_log_sha256':rt._sha256_file(root/'semantic/query-log.json'),
             'source_sha256':rt._sha256_bytes(source.encode('utf-8'))}
    check_id = rt._sha256_bytes(json.dumps(locks, sort_keys=True, separators=(',', ':')).encode())
    directory = root/'semantic/aggregation-checks'/check_id
    return manifest, policy, arguments, placeholders, source, locks, directory


def check(rt, *, attempt_root, response_path, runtime_python):
    root = attempt_root.expanduser().resolve(strict=True)
    manifest, policy, arguments, placeholders, source, locks, directory = _inputs(rt, root, response_path)
    if (directory/'proof.json').exists():
        return verify(rt, root=root, response_path=response_path)
    if directory.exists():
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_PRIOR_FAILURE_RETAINED', str(directory))
    directory.mkdir(parents=True); workspace = directory/'workspace';workspace.mkdir()
    runtime_python = rt._absolute_executable(runtime_python, 'RUNTIME_PYTHON_UNAVAILABLE')
    if os.path.abspath(runtime_python)!=os.path.abspath(sys.executable):
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_FROZEN_PYTHON_MISMATCH')
    rt._import_grading_core()
    from wildclawbench_grading_core import inspect_rule_dependencies
    executor = rt._WorkerExecutor(attempt_root=directory, runtime_python=runtime_python,
        runtime_lock_path=root/manifest['paths']['runtime_lock'], timeout_seconds=120, playwright_browsers_path=None,
        rule_result_adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1',
                             'diagnostic_keys':['diagnostics']})
    executor(source, {'dependencies':inspect_rule_dependencies(source),
                      'workspace_path':str(workspace), 'transcript':[]})
    result = rt._read_json(directory/'worker/result.json')
    original = result.get('raw_result', {}).get('diagnostics', {}).get('aggregation_review')
    if result.get('result') != {} or not isinstance(original, dict):
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_NOT_VALIDATION_ONLY')
    proof = {'schema':'managed-semantic-aggregation-check/v1','identity':manifest['identity'],
             'locks':locks,'arguments':arguments,'placeholder_keys':placeholders,
             'provisional_values_publishable':False,'original_result':original,'worker':executor.audit,
             'worker_files':{name:rt._sha256_file(directory/'worker'/name)
                             for name in ['request.json','result.json','stdout.log','stderr.log']}}
    rt._write_new_json(directory/'proof.json', proof)
    return verify(rt, root=root, response_path=response_path)


def verify(rt, *, root, response_path):
    manifest, policy, arguments, placeholders, source, locks, directory = _inputs(rt, root, response_path)
    proof = rt._read_json(directory/'proof.json', code='SEMANTIC_AGGREGATION_CHECK_REQUIRED')
    if (proof.get('schema') != 'managed-semantic-aggregation-check/v1'
            or proof.get('identity') != manifest['identity'] or proof.get('locks') != locks
            or proof.get('arguments') != arguments or proof.get('placeholder_keys') != placeholders
            or proof.get('provisional_values_publishable') is not False):
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_PROOF_DRIFT')
    for name in ['request.json','result.json','stdout.log','stderr.log']:
        if rt._sha256_file(directory/'worker'/name) != proof['worker_files'].get(name):
            raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_WORKER_DRIFT', name)
    request = rt._read_json(directory/'worker/request.json');result=rt._read_json(directory/'worker/result.json')
    audit = proof.get('worker', {})
    if (request.get('automated_checks') != source or request.get('transcript') != []
            or request.get('rule_result_adapter') != {'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics']}
            or result.get('ok') is not True or result.get('result') != {}
            or result.get('raw_result') != {'diagnostics':{'aggregation_review':proof.get('original_result')}}
            or audit.get('request_sha256')!=proof['worker_files']['request.json']
            or audit.get('stdout_sha256')!=proof['worker_files']['stdout.log']
            or audit.get('stderr_sha256')!=proof['worker_files']['stderr.log']
            or audit.get('return_code') != 0 or audit.get('timed_out') is not False
            or audit.get('log_too_large') is not False or audit.get('process_tree_cleanup',{}).get('remaining')):
        raise rt.ScoringRuntimeError('SEMANTIC_AGGREGATION_WORKER_INVALID')
    return {'status':'PASS','proof_path':directory.relative_to(root).as_posix()+'/proof.json',
            'proof_sha256':rt._sha256_file(directory/'proof.json'),
            'original_result':proof['original_result'],'placeholder_keys':placeholders,
            'provisional_values_publishable':False}
