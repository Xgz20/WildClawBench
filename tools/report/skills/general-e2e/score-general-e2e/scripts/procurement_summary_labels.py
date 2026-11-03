"""One declared equivalent matched-order label; original arithmetic is untouched."""
import hashlib

PROFILE='procurement-equivalent-matched-summary-label/v1'
TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT_SHA='808dce46890576b6f97f1d2364389ae2bff19bf81dc8a11096618e178146b127'
SOURCE_SHA='e0ce3c13706112766a91b1d6309dae0c13ddb99aa4b7b8c6f9f574b9ed97490c'
BRIDGE="\n# Publicly equivalent matched orders; the original short-label parser retains qualifiers.\nSUMMARY_LABELS['matched']=list(SUMMARY_LABELS['matched'])+['已匹配订单']\n"


from source_identities import accepted_contracts

def marker(contract,contract_sha):
    if (contract.get('task_id')==TASK and contract_sha in accepted_contracts(CONTRACT_SHA)
            and hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':contract_sha,'source_sha256':SOURCE_SHA}
    import procurement_orphan_id_header
    return procurement_orphan_id_header.marker(contract,contract_sha)


def effective_source(manifest,original,current,prior):
    import procurement_orphan_id_header
    frozen=manifest.get('runtime',{}).get('procurement_summary_label_profile')
    if (frozen or {}).get('profile') in {procurement_orphan_id_header.PROFILE,procurement_orphan_id_header.PROFILE_V2,procurement_orphan_id_header.PROFILE_V3}:
        return procurement_orphan_id_header.effective_source(manifest,original,current,prior)
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original},
        manifest.get('digests',{}).get('contract_sha256'))
    if expected is None or frozen!=expected:raise ValueError('PROCUREMENT_SUMMARY_LABEL_PROFILE_MISMATCH')
    if current.count("SUMMARY_LABELS =")+current.count('SUMMARY_LABELS=')!=1:
        raise ValueError('PROCUREMENT_SUMMARY_LABEL_SOURCE_SPAN_MISMATCH')
    effective=current+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode('utf-8')).hexdigest(),
        'candidate_rewritten':False,'numeric_claims_invented':False,
        'reason':'仅将已匹配订单这一公开等价表头交原matched口径核验，括号限定仍由原short-label解析；原数值、可见性、分母、金额义务、未知公式失败边界及80/20权重不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
