"""Keep the original deterministic chunker; increase only its total resource budget."""
import hashlib

PROFILE='work-order-complete-evidence-budget/v1'
SERVICE_PROFILE='service-report-complete-evidence-budget/v1'
SERVICE_TASK='02_Office_task_012_service_channel_ticket_daily'
SERVICE_CONTRACT='b440485348ee72c7ab58b6f212a05cbc16691d8e6ece9a286661f981fa13358a'
SERVICE_SOURCE='64ac633a83d579fa4f099aca687c3aa1bde8477273e0e93ad31cf28b043a9956'
SERVICE_OLD="    if any(len(v)>19000 for v in encoded.values()) or sum(map(len,encoded.values()))>74000:raise EvaluationError('Evidence would be truncated; evaluation invalid')"
SERVICE_NEW="    if any(len(v.encode('utf-8'))>1048576 for v in encoded.values()) or sum(len(v.encode('utf-8')) for v in encoded.values())>16777216:raise EvaluationError('Evidence would be truncated; evaluation invalid')"
CUSTOMER_PROFILE='customer-remediation-complete-evidence-budget/v1'
CUSTOMER_TASK='02_Office_task_013_customer_remediation_pack'
CUSTOMER_CONTRACT='af1f136e9c417075c20e6e694af74eadbe14fd24f623356f08960af17b8da5e3'
CUSTOMER_SOURCE='3cc8ca96c44618391fad974313fc84ac83e15532c525acff4d1d20fd8cc97955'
PACK_PROFILE='communication-pack-complete-evidence-budget/v1'
PACK_TASK='02_Office_task_018_targeted_repair_communication_pack'
PACK_CONTRACT='303328777610178aab42baa175aa2e3c65dd0ccf868b5200d200a0597704e107'
PACK_SOURCE='d2e1e3adf18ce595499464db66e3bc1a728ccabc64bc887d02ef70356eac17bf'
PRD_PROFILE='prd-plan-complete-evidence-budget/v1'
PRD_TASK='02_Office_task_019_prd_system_design_breakdown'
PRD_CONTRACT='2a473675b08481052bc5808a5387e85fa0152bdcf4ed5448e922e9023a4097d5'
PRD_SOURCE='4ab6e8cd79ecc6aeeb8fc6294dc4f7257947365162c8cba1511a202b89989035'
EXTRA={
 '02_Office_task_029_monitoring_weekly_docx':('967f54a181a67fe91b7513b6d81d61a6badd7d7def1c6fcc1033d5d69fae762a','93859e60892a717a0adfb8e3d1feb78a7baa6bdd0f33ea707b520e5c3a5af309','evidence',55000),
 '02_Office_task_030_service_center_consolidation':('1cf27d0d5844d40d08824e606bc92e1efb9514bc0d780051793d85b270d586cc','f29d880bb031209ecca324e32f1761598adf407f354ae8975d2a288d805d2378','evidence',74000),
}
EXTRA_PROFILE='office-complete-collection-resource/v1'
TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT_SHA='c44c983d8373f7075baeee65e327cf886ed2931368b8a59dcd8dae5d484d6cc1'
SOURCE_SHA='fab46597d51de9869feeef882eaa222b9ced1ecc8809ad10c7a8fa1be697bfac'

from source_identities import accepted_contracts

def marker(contract,contract_sha):
    if (contract.get('task_id')==CUSTOMER_TASK and contract_sha==CUSTOMER_CONTRACT
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==CUSTOMER_SOURCE):
        return {'profile':CUSTOMER_PROFILE,'contract_sha256':CUSTOMER_CONTRACT,'source_sha256':CUSTOMER_SOURCE,
                'total_utf8_bytes':16777216,'part_characters':17000,'truncation_allowed':False}
    if (contract.get('task_id')==SERVICE_TASK and contract_sha==SERVICE_CONTRACT
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SERVICE_SOURCE):
        return {'profile':SERVICE_PROFILE,'contract_sha256':SERVICE_CONTRACT,'source_sha256':SERVICE_SOURCE,
                'file_utf8_bytes':1048576,'total_utf8_bytes':16777216,'truncation_allowed':False}
    extra=EXTRA.get(contract.get('task_id'))
    if extra and contract_sha==extra[0] and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==extra[1]:
        return {'profile':EXTRA_PROFILE,'contract_sha256':extra[0],'source_sha256':extra[1],'total_utf8_bytes':16777216,'truncation_allowed':False,'original_total_chars':extra[3]}
    if (contract.get('task_id')==PRD_TASK and contract_sha==PRD_CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==PRD_SOURCE):
        return {'profile':PRD_PROFILE,'contract_sha256':PRD_CONTRACT,'source_sha256':PRD_SOURCE,'total_utf8_bytes':16777216,'truncation_allowed':False}
    if (contract.get('task_id')==PACK_TASK and contract_sha==PACK_CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==PACK_SOURCE):
        return {'profile':PACK_PROFILE,'contract_sha256':PACK_CONTRACT,'source_sha256':PACK_SOURCE,'total_utf8_bytes':16777216,'truncation_allowed':False}
    if (contract.get('task_id')==TASK and contract_sha in accepted_contracts(CONTRACT_SHA)
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':contract_sha,'source_sha256':SOURCE_SHA,'total_utf8_bytes':16777216,'truncation_allowed':False}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('work_order_evidence_budget_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'])
    if expected is None or frozen!=expected:raise ValueError('WORK_ORDER_BUDGET_PROFILE_MISMATCH')
    if frozen['profile']==CUSTOMER_PROFILE:
        pairs=[('MAX_TOTAL_TEXT = 74000','MAX_TOTAL_TEXT = 16777216'),
               ('    if total > MAX_TOTAL_TEXT:', '    if sum(len(line.encode("utf-8")) for line in lines) > MAX_TOTAL_TEXT:')]
        effective=current
        for old,new in pairs:
            if effective.count(old)!=1:raise ValueError('CUSTOMER_EVIDENCE_BUDGET_SOURCE_MISMATCH')
            effective=effective.replace(old,new)
        receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':CUSTOMER_PROFILE,
            'task_id':CUSTOMER_TASK,'contract_sha256':CUSTOMER_CONTRACT,'original_source_sha256':CUSTOMER_SOURCE,
            'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'evidence_budget':expected,
            'candidate_rewritten':False,'reason':'仅为完整业务取证冻结16MiB UTF8总资源上限，保留原17000字符分页、逐记录拒绝截断、返回字符计数、文件及路径安全边界；候选、全部字段、数值规则、语义标准和权重不变。'}
        if prior:receipt['prior_correction']=prior
        return effective,receipt
    if frozen['profile']==SERVICE_PROFILE:
        if current.count(SERVICE_OLD)!=1:raise ValueError('SERVICE_REPORT_EVIDENCE_BUDGET_SOURCE_MISMATCH')
        effective=current.replace(SERVICE_OLD,SERVICE_NEW)
        receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':SERVICE_PROFILE,
            'task_id':SERVICE_TASK,'contract_sha256':SERVICE_CONTRACT,'original_source_sha256':SERVICE_SOURCE,
            'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'evidence_budget':expected,
            'candidate_rewritten':False,'reason':'仅将完整JSON取证存储上限明确为单文件1MiB、合计16MiB UTF8字节；原报告30000字符门禁、文件名、分页、字段、序列化字节和安全检查全部保留，全部数值算法、语义标准及70/30权重不变。超限仍异常，不截断或补零。'}
        if prior:receipt['prior_correction']=prior
        return effective,receipt
    communication=frozen['profile']==PACK_PROFILE
    prd=frozen['profile']==PRD_PROFILE
    extra=frozen['profile']==EXTRA_PROFILE
    old="    size=sum(len(path.read_text(encoding='utf-8')) for path in output.iterdir())\n    if size>74000:" if communication else '    total=sum(len(v) for v in serialized.values())\n    if total>70000:'
    new="    size=sum(path.stat().st_size for path in output.iterdir())\n    if size>16777216:" if communication else "    total=sum(len(v.encode('utf-8')) for v in serialized.values())\n    if total>16777216:"
    if prd:
        old='    total=sum(map(len,serialized))\n    if total>72000:'
        new="    total=sum(len(v.encode('utf-8')) for v in serialized)\n    if total>16777216:"
    if extra:
        row=EXTRA[manifest['identity']['task_id']]
        old="    total=sum(len(p.read_text(encoding='utf-8')) for p in evidence.iterdir())\n    if total>"+str(row[3])+':'
        new="    total=sum(p.stat().st_size for p in evidence.iterdir())\n    if total>16777216:"
    if current.count(old)!=1:raise ValueError('WORK_ORDER_BUDGET_SOURCE_SPAN_MISMATCH')
    effective=current.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':frozen['profile'],
        'task_id':manifest['identity']['task_id'] if communication or prd or extra else TASK,
        'contract_sha256':frozen['contract_sha256'] if communication or prd or extra else CONTRACT_SHA,
        'original_source_sha256':frozen['source_sha256'] if communication or prd or extra else SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'evidence_budget':expected,
        'candidate_rewritten':False,'reason':('只为完整业务取证登记16MiB UTF8资源上限，保留原确定性分页、单文件与格式安全限额；不改变候选、规则分值、Rubric、权重，超限继续异常且不截断。' if prd or extra else '只为完整业务取证登记16MiB UTF8资源上限，保留原18000字符文件上限与确定性分页；不改变候选、规则分值、Rubric、权重、原格式安全限额，超限继续异常且不截断。' if communication else '只扩大完整取证总资源上限到16MiB UTF8字节，保留原18500字符确定性分页、全部检查点、分母、数值和权重；超过仍异常，不截断或补零。')}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
