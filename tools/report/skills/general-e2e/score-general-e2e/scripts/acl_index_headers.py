"""Accept an unambiguous equivalent title heading in newly prepared ACL reviews."""
import hashlib

TASK = '01_Information_Search_Organization_task_001_acl2024_long_context_qa'
SOURCE = 'b80e8169171e514cc4902613e1cda020fb99076c6fe412d7c45b907f1dc29afe'
REPAIRED_PDF_SOURCE = 'be25eda7c74472bce30429d08e3b1fc10fb7e47c0f74dd149d571d76c07c43a7'
PROFILE = 'acl-paper-index-official-title-alias/v1'
OLD = '"完整题名", "正式题名", "标题", "题名"'
NEW = '"完整题名", "正式题名", "正式标题", "标题", "题名"'
sha = lambda value: hashlib.sha256(value.encode('utf-8')).hexdigest()


def marker(contract):
    source=contract.get('automated_checks','')
    if contract.get('task_id')!=TASK or sha(source) not in {SOURCE,REPAIRED_PDF_SOURCE}:
        return None
    return {'profile':PROFILE,'source_sha256':sha(source),'additional_exact_title_alias':'正式标题'}


def effective_source(manifest,original,effective,prior):
    frozen=manifest.get('runtime',{}).get('acl_index_header_profile')
    if frozen is None:
        return effective,prior
    expected=marker({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original})
    if expected is None or frozen!=expected or effective.count(OLD)!=1:
        raise ValueError('ACL_INDEX_TITLE_ALIAS_PROFILE_MISMATCH')
    corrected=effective.replace(OLD,NEW)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id':PROFILE,'task_id':TASK,'original_source_sha256':sha(original),
        'effective_source_sha256':sha(corrected),'candidate_rewritten':False,'rubric_and_weights_changed':False,
        'reason':'只接受完整、无歧义的等价列名“正式标题”；身份集合、题名相等判断、分类、分母、分值和权重不变。旧冻结attempt未登记此Profile时保持原实现。'}
    if prior is not None:receipt['prior_correction']=prior
    return corrected,receipt
