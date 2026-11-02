"""Exact original UTF-8 LF/CRLF public-input identities, without rewriting bytes."""
import hashlib
import json
from pathlib import Path

PROFILE='canonical-public-text-newlines/v1'
CATALOG_SHA='9fd7c0679cf52111b0535535b3e47bd72eb3cdf19a36c957080f65ca4c3a56ed'
ERROR_KIND='declared-public-text-newline-repair/v1'


from source_identities import registry_variants

def registry(*, include_revisions=False):
    raw=(Path(__file__).resolve().parents[1]/'data/reviewed-public-text-newlines-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('PUBLIC_TEXT_CATALOG_DRIFT')
    return registry_variants(json.loads(raw)['profiles']) if include_revisions else json.loads(raw)['profiles']


def marker(contract,contract_sha,dataset):
    for row in registry(include_revisions=True):
        if (row['task_id']==contract.get('task_id') and row['contract_sha256']==contract_sha
                and row['dataset']=={k:dataset.get(k) for k in ['id','digest']}
                and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==row['source_sha256']):
            return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,'contract_sha256':contract_sha,
                'source_sha256':row['source_sha256']}
    return None


BRIDGE=r'''
_ge2e_text_original_office_matches=_ge2e_public_office_matches
def _ge2e_public_office_matches(path,expected_sha256,workspace,*,role='input_snapshot'):
    if _ge2e_text_original_office_matches(path,expected_sha256,workspace,role=role):return True
    if role!='input_snapshot':return False
    path=_ge2e_Path(path);workspace=_ge2e_Path(workspace)
    try:
        relative=path.relative_to(workspace).as_posix()
        if not path.resolve().is_relative_to(workspace.resolve()):return False
    except (ValueError,OSError):return False
    for parent in [path,*path.parents]:
        if parent==workspace:break
        if parent.is_symlink():return False
    ref=next((r for r in _GE2E_TEXT_FILES if r['path']==relative and expected_sha256 in {r['declared_sha256'],r['canonical_sha256']}),None)
    if ref is None or not path.is_file():return False
    raw=path.read_bytes();observed=_ge2e_text_hashlib.sha256(raw).hexdigest()
    if observed not in {ref['canonical_sha256'],ref['declared_sha256']}:return False
    canonical=raw.replace(b'\r\n',b'\n')
    if _ge2e_text_hashlib.sha256(canonical).hexdigest()!=ref['canonical_sha256']:return False
    if _ge2e_text_hashlib.sha256(canonical.replace(b'\n',b'\r\n')).hexdigest()!=ref['declared_sha256']:return False
    folder=workspace/_GE2E_PUBLIC_OFFICE_PROFILE['evidence_directory']
    if folder.is_symlink() or not folder.resolve().is_relative_to(workspace.resolve()):raise ValueError('Unsafe text variance evidence')
    folder.mkdir(exist_ok=True)
    target=folder/'00_public_text_newline_variance.json'
    if target.exists() and (target.is_symlink() or target.stat().st_nlink!=1):raise ValueError('Unsafe text variance audit')
    records=_ge2e_json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
    record={'profile':'canonical-public-text-newlines/v1','path':relative,'observed_sha256':observed,
        'original_expected_sha256':expected_sha256,'canonical_lf_sha256':ref['canonical_sha256'],
        'declared_crlf_sha256':ref['declared_sha256'],'source_rewritten':False,'not_agent_action_evidence':True}
    if record not in records:records.append(record)
    target.write_text(_ge2e_json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return True
'''


def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('public_text_input_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected or current.count('def _ge2e_public_office_matches(')!=1:
        raise ValueError('PUBLIC_TEXT_FROZEN_PROFILE_MISMATCH')
    row=next(r for r in registry(include_revisions=True) if r['task_id']==manifest['identity']['task_id'] and r['contract_sha256']==manifest['digests']['contract_sha256'])
    effective=current+'\nimport hashlib as _ge2e_text_hashlib\n_GE2E_TEXT_FILES='+repr(row['files'])+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':row['task_id'],'contract_sha256':row['contract_sha256'],'original_source_sha256':row['source_sha256'],
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'catalog_sha256':CATALOG_SHA,
        'canonical_text_inputs':row['files'],'candidate_rewritten':False,
        'reason':'仅按原dataset/contract/source绑定接受已证明逐字节UTF8 LF/CRLF等价的公开文本；原GT预期hash保留、实际hash独立审计，其他内容变化仍拒绝，数值与权重不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def original_failure(attempt,manifest,contract,audit,worker):
    if marker(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{})) is None:return False
    error=worker.get('error') or {};message=error.get('message','')
    if (audit.get('status')!='failed' or audit.get('error',{}).get('code')!='RULE_WORKER_FAILED'
            or worker.get('ok') is not False or error.get('type') not in {'RuntimeError','EvaluationDataError'}):return False
    row=next(r for r in registry(include_revisions=True) if r['task_id']==contract['task_id'])
    suffix=Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace'])
    original=Path(attempt)/manifest['paths']['candidate_original']/suffix
    for ref in row['files']:
        if ref['path'] not in message:continue
        path=original/ref['path']
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(original.resolve()):return False
        raw=path.read_bytes()
        if (hashlib.sha256(raw).hexdigest()==ref['canonical_sha256']
                and hashlib.sha256(raw.replace(b'\n',b'\r\n')).hexdigest()==ref['declared_sha256']):return True
    return False
