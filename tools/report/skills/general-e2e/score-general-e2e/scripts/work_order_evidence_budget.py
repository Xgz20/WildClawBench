"""Keep the original deterministic chunker; increase only its total resource budget."""
import hashlib

PROFILE='work-order-complete-evidence-budget/v1'
TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT_SHA='c44c983d8373f7075baeee65e327cf886ed2931368b8a59dcd8dae5d484d6cc1'
SOURCE_SHA='fab46597d51de9869feeef882eaa222b9ced1ecc8809ad10c7a8fa1be697bfac'

def marker(contract,contract_sha):
    if (contract.get('task_id')==TASK and contract_sha==CONTRACT_SHA
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'source_sha256':SOURCE_SHA,'total_utf8_bytes':16777216,'truncation_allowed':False}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('work_order_evidence_budget_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'])
    if expected is None or frozen!=expected:raise ValueError('WORK_ORDER_BUDGET_PROFILE_MISMATCH')
    old='    total=sum(len(v) for v in serialized.values())\n    if total>70000:'
    new="    total=sum(len(v.encode('utf-8')) for v in serialized.values())\n    if total>16777216:"
    if current.count(old)!=1:raise ValueError('WORK_ORDER_BUDGET_SOURCE_SPAN_MISMATCH')
    effective=current.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'evidence_budget':expected,
        'candidate_rewritten':False,'reason':'只扩大完整取证总资源上限到16MiB UTF8字节，保留原18500字符确定性分页、全部检查点、分母、数值和权重；超过仍异常，不截断或补零。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
