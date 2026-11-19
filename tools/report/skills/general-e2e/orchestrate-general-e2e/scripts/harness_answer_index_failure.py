"""Retain the exact pre-judge v1 missing answer-event-index Worker failure."""
import hashlib

ERROR_KIND = 'verified-harness-answer-index-export-failure/v1'
TASK = '01_Information_Search_Organization_task_003_batch_normalization_claim_verification'
CONTRACT = '76aa00cb066778eaf57b43babf379d2577a552e98ea3e6a0c57b17ca4afd1bba'
SOURCE = '72b3b431266c343e782736efe2b433c85c3595f5ff7ff2d37e3f784443ae9dcb'
PROFILE = 'verified-harness-failure-answer-not-provided/v1'
GUARD = "    if not completed:\n        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')"
REPLACEMENT = """    if not completed:
        return '',{'status':'verified_harness_failure_answer_not_provided',
                  'delivery_profile':'verified-harness-failure-answer-not-provided/v1',
                  'formal_answer_evidence':'not_provided','original_process_preserved':True}"""

def evidence(rt, attempt, manifest, contract, task):
    source = contract.get('automated_checks', '')
    if (contract.get('task_id') != TASK or manifest.get('dataset', {}).get('id') != 'general-custom70-v6'
        or manifest.get('dataset', {}).get('digest') != '20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'
        or manifest.get('digests', {}).get('contract_sha256') != CONTRACT
        or manifest.get('evidence_admission') != 'verified-harness-failure-evidence/v1'
        or hashlib.sha256(source.encode()).hexdigest() != SOURCE
        or manifest.get('runtime', {}).get('interrupted_answer_delivery_profile') != {
            'profile': PROFILE, 'contract_sha256': CONTRACT, 'source_sha256': SOURCE}
        or task.get('phase') not in {'RULES_NEEDS_ATTENTION', 'UNSCORED'}
        or task.get('thread') is not None or task.get('score') is not None
        or any((attempt / p).exists() for p in ['score.json', 'rule-component.json', 'semantic'])):
        raise ValueError('HARNESS_ANSWER_INDEX_FAILURE_SCOPE_INVALID')
    audit = rt._read_json(attempt / 'rule-audit.json')
    worker = rt._read_json(attempt / 'worker/result.json')
    request_path = attempt / 'worker/request.json'
    request = rt._read_json(request_path)
    correction_path = attempt / 'rule-source-correction.json'
    correction = rt._read_json(correction_path)
    expected = source.replace(GUARD, REPLACEMENT, 1)
    if (source.count(GUARD) != 1 or request.get('automated_checks') != expected
        or audit.get('status') != 'failed' or audit.get('error') != {'code': 'RULE_WORKER_FAILED', 'detail': "'event_index'"}
        or audit.get('runtime_workspace', {}).get('drifted') is not False
        or audit.get('worker', {}).get('return_code') != 1
        or audit.get('worker', {}).get('timed_out') is not False
        or audit.get('worker', {}).get('process_tree_cleanup', {}).get('remaining') is not False
        or audit.get('worker', {}).get('request_sha256') != rt._sha256_file(request_path)
        or worker.get('ok') is not False or worker.get('result') is not None
        or worker.get('error', {}).get('type') != 'KeyError'
        or worker.get('error', {}).get('message') != "'event_index'"
        or worker.get('worker', {}).get('pid') != audit.get('worker', {}).get('worker_pid')
        or audit.get('source_correction', {}).get('sha256') != rt._sha256_file(correction_path)
        or correction.get('correction_id') != PROFILE
        or correction.get('effective_source_sha256') != hashlib.sha256(expected.encode()).hexdigest()):
        raise ValueError('HARNESS_ANSWER_INDEX_FAILURE_PROOF_INVALID')
    return {'kind': ERROR_KIND, 'contract_sha256': CONTRACT, 'source_sha256': SOURCE,
            'worker': worker['worker'], 'native_judge_created': False,
            'numeric_score_assigned': False, 'original_candidate_changed': False}
