"""Separate evaluator-added compatibility audit from the original evidence budget."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import declared_public_snapshots

PROFILE='public-snapshot-compatibility-audit-sidecar/v1'
ERROR_KIND='evaluator-added-audit-budget-repair/v1'
TASK='02_Office_task_018_targeted_repair_communication_pack'
SIDECAR='evaluator_compatibility_audit/public_snapshot_variance.json'
PRESERVED='infrastructure-evidence/public-snapshot-original-budget'
ERROR='evaluator_error: complete evidence exceeds 74000 characters; supplementary collection required, never candidate zero'

def marker(contract,contract_sha,dataset):
    base=declared_public_snapshots.marker(contract,contract_sha,dataset)
    return None if contract.get('task_id')!=TASK or base is None else {'profile':PROFILE,'snapshot_profile':base,'path':SIDECAR}

def policy(manifest,contract):
    frozen=manifest.get('runtime',{}).get('public_snapshot_audit_sidecar_profile')
    if frozen is None:return None
    expected=marker(contract,manifest['digests']['contract_sha256'],manifest['dataset'])
    if (expected is None or frozen!=expected
            or manifest['runtime'].get('declared_public_snapshot_profile')!=expected['snapshot_profile']):raise ValueError('PUBLIC_SNAPSHOT_SIDECAR_PROFILE_MISMATCH')
    return expected

INITIALIZER=r'''
def _ge2e_prepare_public_snapshot_sidecar(workspace):
    workspace=_ge2e_Path(workspace)
    output=workspace/'evaluator_compatibility_audit'/'public_snapshot_variance.json'
    if output.parent.is_symlink() or not output.parent.resolve().is_relative_to(workspace.resolve()):raise ValueError('PUBLIC_SNAPSHOT_UNSAFE_SIDECAR')
    if output.exists() or output.is_symlink():raise ValueError('PUBLIC_SNAPSHOT_SIDECAR_ALREADY_EXISTS')
    output.parent.mkdir(exist_ok=True)
    output.open('x',encoding='utf-8').write('[]')
'''

def effective_source(manifest,original,current,prior):
    contract={'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original}
    if policy(manifest,contract) is None:return current,prior
    old="    output=workspace/_GE2E_SNAPSHOT_PROFILE['evidence_directory']/'00_public_snapshot_variance.json'"
    declaration='def grade(transcript: list, workspace_path: str) -> dict:\n'
    if current.count(old)!=1 or current.count(declaration)!=1:raise ValueError('PUBLIC_SNAPSHOT_SIDECAR_SOURCE_SPAN_MISMATCH')
    effective=current.replace(old,"    output=workspace/'evaluator_compatibility_audit'/'public_snapshot_variance.json'")
    effective=effective.replace(declaration,declaration+'    _ge2e_prepare_public_snapshot_sidecar(workspace_path)\n')+'\n'+INITIALIZER
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'original_source_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'sidecar_path':SIDECAR,
        'original_total_character_budget':74000,'original_per_file_character_budget':18000,
        'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'仅将适配器新增兼容审计移到单独受管取证路径，仍完整冻结、分页查询与归档；保留原74000/18000业务证据预算、原分页、原计分和权重，审计不算候选行为。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def failure_evidence(attempt,manifest,contract,audit,worker):
    expected=marker(contract,manifest['digests']['contract_sha256'],manifest['dataset'])
    if (expected is None or manifest.get('runtime',{}).get('public_snapshot_audit_sidecar_profile') is not None
            or manifest.get('runtime',{}).get('declared_public_snapshot_profile')!=expected['snapshot_profile']
            or audit.get('status')!='failed' or audit.get('error',{}).get('code')!='RULE_WORKER_FAILED'
            or worker.get('ok') is not False or worker.get('result') is not None
            or worker.get('error',{}).get('type')!='EvidenceError' or worker.get('error',{}).get('message')!=ERROR):
        raise ValueError('PUBLIC_SNAPSHOT_ADDED_AUDIT_FAILURE_UNREGISTERED')
    attempt=Path(attempt);folder=attempt/PRESERVED
    if not folder.exists():folder=attempt/manifest['runtime']['workspace_argument']/'evaluator_evidence_018'
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(attempt.resolve()):raise ValueError('PUBLIC_SNAPSHOT_FAILURE_EVIDENCE_UNSAFE')
    files=sorted(folder.iterdir());original=[];variance=None
    for path in files:
        if path.is_symlink() or not path.is_file():raise ValueError('PUBLIC_SNAPSHOT_FAILURE_EVIDENCE_UNSAFE')
        if path.name=='00_public_snapshot_variance.json':variance=path
        elif re.fullmatch(r'(?:00_manifest|01_truth_\d{3}|10_candidate_\d{3}_\d{3})\.json',path.name):original.append(path)
        else:raise ValueError('PUBLIC_SNAPSHOT_FAILURE_EVIDENCE_UNKNOWN')
    chars=lambda p:len(p.read_text(encoding='utf-8'))
    if (variance is None or not original or not any(p.name=='00_manifest.json' for p in original)
            or any(chars(p)>18000 for p in original) or sum(map(chars,original))>74000
            or sum(map(chars,files))<=74000):raise ValueError('PUBLIC_SNAPSHOT_ORIGINAL_BUDGET_NOT_PROVEN')
    row=next(r for r in declared_public_snapshots.registry(include_revisions=True) if r['task_id']==TASK and r['contract_sha256']==manifest['digests']['contract_sha256'])
    records=json.loads(variance.read_text(encoding='utf-8'));index={r['path']:r for r in records}
    if len(index)!=len(records) or set(index)!={r['path'] for r in row['files']}:raise ValueError('PUBLIC_SNAPSHOT_VARIANCE_LEDGER_INVALID')
    base=attempt/manifest['paths']['candidate_original']/Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace'])
    for ref in row['files']:
        path=base/ref['path'];record=index[ref['path']]
        if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve())
                or not declared_public_snapshots.matches_bytes(ref,path.read_bytes())
                or record.get('actual_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest()
                or record.get('original_expected_sha256')!=ref['declared_sha256']
                or record.get('candidate_rewritten') is not False or record.get('not_agent_action_evidence') is not True):raise ValueError('PUBLIC_SNAPSHOT_VARIANCE_LEDGER_DRIFT')
    return files

def preserve_failure(attempt,manifest,contract,audit,worker):
    files=failure_evidence(attempt,manifest,contract,audit,worker);target=Path(attempt)/PRESERVED
    if target.exists():raise ValueError('PUBLIC_SNAPSHOT_FAILURE_COPY_ALREADY_EXISTS')
    target.mkdir(parents=True)
    for path in files:
        destination=target/path.name;shutil.copyfile(path,destination);destination.chmod(0o444)
    failure_evidence(attempt,manifest,contract,audit,worker)
