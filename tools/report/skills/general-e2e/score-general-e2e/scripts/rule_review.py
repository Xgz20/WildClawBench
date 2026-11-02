"""Declared semantic review inputs for an otherwise deterministic dataset rule."""
from __future__ import annotations
import hashlib
from source_identities import accepted_source_hashes

PROFILE = 'hr-fields-and-sources-semantic-review/v1'
WORKER_SCHEMA = 'wildclawbench.general-e2e-rule-review-worker/v1'
REQUEST_SCHEMA = 'wildclawbench.general-e2e-rule-review-request/v1'
RESPONSE_SCHEMA = 'wildclawbench.general-e2e-rule-review-response/v1'
TASK_ID = '03_Data_Analysis_task_001_hr_worktime_reconciliation'
SOURCE_SHA256 = 'f98e97479b61249f5421b652816d74d39f4d9d3c9b98a6ba4f14fa40b5d2a6d5'
ROW_LOCATOR_PROFILE = 'hr-equivalent-row-prefix-locators/v1'


def matches(contract):
    return (contract.get('task_id') == TASK_ID
            and hashlib.sha256(contract.get('automated_checks', '').encode('utf-8')).hexdigest() in accepted_source_hashes(SOURCE_SHA256))


def profile_for(contract, contract_sha=None, *, frozen_profile=None):
    if matches(contract):
        return PROFILE
    import office001_rule_review
    if office001_rule_review.matches(contract, contract_sha):
        return office001_rule_review.PROFILE
    import escrow_state_review
    if escrow_state_review.matches(contract,contract_sha):
        import escrow_grouped_review
        import escrow_grouped_review_v2
        if frozen_profile in {escrow_state_review.PROFILE,escrow_grouped_review_v2.PROFILE,escrow_grouped_review.PROFILE}:
            return frozen_profile
        return escrow_grouped_review.PROFILE
    return None


def worker_configuration(mode, decisions=None, *, profile=PROFILE):
    if mode not in {'discover','apply'}:
        raise ValueError('RULE_REVIEW_MODE_INVALID')
    if profile not in {PROFILE, 'office001-numeric-extraction-semantic-review/v1','escrow-status-equivalence-review/v1','escrow-status-equivalence-review/v2','escrow-status-equivalence-review/v3'}:
        raise ValueError('RULE_REVIEW_PROFILE_MISMATCH')
    return {'schema_version': WORKER_SCHEMA, 'profile': profile, 'mode': mode, 'decisions': decisions or {}}


WRAPPERS = r'''

import hashlib as _rr_hashlib
import json as _rr_json

def _rr_normalize(value):
    if isinstance(value, dict):
        return {str(k):_rr_normalize(v) for k,v in sorted(value.items(),key=lambda p:str(p[0]))}
    if isinstance(value,(list,tuple)):
        return [_rr_normalize(v) for v in value]
    if isinstance(value,(set,frozenset)):
        return sorted((_rr_normalize(v) for v in value),key=lambda v:_rr_json.dumps(v,ensure_ascii=False,sort_keys=True))
    if value is None or isinstance(value,(str,bool,int,float)):
        return value
    return str(value)

def _rr_decide(context):
    state=globals().get('_GENERAL_E2E_RULE_REVIEW')
    if not isinstance(state,dict) or state.get('profile')!='hr-fields-and-sources-semantic-review/v1':
        raise RuntimeError('RULE_REVIEW_NOT_PREPARED')
    context=_rr_normalize(context)
    digest=_rr_hashlib.sha256(_rr_json.dumps(context,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    observations=state.setdefault('observations',{})
    if len(observations)>=10000 and digest not in observations:
        raise RuntimeError('RULE_REVIEW_CONTEXT_LIMIT')
    observations[digest]=context
    if state['mode']=='discover':
        return False  # Discovery only: the Worker suppresses every provisional score.
    decision=state.get('decisions',{}).get(digest)
    if not isinstance(decision,bool):
        raise RuntimeError('RULE_REVIEW_DECISION_MISSING:'+digest)
    state.setdefault('applied',[]).append(digest)
    return decision

_rr_original_impact=check_impact_fields
def check_impact_fields(candidate_value,reference_row,daily_row=None):
    result=_rr_original_impact(candidate_value,reference_row,daily_row)
    if result.get('passed') is None:
        result=dict(result)
        result['passed']=_rr_decide({'kind':'impact-fields','candidate_value':candidate_value,
            'reference_row':reference_row,'daily_row':daily_row,'original_diagnostic':result})
    return result

_rr_original_sources=check_source_evidence
def check_source_evidence(table_name,reference_row,expected_refs,actual_refs,context):
    result=_rr_original_sources(table_name,reference_row,expected_refs,actual_refs,context)
    if result.get('passed') is None:
        result=dict(result)
        result['passed']=_rr_decide({'kind':'source-relevance','table_name':table_name,
            'reference_row':reference_row,'expected_refs':expected_refs,'actual_refs':actual_refs,
            'original_diagnostic':result})
    return result
'''


def effective_source(source, *, source_row_aliases=False):
    observed_source_sha = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if observed_source_sha not in accepted_source_hashes(SOURCE_SHA256):
        raise ValueError('RULE_REVIEW_SOURCE_MISMATCH')
    parsed_source=source
    if source_row_aliases:
        anchor='        if not match:\n            match = re.fullmatch(r"\\['
        fallback=r'''        if not match:
            match = re.fullmatch(r"(.+?\.xlsx)\s*[#|｜]\s*'?(.+?)'?\s*[!|｜]\s*行\s*()(\d+)", segment)
'''
        if source.count(anchor)!=1:
            raise ValueError('HR_ROW_LOCATOR_SOURCE_MISMATCH')
        parsed_source=source if fallback in source else source.replace(anchor,fallback+anchor)
    effective=parsed_source+WRAPPERS
    return effective, {'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id':PROFILE,'task_id':TASK_ID,'original_source_sha256':observed_source_sha,
        'effective_source_sha256':hashlib.sha256(effective.encode('utf-8')).hexdigest(),
        'reason':'仅将原规则明确标记需语义复核的字段和来源交由独立裁判判断，随后执行原数值计分；原确定性判定、检查点、分母及78/22权重不变。',
        **({'source_locator_profile':ROW_LOCATOR_PROFILE,
            'source_locator_reason':'仅将公开允许的同一物理行定位“文件.xlsx#工作表!行N”解析为原行号；排班仍须具体日期单元格，原存在性、相关性和计分函数不变。'} if source_row_aliases else {}),
        'discovery_provisional_scores_publishable':False}
