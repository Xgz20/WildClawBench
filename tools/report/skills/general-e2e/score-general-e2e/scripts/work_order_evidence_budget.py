"""Keep the original deterministic chunker; increase only its total resource budget."""
import hashlib

PROFILE='work-order-complete-evidence-budget/v1'
PACK_PROFILE='communication-pack-complete-evidence-budget/v1'
PACK_TASK='02_Office_task_018_targeted_repair_communication_pack'
PACK_CONTRACT='303328777610178aab42baa175aa2e3c65dd0ccf868b5200d200a0597704e107'
PACK_SOURCE='d2e1e3adf18ce595499464db66e3bc1a728ccabc64bc887d02ef70356eac17bf'
PRD_PROFILE='prd-plan-complete-evidence-budget/v1'
PRD_TASK='02_Office_task_019_prd_system_design_breakdown'
PRD_CONTRACT='2a473675b08481052bc5808a5387e85fa0152bdcf4ed5448e922e9023a4097d5'
PRD_SOURCE='4ab6e8cd79ecc6aeeb8fc6294dc4f7257947365162c8cba1511a202b89989035'
TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT_SHA='c44c983d8373f7075baeee65e327cf886ed2931368b8a59dcd8dae5d484d6cc1'
SOURCE_SHA='fab46597d51de9869feeef882eaa222b9ced1ecc8809ad10c7a8fa1be697bfac'

from source_identities import accepted_contracts

def marker(contract,contract_sha):
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
    communication=frozen['profile']==PACK_PROFILE
    prd=frozen['profile']==PRD_PROFILE
    old="    size=sum(len(path.read_text(encoding='utf-8')) for path in output.iterdir())\n    if size>74000:" if communication else '    total=sum(len(v) for v in serialized.values())\n    if total>70000:'
    new="    size=sum(path.stat().st_size for path in output.iterdir())\n    if size>16777216:" if communication else "    total=sum(len(v.encode('utf-8')) for v in serialized.values())\n    if total>16777216:"
    if prd:
        old='    total=sum(map(len,serialized))\n    if total>72000:'
        new="    total=sum(len(v.encode('utf-8')) for v in serialized)\n    if total>16777216:"
    if current.count(old)!=1:raise ValueError('WORK_ORDER_BUDGET_SOURCE_SPAN_MISMATCH')
    effective=current.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':frozen['profile'],
        'task_id':manifest['identity']['task_id'] if communication or prd else TASK,
        'contract_sha256':frozen['contract_sha256'] if communication or prd else CONTRACT_SHA,
        'original_source_sha256':frozen['source_sha256'] if communication or prd else SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'evidence_budget':expected,
        'candidate_rewritten':False,'reason':('只为完整业务取证登记16MiB UTF8资源上限，保留原确定性分页、单文件与格式安全限额；不改变候选、规则分值、Rubric、权重，超限继续异常且不截断。' if prd else '只为完整业务取证登记16MiB UTF8资源上限，保留原18000字符文件上限与确定性分页；不改变候选、规则分值、Rubric、权重、原格式安全限额，超限继续异常且不截断。' if communication else '只扩大完整取证总资源上限到16MiB UTF8字节，保留原18500字符确定性分页、全部检查点、分母、数值和权重；超过仍异常，不截断或补零。')}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
