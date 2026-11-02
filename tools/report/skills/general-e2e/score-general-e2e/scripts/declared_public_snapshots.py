"""Exact original public inputs for two authored snapshot checks; no byte rewriting."""
import hashlib
import json
from pathlib import Path
import office_input_compat

PROFILE='declared-public-snapshot-variance/v1'
ERROR_KIND='declared-public-snapshot-baseline-repair/v1'
CATALOG_SHA='42b5cd2f1efd09138c61eb2f3be75d3e2de08a69070dba8c93eaf8a92911a563'

from source_identities import registry_variants

def registry(*, include_revisions=False):
    raw=(Path(__file__).resolve().parents[1]/'data/declared-public-snapshot-variance-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('PUBLIC_SNAPSHOT_CATALOG_DRIFT')
    return registry_variants(json.loads(raw)['profiles']) if include_revisions else json.loads(raw)['profiles']

def marker(contract,contract_sha,dataset):
    for row in registry(include_revisions=True):
        if (row['task_id']==contract.get('task_id') and row['contract_sha256']==contract_sha
                and row['dataset']=={k:dataset.get(k) for k in ['id','digest']}
                and row['source_sha256']==hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()):
            return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,'contract_sha256':contract_sha,'source_sha256':row['source_sha256']}
    return None

def matches_bytes(ref,raw):
    if ref['kind']=='text-newlines':
        return (hashlib.sha256(raw).hexdigest() in {ref['canonical_sha256'],ref['declared_sha256']}
            and hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()==ref['canonical_sha256']
            and hashlib.sha256(raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')).hexdigest()==ref['declared_sha256'])
    if ref['kind']=='office-cwm-only':
        import base64
        return (hashlib.sha256(raw).hexdigest()==ref['canonical_sha256']
            or office_input_compat.compare_office_cwm(base64.b64decode(ref['base64'],validate=True),raw,ref['canonical_sha256']) is not None)
    raise ValueError('PUBLIC_SNAPSHOT_KIND_INVALID')

MATCHER=r'''
def _ge2e_declared_public_snapshot_matches(path,relative,expected,workspace):
    path=_ge2e_Path(path);workspace=_ge2e_Path(workspace)
    if path.is_symlink() or not path.resolve().is_relative_to(workspace.resolve()):return False
    ref=next((r for r in _GE2E_SNAPSHOT_PROFILE['files'] if r['path']==relative and r['declared_sha256']==expected),None)
    if ref is None:return False
    raw=path.read_bytes();actual=_ge2e_hashlib.sha256(raw).hexdigest();proof=None
    if ref['kind']=='text-newlines':
        normalized=raw.replace(b'\r\n',b'\n')
        if (actual not in {ref['canonical_sha256'],ref['declared_sha256']}
                or _ge2e_hashlib.sha256(normalized).hexdigest()!=ref['canonical_sha256']
                or _ge2e_hashlib.sha256(normalized.replace(b'\n',b'\r\n')).hexdigest()!=ref['declared_sha256']):return False
        proof={'kind':'original-lf-crlf-identity'}
    elif ref['kind']=='office-cwm-only':
        try:proof=compare_office_cwm(_ge2e_base64.b64decode(ref['base64'],validate=True),raw,ref['canonical_sha256'])
        except (ValueError,KeyError,_ge2e_zipfile.BadZipFile,_ge2e_et.ParseError):return False
        if proof is None:return False
    else:return False
    output=workspace/_GE2E_SNAPSHOT_PROFILE['evidence_directory']/'00_public_snapshot_variance.json'
    if output.parent.is_symlink() or not output.parent.resolve().is_relative_to(workspace.resolve()):raise ValueError('PUBLIC_SNAPSHOT_UNSAFE_AUDIT')
    output.parent.mkdir(exist_ok=True)
    if output.exists() and (output.is_symlink() or output.stat().st_nlink!=1):raise ValueError('PUBLIC_SNAPSHOT_UNSAFE_AUDIT')
    rows=_ge2e_json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    record={'profile':'declared-public-snapshot-variance/v1','path':relative,'actual_sha256':actual,
        'original_expected_sha256':expected,'canonical_sha256':ref['canonical_sha256'],
        'proof':proof,'candidate_rewritten':False,'not_agent_action_evidence':True}
    if record not in rows:rows.append(record)
    output.write_text(_ge2e_json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return True
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('declared_public_snapshot_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected:raise ValueError('PUBLIC_SNAPSHOT_PROFILE_MISMATCH')
    row=next(r for r in registry(include_revisions=True) if r['task_id']==manifest['identity']['task_id'] and r['contract_sha256']==manifest['digests']['contract_sha256'])
    replacements={
        '02_Office_task_018_targeted_repair_communication_pack':(
            'if not _safe(path,root) or not path.is_file() or _digest(path)!=expected: changed.append(rel)',
            'if not _safe(path,root) or not path.is_file() or (_digest(path)!=expected and not _ge2e_declared_public_snapshot_matches(path,rel,expected,root)): changed.append(rel)'),
        '02_Office_task_029_monitoring_weekly_docx':(
            'if not safe or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:',
            'if not safe or not p.is_file() or (hashlib.sha256(p.read_bytes()).hexdigest()!=expected and not _ge2e_declared_public_snapshot_matches(p,rel,expected,root)):')}
    old,new=replacements[row['task_id']]
    if current.count(old)!=1:raise ValueError('PUBLIC_SNAPSHOT_SOURCE_SPAN_MISMATCH')
    helper=Path(office_input_compat.__file__).read_text(encoding='utf-8')
    effective=helper+'\n_GE2E_SNAPSHOT_PROFILE='+repr(row)+'\n'+MATCHER+'\n'+current.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':row['task_id'],'contract_sha256':row['contract_sha256'],'original_source_sha256':row['source_sha256'],
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'catalog_sha256':CATALOG_SHA,
        'public_input_identities':[{k:v for k,v in r.items() if k!='base64'} for r in row['files']],
        'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'只适配原数据集已证明的公开输入LF/CRLF身份及严格CWM属性变体，业务OPC部件、原件和实际SHA保留；原比较、分母、权重、数值函数及语义要求不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def original_failure(attempt,manifest,contract,worker):
    if marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None:return False
    row=next(r for r in registry(include_revisions=True) if r['task_id']==contract['task_id']);raw=worker.get('raw_result',{})
    if (worker.get('ok') is not True or sorted(raw.get('diagnostics',{}).get('changed_inputs',[]))!=sorted(r['path'] for r in row['files'])):return False
    base=Path(attempt)/manifest['paths']['candidate_original']/Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace'])
    for ref in row['files']:
        path=base/ref['path']
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()) or not matches_bytes(ref,path.read_bytes()):return False
    return True
