"""Retain known, unscored source failures; never rerun the frozen rule worker."""
import hashlib

ERROR_KIND = 'registered-rule-source-implementation-failure/v1'
ROWS = {
    '01_Information_Search_Organization_task_001_acl2024_long_context_qa': (
        'e9917777a34520b691e3d9ef8cc23887c712a11a3baca8e7108df3d2ec7aadfe',
        'b80e8169171e514cc4902613e1cda020fb99076c6fe412d7c45b907f1dc29afe',
        'RULES_NEEDS_ATTENTION', 'worker', 'ValueError',
        'PDF_VERSION_REVIEW_REQUIRED: a paper identity matches but the PDF differs from frozen accepted versions; audit the version before scoring: pdfs/docmath-eval_2024.acl-long.852.pdf'),
    '02_Office_task_010_warranty_recovery_allocation': (
        '6d5fe2fc821cfa1cbf9e1a686ec05e8f9b696b7e4b80def75ecbe934743446aa',
        '5b734e764fc73422f656b579feed386d41c9bd49ec4437568a8e37e4363bb810',
        'RULES_RUNNING', 'rule-review/discovery/worker', 'EvaluationError',
        '未支持的命名区域或外部引用'),
    '02_Office_task_015_procurement_reconciliation': (
        '64ba6743b737870353efc5aebec923ae82f018b6d8bf36583709b142d5515a34',
        '7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b',
        'RULES_NEEDS_ATTENTION', 'worker', 'TypeError',
        'Object of type datetime is not JSON serializable'),
}


def evidence(rt, attempt, manifest, contract, task):
    row = ROWS.get(contract.get('task_id'))
    if row is None:
        raise ValueError('RULE_SOURCE_FAILURE_UNREGISTERED')
    contract_sha, source_sha, _, worker_path, error_type, message = row
    if (manifest.get('digests', {}).get('contract_sha256') != contract_sha
            or manifest.get('dataset', {}).get('id') != 'general-custom70-v4'
            or hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() != source_sha
            or task.get('thread') is not None or task.get('score') is not None
            or any((attempt / p).exists() for p in ('score.json', 'rule-component.json', 'semantic'))):
        raise ValueError('RULE_SOURCE_FAILURE_IDENTITY_OR_JUDGE_INVALID')
    request = rt._read_json(attempt / worker_path / 'request.json')
    result = rt._read_json(attempt / worker_path / 'result.json')
    error = result.get('error') or {}
    request_sha=hashlib.sha256(request.get('automated_checks', '').encode()).hexdigest()
    counta_failure=(contract.get('task_id')=='02_Office_task_010_warranty_recovery_allocation'
        and request_sha=='3dd95a03d0ac5406d80316cc9d86aecdcc4d84b1ae7096c6aa99e99b4ae6019b'
        and error.get('type')=='EvaluationError' and error.get('message')=='未支持的未缓存公式函数：COUNTA'
        and manifest.get('runtime',{}).get('shared_rule_source_repair',{}).get('profile')=='warranty-whole-column-aggregates/v1')
    original_failure=(request_sha==source_sha and error.get('type')==error_type and error.get('message')==message)
    if (not (original_failure or counta_failure)
            or result.get('ok') is not False or result.get('result') is not None
            ):
        raise ValueError('RULE_SOURCE_FAILURE_SIGNATURE_INVALID')
    if worker_path == 'worker':
        audit = rt._read_json(attempt / 'rule-audit.json')
        if (audit.get('identity') != manifest.get('identity') or audit.get('status') != 'failed'
                or audit.get('worker', {}).get('request_sha256') != rt._sha256_file(attempt / worker_path / 'request.json')
                or audit.get('worker', {}).get('process_tree_cleanup', {}).get('remaining') is not False):
            raise ValueError('RULE_SOURCE_FAILURE_AUDIT_INVALID')
    else:
        if (request.get('rule_review') != {'schema_version': 'wildclawbench.general-e2e-rule-review-worker/v1',
                'profile': 'warranty-recovery-reason-semantic-review/v1', 'mode': 'discover', 'decisions': {}}
                or any((attempt / p).exists() for p in ('rule-audit.json', 'worker/result.json',
                    'rule-review/request.json', 'rule-review/discovery-audit.json'))):
            raise ValueError('RULE_SOURCE_FAILURE_DISCOVERY_INVALID')
    return result


def expected_phase(task_id):
    return ROWS[task_id][2]
