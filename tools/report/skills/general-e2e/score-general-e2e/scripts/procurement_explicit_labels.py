"""Recognize explicit procurement labels; never interpret ambiguous totals."""
import hashlib

TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT='64ba6743b737870353efc5aebec923ae82f018b6d8bf36583709b142d5515a34'
SOURCE='7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b'
BASE='5dbc6a6431a8dd4c4692e28fbe52051d7599a4038ab5aae347712e6ff4f4d561'
PROFILE='procurement-explicit-order-count-labels/v1'
BRIDGE='''

# Exact public synonyms only. Ambiguous matching and grand totals remain unknown.
_ge2e_proc_original_category=category
def category(name,grid):
    if norm(name)==norm('无单入库'):
        return 'orphan'
    return _ge2e_proc_original_category(name,grid)
for _ge2e_proc_key,_ge2e_proc_labels in {
    'qty':['数量差异订单','数量差异订单笔数'],
    'amount':['金额差异订单','金额差异订单笔数'],
    'orphan_amount':['无单入库金额合计'],
}.items():
    SUMMARY_LABELS[_ge2e_proc_key].extend(_ge2e_proc_labels)
'''

def marker(contract,contract_sha):
    if (contract.get('task_id')==TASK and contract_sha==CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,'base_effective_source_sha256':BASE}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_explicit_labels_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original},manifest.get('digests',{}).get('contract_sha256'))
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=BASE:
        raise ValueError('PROCUREMENT_EXPLICIT_LABEL_PROFILE_MISMATCH')
    effective=current+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
             'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
             'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'candidate_rewritten':False,
             'numeric_decisions_assigned':False,
             'reason':'仅识别无单入库工作表与数量/金额差异订单笔数、无单入库金额合计的明确同义名称；只读取候选原单元格，不补ID、值或参考事实。匹配成功、合计等含义未定汇总继续触发原未决门禁，原数字算法、分母和80/20不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
