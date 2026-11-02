"""Independent adjudication only where Office001 explicitly leaves extraction unknown.

Keep the public numeric interface, original deterministic comparisons and denominator.
Discovery never publishes provisional numeric results. Old attempts have no marker.
"""
from __future__ import annotations
import hashlib
import rule_review

PROFILE = 'office001-numeric-extraction-semantic-review/v1'
TASK = '02_Office_task_001_multi_source_project_report'
SOURCE_SHA = '98d2e59396ce97e43333ce6b164cd1c0073ff023f70e39a3ff90d0272716cec1'
CONTRACT_SHA = 'f6386914c4ab0208f66feb75dbce2a61eccf7a384c289cc3a138ce61b048d11e'


from source_identities import accepted_contracts

def matches(contract, contract_sha=None):
    return (contract.get('task_id') == TASK
        and hashlib.sha256(contract.get('automated_checks', '').encode('utf-8')).hexdigest() == SOURCE_SHA
        and (contract_sha is None or contract_sha in accepted_contracts(CONTRACT_SHA)))


def effective_source(manifest, source, current, prior):
    marker = manifest.get('runtime', {}).get('rule_review_profile')
    if marker != PROFILE:
        return current, prior
    if (not matches({'task_id': manifest.get('identity', {}).get('task_id'), 'automated_checks': source},
                    manifest.get('digests', {}).get('contract_sha256'))
            or manifest.get('judge', {}).get('protocol') != 'codex-agent-judge-v1'):
        raise ValueError('OFFICE001_RULE_REVIEW_PROFILE_MISMATCH')
    # Original `uncertain` branch explicitly says semantic adjudication is required.
    # Only that branch changes. Known observations retain every original comparison.
    old = "                if uncertain:unparsed.append(dict(task_id=tid,field=k,observations=obs))\n                match=bool(obs) and all(number(o['value'])==t[k] for o in obs)"
    new = """                if uncertain:
                    match=_rr_decide({'kind':'office001-numeric-field','task_id':tid,'field':k,
                        'expected':t[k],'observations':obs,'parsed_rows':rows,
                        'candidate_document':doc,'original_extraction_undetermined':True,
                        'instruction':'Check every assertion of this exact field for this task. True only if the original total is explicitly supported, all repeated assertions agree, and no contradiction exists. Explicit omission or incorrect value is false. If evidence remains insufficient, use unresolved rather than guessing.'})
                    numeric+=match
                    if not match:diff.append(dict(task_id=tid,field=k,expected=t[k],observations=obs,
                        independently_reviewed=True))
                    continue
                match=bool(obs) and all(number(o['value'])==t[k] for o in obs)"""
    if current.count(old) != 1:
        raise ValueError('OFFICE001_RULE_REVIEW_SOURCE_ANCHOR_MISMATCH')
    common = rule_review.WRAPPERS.split('_rr_original_impact=', 1)[0].replace(rule_review.PROFILE, PROFILE)
    effective = current.replace(old, new) + common
    receipt = {'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id':PROFILE,'task_id':TASK,'contract_sha256':CONTRACT_SHA,
        'original_source_sha256':SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode('utf-8')).hexdigest(),
        'reason':'只将原规则明确无法抽取的逐任务数值交独立裁判复核；已确定比较、重复陈述一致性、原字段全集、分母、公共等权规则接口及60/40权重不变。未决仍阻断数值发布，原候选不改。',
        'discovery_provisional_scores_publishable':False}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
