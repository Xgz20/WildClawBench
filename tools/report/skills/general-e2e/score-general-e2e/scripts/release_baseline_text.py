"""Exact public release references; accept only original LF/CRLF identities."""
import hashlib
import json
from pathlib import Path

PROFILE='release-protected-original-text-identities/v1'
ERROR_KIND='release-protected-text-baseline-repair/v1'
CATALOG_SHA='f1a1bcb18b3ae18defef018ba180c02b7620c21cfd208ed7730dcc726456a6c4'
V4_CONTRACT='57338e91bd87b3cff8f034d5da7340fa95d19dbeae701db8a3a57afa95252c45'
V4_SOURCE='ec04d3539c64efaf0909e4c0772164e39fa30c835d389eff46d2c5becaa59fe1'
V4_DATASET={'id':'general-custom70-v4','digest':'914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'}
V5_DATASET={'id': 'general-custom70-v5', 'digest': '8503a341fc496b88e1b8e368105e2d700360e026fa5c22578a819f0beb748a6d'}
V6_DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
V3_DATASET={'id':'general-custom70-v3','digest':'2a9ebd7ee9330a6d7fd7261df44275e8980eb95275b0ada2c80b4005573132b7'}

def registry(contract_sha=None):
    raw=(Path(__file__).resolve().parents[1]/'data/reviewed-release-baseline-text-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('RELEASE_TEXT_CATALOG_DRIFT')
    row=json.loads(raw)
    if contract_sha==V4_CONTRACT:
        files=[{**f,'dataset_member':f['dataset_member'].replace('general-custom116-v1/','general-custom70-v4/',1)}
               for f in row['files']]
        return {**row,'contract_sha256':V4_CONTRACT,'source_sha256':V4_SOURCE,'dataset':V4_DATASET,
                'dataset_archive_sha256':'e3249442694aa3745e2f1adff100035f86e458fd5832a9adb6effff522647e40',
                'files':files}
    if contract_sha is None or contract_sha==row['contract_sha256']:return row
    from source_identities import registry_variants
    return next((r for r in registry_variants([row]) if r['contract_sha256']==contract_sha),row)

def marker(contract,contract_sha,dataset):
    row=registry(contract_sha)
    binding={k:dataset.get(k) for k in ['id','digest']}
    dataset_matches=(binding in [V3_DATASET,V4_DATASET,V5_DATASET,V6_DATASET] if contract_sha==V4_CONTRACT else binding==row['dataset'])
    if (contract.get('task_id')==row['task_id'] and contract_sha==row['contract_sha256']
            and dataset_matches
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==row['source_sha256']):
        return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,'contract_sha256':contract_sha,'source_sha256':row['source_sha256']}
    return None

BRIDGE=r'''
def _ge2e_release_protected_matches(path,relative):
    raw=path.read_bytes()
    observed=hashlib.sha256(raw).hexdigest()
    if observed==FROZEN['hashes'][relative]:return True
    ref=next((r for r in _GE2E_RELEASE_TEXT_FILES if r['path']==relative),None)
    if ref is None or observed!=ref['canonical_sha256']:return False
    return hashlib.sha256(raw.replace(b'\n',b'\r\n')).hexdigest()==ref['declared_sha256']
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('release_baseline_text_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    old="        if not p or hashlib.sha256(p.read_bytes()).hexdigest()!=FROZEN['hashes'][rel]: changed.append(rel)"
    if expected is None or expected!=frozen or current.count(old)!=1:raise ValueError('RELEASE_TEXT_PROFILE_MISMATCH')
    row=registry(manifest['digests']['contract_sha256'])
    files=([{k:f[k] for k in ['path','canonical_sha256','declared_sha256','size']} for f in row['files']]
           if manifest['digests']['contract_sha256']==V4_CONTRACT else row['files'])
    effective=current.replace(old,"        if not p or not _ge2e_release_protected_matches(p,rel): changed.append(rel)")+'\n_GE2E_RELEASE_TEXT_FILES='+repr(files)+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':row['task_id'],'contract_sha256':row['contract_sha256'],'original_source_sha256':row['source_sha256'],
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'catalog_sha256':CATALOG_SHA,
        'original_public_text_identities':files,'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'只接受原版本化数据集已核验的8份受保护文本LF/CRLF字节身份，保留原SHA与原件；其他变动仍按原规则拒绝，原数值、分母、权重与语义门禁不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def check_original(attempt,manifest,contract):
    if marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None:raise ValueError('RELEASE_TEXT_UNREGISTERED')
    base=Path(attempt)/manifest['paths']['candidate_original']
    suffix=Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace']);base=base/suffix
    for ref in registry()['files']:
        path=base/ref['path']
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):raise ValueError('RELEASE_TEXT_INPUT_INVALID')
        raw=path.read_bytes()
        if (hashlib.sha256(raw).hexdigest()!=ref['canonical_sha256']
                or hashlib.sha256(raw.replace(b'\n',b'\r\n')).hexdigest()!=ref['declared_sha256']):raise ValueError('RELEASE_TEXT_NONCANONICAL')
    return True

def native_blocker_matches(rt,attempt,manifest,contract):
    """Only exact uncorrected v4/v6 LF/CRLF failures before semantic import."""
    if (manifest.get('digests',{}).get('contract_sha256')!=V4_CONTRACT
            or manifest.get('dataset') not in (V4_DATASET,V6_DATASET)
            or marker(contract,V4_CONTRACT,manifest.get('dataset',{})) is None
            or manifest.get('runtime',{}).get('release_baseline_text_profile') is not None):
        return False
    path=Path(attempt)/'scoring-infrastructure-blocker.json'
    if path.is_symlink() or not path.is_file():return False
    b=rt._read_json(path)
    if (b.get('schema_version')!='judge-scoring-infrastructure-blocker/v1'
            or b.get('status')!='evaluation_error'
            or b.get('error_code')!='FROZEN_RULE_PUBLIC_TEXT_BASELINE_MISMATCH'
            or b.get('task_id')!=manifest['identity']['task_id']
            or b.get('scoring_attempt_id')!=manifest['identity']['scoring_attempt_id']
            or b.get('score_published') is not False or b.get('total_score') is not None
            or b.get('evidence',{}).get('registry_sha256')!=CATALOG_SHA
            or b.get('evidence',{}).get('frozen_rule_component_sha256')!=rt._sha256_file(Path(attempt)/'rule-component.json')
            or b.get('preservation',{}).get('semantic_response_imported') is not False
            or (Path(attempt)/'semantic/semantic-component.json').exists()
            or not (Path(attempt)/'semantic/query-log.json').is_file()):
        raise ValueError('RELEASE_TEXT_NATIVE_BLOCKER_INVALID')
    if manifest['dataset']==V6_DATASET:
        evidence=b.get('evidence',{})
        if (b.get('execution_attempt_id')!=manifest['identity']['execution_attempt_id']
                or evidence.get('frozen_contract_sha256')!=V4_CONTRACT
                or evidence.get('frozen_rule_source_sha256')!=V4_SOURCE
                or evidence.get('dataset')!=V6_DATASET or evidence.get('profile_in_attempt') is not None
                or evidence.get('all_eight_registered_original_identities') is not True
                or any(b.get('preservation',{}).get(k) is not False for k in
                    ['candidate_original_modified','frozen_skill_modified','harness_executed','rule_component_rerun',
                     'old_component_modified','semantic_response_imported','finalize_run','verify_score_passed'])):
            raise ValueError('RELEASE_TEXT_V6_NATIVE_BLOCKER_INVALID')
    check_original(attempt,manifest,contract)
    return True
