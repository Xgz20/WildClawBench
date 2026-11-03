"""Recognize a declared combined identifier label only in orphan receipts.

Identifier cell values and every original comparison remain untouched.
"""
import hashlib
TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT='46b90a5bee7b2a90fbad93b5f36f04fa3730d2f3f27e54ca6e830cb691301e4b'
SOURCE='84df260f1948f86c0c7da4f651ac1bbf5e8d3ac220e8ad6a115b33af44d22f6c'
PROFILE='procurement-orphan-combined-id-header/v1'
PROFILE_V2='procurement-orphan-and-summary-headers/v2'
PROFILE_V3='procurement-summary-table-boundary/v3'
def marker(contract,sha):
    if contract.get('task_id')==TASK and sha==CONTRACT and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE:
        return {'profile':PROFILE_V3,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None
def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_summary_label_profile')
    if (frozen or {}).get('profile') not in {PROFILE,PROFILE_V2,PROFILE_V3}:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'])
    if expected is not None:expected={**expected,'profile':frozen['profile']}
    if frozen!=expected or expected is None:raise ValueError('PROCUREMENT_ORPHAN_ID_PROFILE_MISMATCH')
    anchor='    # Parenthesized unit/direction suffixes do not change the column\'s role.'
    replacement="    if kind=='orphan' and text in {norm(v) for v in ['入库单号/订单号','入库单号/采购订单号','入库编号/订单编号','入库对应订单号']}:return 'receipt'\n"+anchor
    if current.count(anchor)!=1:raise ValueError('PROCUREMENT_ORPHAN_ID_SOURCE_SPAN')
    effective=current.replace(anchor,replacement)
    if frozen['profile'] in {PROFILE_V2,PROFILE_V3}:
        spans=[
            ("{'对账类别','差异类型','异常类别'}", "{'类别','对账类别','差异类型','异常类别'}"),
            ("{'采购订单金额','订单金额','采购金额','订单总额'}", "{'订单金额合计','采购订单金额','订单金额','采购金额','订单总额'}"),
            ("{'入库记录金额','入库金额','实收金额'}", "{'入库金额合计','入库记录金额','入库金额','实收金额'}"),
            ("'orders':'总采购订单数','orders_amount':'订单金额合计'", "'orders':'总采购订单数','receipts':'入库记录总数','orders_amount':'订单金额合计'"),
            ("            emit('orders' if is_total else kind,headers['count'])", """            combined=re.fullmatch(r'采购订单\s*(\d+)\s*(?:笔|条|单)\s*[/／,，;；]\s*入库(?:关联|记录)?\s*(\d+)\s*(?:个订单|笔|条|单)',str(vals[headers['count']]).strip()) if is_total else None
            if combined:
                emit('orders',headers['count'],int(combined.group(1)))
                emit('receipts',headers['count'],int(combined.group(2)))
            else:emit('orders' if is_total else kind,headers['count'])"""),
        ]
        for old,new in spans:
            if effective.count(old)!=1:raise ValueError('PROCUREMENT_MATRIX_HEADER_SOURCE_SPAN')
            effective=effective.replace(old,new)
        effective+="\nSUMMARY_LABELS['clean']=list(SUMMARY_LABELS['clean'])+['完全匹配']\n"
        if frozen['profile']==PROFILE_V3:
            old='                emit(key,headers[field])\n        if (not net_present'
            new='                emit(key,headers[field])\n            if is_total:headers=None\n        if (not net_present'
            if effective.count(old)!=1:raise ValueError('PROCUREMENT_MATRIX_BOUNDARY_SOURCE_SPAN')
            effective=effective.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':frozen['profile'],
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_claims_invented':False,
        'reason':('矩阵合计行结束后关闭该表域，后续口径说明交原普通声明读取，不作为重复矩阵类别；保留原编号和数值、全部可见性/比较/分母/限分及80/20。' if frozen['profile']==PROFILE_V3 else '仅识别明确合并编号及矩阵表头/完全匹配标签，合计的显式双计数按原数字拆成两项声明；不补业务ID后缀或任何单元格值，不改变对象、原金额比较、分母、可见性、限分和80/20。' if frozen['profile']==PROFILE_V2 else '仅在无对应订单入库类别识别明确合并编号表头，原编号单元格不拆分、不补值；对象、数值、可见性、差额方向、汇总、分母、严重金额义务及80/20保持原逻辑。')}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
