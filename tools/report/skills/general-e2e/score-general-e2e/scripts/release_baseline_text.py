"""Exact public release references; accept only original LF/CRLF identities."""
import hashlib
import json
from pathlib import Path

PROFILE='release-protected-original-text-identities/v1'
ERROR_KIND='release-protected-text-baseline-repair/v1'
CATALOG_SHA='f1a1bcb18b3ae18defef018ba180c02b7620c21cfd208ed7730dcc726456a6c4'

def registry():
    raw=(Path(__file__).resolve().parents[1]/'data/reviewed-release-baseline-text-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('RELEASE_TEXT_CATALOG_DRIFT')
    return json.loads(raw)

def marker(contract,contract_sha,dataset):
    row=registry()
    if (contract.get('task_id')==row['task_id'] and contract_sha==row['contract_sha256']
            and {k:dataset.get(k) for k in ['id','digest']}==row['dataset']
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
    row=registry();effective=current.replace(old,"        if not p or not _ge2e_release_protected_matches(p,rel): changed.append(rel)")+'\n_GE2E_RELEASE_TEXT_FILES='+repr(row['files'])+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':row['task_id'],'contract_sha256':row['contract_sha256'],'original_source_sha256':row['source_sha256'],
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'catalog_sha256':CATALOG_SHA,
        'original_public_text_identities':row['files'],'candidate_rewritten':False,'numeric_decisions_assigned':False,
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
