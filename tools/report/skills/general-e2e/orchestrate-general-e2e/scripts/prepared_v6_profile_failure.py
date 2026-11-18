"""Retain an exact v6 quote preparation missing its registered input profile."""
import hashlib
import sterilization_quote_complete_layout as quote

ERROR_KIND='prepared-v6-rule-profile-registration-repair/v1'

def evidence(rt,attempt,manifest,contract,task):
    expected=quote.marker(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{}))
    if (manifest.get('identity',{}).get('task_id')!=quote.TASK or manifest.get('dataset')!=quote.V6_DATASET
            or expected is None or manifest.get('runtime',{}).get('sterilization_quote_layout_profile') is not None
            or task.get('phase') not in {'RULES_READY','UNSCORED'}
            or task.get('thread') is not None or task.get('score') is not None
            or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=quote.SOURCE
            or any((attempt/name).exists() for name in ['worker','rule-review','semantic','grader-evidence',
                'rule-component.json','rule-audit.json','rule-source-correction.json','score.json'])):
        raise ValueError('PREPARED_V6_PROFILE_FAILURE_INVALID')
    return {'profile':ERROR_KIND,'dataset':quote.V6_DATASET,'contract_sha256':quote.CONTRACT,
            'source_sha256':quote.SOURCE,'missing_profile_key':'sterilization_quote_layout_profile',
            'expected_registered_profile':expected,'worker_never_started':True,
            'process_created':False,'native_judge_created':False,'numeric_score_assigned':False}
