"""Retain known, unscored source failures; never rerun the frozen rule worker."""
import hashlib
import json

ERROR_KIND = 'registered-rule-source-implementation-failure/v1'
HR_TASK = '03_Data_Analysis_task_001_hr_worktime_reconciliation'
HR_CONTRACT = '853ffd362d034b56e142c8102a02a4664bebd304a6228f4e1bb4ee04a869364e'
HR_SOURCE = '13c5130e0292799e066d59c2076f3ed2a050650c61572fa3cec3266d97dca69a'
HR_REQUEST_SOURCE = '86946fcc9d801277522f16d09c319928e886ca9623e3af6247370bad445a331e'
HR_V1_REQUEST_SOURCE = 'f0c1dd50d8f8e0dd4bfbe222db76ef067ed6757c1673c60cd6fd049033517f56'
HR_V1_MARKER = {'profile':'hr-native-time-evidence-serialization/v1',
                'source_sha256':HR_SOURCE,
                'current_source_sha256':'0dcea3cc4cc7d9dcdbd66e6824a3732ee7b5c98475cadecf2a26a175c4897cd4'}
ESCROW_TASK = '03_Data_Analysis_task_010_contract_escrow_refund_reconciliation'

def _escrow_locator_evidence(rt,attempt,manifest,contract,task):
    profile=manifest.get('runtime',{}).get('rule_review_profile')
    repair=manifest.get('runtime',{}).get('shared_rule_source_repair')
    locator_marker={'profile':'escrow-equivalent-row-prefix-locators/v1',
        'source_sha256':'a16b0e1b172dd17536f754d1f5c506a3220facfec584a0d6efc16ed85006c22d',
        'current_source_sha256':'47656f9572199c91454cd69bf31a8dc2506e621be645c4eea654c3a585b2a40e'}
    if profile=='escrow-status-equivalence-review/v4' and repair is None:
        expected_source='229174ad3b86aed9a62f7e9281ceddcb4b55334b21c7df1df108c49231bc3f27'
        expected_error='b1e634110ac6aae1a2a0118edd1c0de788cbf229180987f626cc8ec079c065c1';count=1081
    elif profile=='escrow-status-equivalence-review/v5' and repair==locator_marker:
        expected_source='11d32fde4844d264db3f1c7e15d351dc3ca5bdd40344bd468541f7e04275a981'
        expected_error='d82a1f4d2da4ce881ecd39f77e01b635267ebb398d279933e3bdfbbcb6e7d3af';count=1127
    else:
        raise ValueError('ESCROW_LOCATOR_FAILURE_PROFILE_INVALID')
    if (manifest.get('identity',{}).get('task_id')!=ESCROW_TASK
            or manifest.get('digests',{}).get('contract_sha256')!='c93e50e83a8ac8eb9d6ba9e02510a762952b4011e8495c763073029a42bfff75'
            or manifest.get('dataset')!={'id':'general-custom70-v4','digest':'914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'}
            or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!='a16b0e1b172dd17536f754d1f5c506a3220facfec584a0d6efc16ed85006c22d'
            or (task.get('thread') or {}).get('status')!='COMPLETED' or task.get('score') is not None
            or any((attempt/p).exists() for p in ['score.json','rule-component.json','semantic/semantic-component.json'])):
        raise ValueError('ESCROW_LOCATOR_FAILURE_IDENTITY_OR_PHASE_INVALID')
    request=rt._read_json(attempt/'worker/request.json');result=rt._read_json(attempt/'worker/result.json')
    audit=rt._read_json(attempt/'rule-audit.json');review=rt._read_json(attempt/'rule-review/audit.json')
    blocker=rt._read_json(attempt/'scoring-infrastructure-blocker.json')
    blocker_identity=(blocker if count==1081 else blocker.get('identity',{}))
    blocker_error=(blocker.get('error_code') if count==1081 else blocker.get('error',{}).get('code'))
    blocker_unpublished=(blocker.get('formal_score_generated') if count==1081 else blocker.get('formal_score_completed'))
    if (hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=expected_source
            or result.get('ok') is not False or result.get('result') is not None
            or result.get('error',{}).get('type')!='RuntimeError'
            or hashlib.sha256(result.get('error',{}).get('message','').encode()).hexdigest()!=expected_error
            or audit.get('status')!='failed' or audit.get('identity')!=manifest['identity']
            or audit.get('worker',{}).get('request_sha256')!=rt._sha256_file(attempt/'worker/request.json')
            or audit.get('worker',{}).get('process_tree_cleanup',{}).get('remaining') is not False
            or review.get('status')!='completed' or review.get('numeric_score_assigned') is not False
            or review.get('reviewed_context_count')!=count or review.get('unresolved_context_ids')!=[]
            or review.get('identity')!=manifest['identity'] or review.get('profile')!=profile
            or blocker_identity.get('task_id')!=ESCROW_TASK or blocker_identity.get('scoring_attempt_id')!=manifest['identity']['scoring_attempt_id']
            or blocker_error!='RULE_WORKER_FAILED' or blocker_unpublished is not False):
        raise ValueError('ESCROW_LOCATOR_FAILURE_SIGNATURE_INVALID')
    for key,name in [('request_sha256','request.json'),('response_sha256','response.json'),
                     ('query_log_sha256','query-log.json'),('discovery_audit_sha256','discovery-audit.json')]:
        if review.get(key)!=rt._sha256_file(attempt/'rule-review'/name):
            raise ValueError('ESCROW_LOCATOR_REVIEW_DRIFT')
    return result

def registered(task_id):
    return task_id in ROWS or task_id in {HR_TASK,ESCROW_TASK}

def _hr_evidence(rt, attempt, manifest, contract, task):
    if (manifest.get('identity',{}).get('task_id') != HR_TASK
            or manifest.get('digests',{}).get('contract_sha256') != HR_CONTRACT
            or manifest.get('dataset') != {'id':'general-custom70-v4','digest':'914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'}
            or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest() != HR_SOURCE
            or manifest.get('runtime',{}).get('rule_review_profile') != 'hr-fields-and-sources-semantic-review/v1'
            or manifest.get('runtime',{}).get('hr_source_locator_profile') != 'hr-equivalent-row-prefix-locators/v1'
            or task.get('thread') is not None or task.get('score') is not None
            or any((attempt/p).exists() for p in ['score.json','rule-component.json','semantic','rule-audit.json',
                'worker/result.json','rule-review/request.json','rule-review/discovery-audit.json'])):
        raise ValueError('HR_TIME_FAILURE_IDENTITY_OR_PHASE_INVALID')
    request=rt._read_json(attempt/'rule-review/discovery/worker/request.json')
    result=rt._read_json(attempt/'rule-review/discovery/worker/result.json')
    profile=manifest.get('runtime',{}).get('shared_rule_source_repair')
    if profile is None:
        expected_source=HR_REQUEST_SOURCE;message='无法输出证据类型：time'
    elif profile==HR_V1_MARKER:
        expected_source=HR_V1_REQUEST_SOURCE;message='Object of type time is not JSON serializable'
    else:
        raise ValueError('HR_TIME_FAILURE_PROFILE_INVALID')
    if (hashlib.sha256(request.get('automated_checks','').encode()).hexdigest() != expected_source
            or request.get('rule_review') != {'schema_version':'wildclawbench.general-e2e-rule-review-worker/v1',
                'profile':'hr-fields-and-sources-semantic-review/v1','mode':'discover','decisions':{}}
            or result.get('ok') is not False or result.get('result') is not None
            or result.get('error',{}).get('type') != 'TypeError'
            or result.get('error',{}).get('message') != message):
        raise ValueError('HR_TIME_FAILURE_SIGNATURE_INVALID')
    return result

def partial_evidence_paths(attempt, task_id):
    if task_id != HR_TASK:
        return []
    base=attempt/'rule-review/discovery/runtime/workspace/评分证据'
    names=['01候选分析全文.json','02候选核对记录.json','03部门及身份对照.json']
    manifest=attempt/'attempt-manifest.json'
    if manifest.is_file():
        profile=json.loads(manifest.read_text(encoding='utf-8')).get('runtime',{}).get('shared_rule_source_repair')
        if profile==HR_V1_MARKER:
            names+=['00证据说明.json','04规则诊断及材料摘要.json','05异常类别与样本.json']
    if base.is_symlink() or not base.is_dir() or sorted(p.name for p in base.iterdir()) != sorted(names):
        raise ValueError('HR_TIME_PARTIAL_EVIDENCE_INVALID')
    paths=[base/name for name in names]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('HR_TIME_PARTIAL_EVIDENCE_INVALID')
    return paths
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
    if contract.get('task_id') == ESCROW_TASK:
        return _escrow_locator_evidence(rt,attempt,manifest,contract,task)
    if contract.get('task_id') == HR_TASK:
        return _hr_evidence(rt,attempt,manifest,contract,task)
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
    profile=manifest.get('runtime',{}).get('shared_rule_source_repair',{})
    if (contract.get('task_id')=='02_Office_task_015_procurement_reconciliation'
            and profile.get('profile')=='procurement-date-and-section-extraction/v2'
            and profile.get('current_source_sha256')=='34cd4dae061555354dea38a62146b4f1b833423837d2898ac30720470e02f3df'):
        audit=rt._read_json(attempt/'rule-audit.json')
        correction=rt._read_json(attempt/'rule-source-correction.json')
        if (audit.get('status')!='failed' or audit.get('identity')!=manifest.get('identity')
                or audit.get('worker') is not None or (attempt/'worker').exists()
                or audit.get('runtime_workspace',{}).get('drifted') is not False
                or audit.get('error')!={'code':'RULE_ENTRYPOINT_INVALID',
                    'message':'automated_checks must define exactly one synchronous grade() function'}
                or correction.get('effective_source_sha256')!=profile['current_source_sha256']
                or audit.get('source_correction')!={'path':'rule-source-correction.json',
                    'sha256':rt._sha256_file(attempt/'rule-source-correction.json')}):
            raise ValueError('RULE_SOURCE_PREWORKER_FAILURE_INVALID')
        return {'worker_never_started':True}
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
    if task_id == ESCROW_TASK:
        return 'SCORE_VERIFICATION_PENDING'
    if task_id == HR_TASK:
        return 'RULES_RUNNING'
    return ROWS[task_id][2]
