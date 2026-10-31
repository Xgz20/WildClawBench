"""Preserve Office001's explicitly continuous original semantic rubric in new attempts."""
from __future__ import annotations
from copy import deepcopy
import hashlib

PROFILE='office001-original-continuous-semantic-ranges/v1'
TASK='02_Office_task_001_multi_source_project_report'
CONTRACT_SHA='f6386914c4ab0208f66feb75dbce2a61eccf7a384c289cc3a138ce61b048d11e'
SOURCE_SHA='98d2e59396ce97e43333ce6b164cd1c0073ff023f70e39a3ff90d0272716cec1'
RUBRIC_SHA='ea0636af04b4a882ee7a250a429a9a012fa6729996367f2ae6318b961cb4c16c'
KEYS=['c2_source_links','c3_fidelity','c6_readability','c7_self_verification']


def marker(contract,contract_sha):
    if (contract.get('task_id')!=TASK or contract_sha!=CONTRACT_SHA
            or hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()!=SOURCE_SHA
            or hashlib.sha256(contract.get('llm_judge_rubric','').encode('utf-8')).hexdigest()!=RUBRIC_SHA):
        return None
    return {'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'source_sha256':SOURCE_SHA,
        'rubric_sha256':RUBRIC_SHA,'continuous_criteria':list(KEYS),'range':[0.,1.]}


def apply(manifest,contract,criteria):
    frozen=manifest.get('runtime',{}).get('semantic_score_range_profile')
    if frozen is None:return criteria
    expected=marker(contract,manifest.get('digests',{}).get('contract_sha256'))
    if (expected is None or frozen!=expected or manifest.get('judge',{}).get('protocol')!='codex-agent-judge-v1'):
        raise ValueError('OFFICE001_SEMANTIC_RANGE_PROFILE_MISMATCH')
    result=deepcopy(criteria)
    if {r['key'] for r in result}!={'c1_substance','c4_no_fabrication',*KEYS}:
        raise ValueError('OFFICE001_SEMANTIC_RANGE_CRITERIA_MISMATCH')
    for item in result:
        if item['key'] in KEYS:
            if '**Score (0, 1)**:' not in item['rubric']:
                raise ValueError('OFFICE001_SEMANTIC_RANGE_DECLARATION_MISSING')
            item['allowed_scores']=None
            item['score_range']=[0.,1.]
    return result
