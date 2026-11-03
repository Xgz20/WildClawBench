"""Recognize a declared combined identifier label only in orphan receipts.

Identifier cell values and every original comparison remain untouched.
"""
import hashlib
TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT='46b90a5bee7b2a90fbad93b5f36f04fa3730d2f3f27e54ca6e830cb691301e4b'
SOURCE='84df260f1948f86c0c7da4f651ac1bbf5e8d3ac220e8ad6a115b33af44d22f6c'
PROFILE='procurement-orphan-combined-id-header/v1'
def marker(contract,sha):
    if contract.get('task_id')==TASK and sha==CONTRACT and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE:
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None
def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_summary_label_profile')
    if (frozen or {}).get('profile')!=PROFILE:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'])
    if frozen!=expected or expected is None:raise ValueError('PROCUREMENT_ORPHAN_ID_PROFILE_MISMATCH')
    anchor='    # Parenthesized unit/direction suffixes do not change the column\'s role.'
    replacement="    if kind=='orphan' and text in {norm(v) for v in ['入库单号/订单号','入库单号/采购订单号','入库编号/订单编号','入库对应订单号']}:return 'receipt'\n"+anchor
    if current.count(anchor)!=1:raise ValueError('PROCUREMENT_ORPHAN_ID_SOURCE_SPAN')
    effective=current.replace(anchor,replacement)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_claims_invented':False,
        'reason':'仅在无对应订单入库类别识别明确合并编号表头，原编号单元格不拆分、不补值；对象、数值、可见性、差额方向、汇总、分母、严重金额义务及80/20保持原逻辑。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
