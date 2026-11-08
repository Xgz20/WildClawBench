"""Preserve a source-bound complete business-evidence resource failure."""
from pathlib import Path
import hashlib,json,re,shutil
TASK='02_Office_task_018_targeted_repair_communication_pack'
CONTRACT='303328777610178aab42baa175aa2e3c65dd0ccf868b5200d200a0597704e107'
SOURCE='d2e1e3adf18ce595499464db66e3bc1a728ccabc64bc887d02ef70356eac17bf'
ERROR='evaluator_error: complete evidence exceeds 74000 characters; supplementary collection required, never candidate zero'
PRESERVED='infrastructure-evidence/complete-business-evidence-budget'
PRD_TASK='02_Office_task_019_prd_system_design_breakdown'
PRD_CONTRACT='2a473675b08481052bc5808a5387e85fa0152bdcf4ed5448e922e9023a4097d5'
PRD_SOURCE='4ab6e8cd79ecc6aeeb8fc6294dc4f7257947365162c8cba1511a202b89989035'
CUSTOMER_TASK='02_Office_task_013_customer_remediation_pack'
CUSTOMER_CONTRACT='af1f136e9c417075c20e6e694af74eadbe14fd24f623356f08960af17b8da5e3'
CUSTOMER_SOURCE='3cc8ca96c44618391fad974313fc84ac83e15532c525acff4d1d20fd8cc97955'

def customer_failure(manifest,contract,audit,worker):
    error=worker.get('error') or {}
    match=re.fullmatch(r'EVALUATOR_EVIDENCE_BUDGET_EXCEEDED: (\d+); no candidate truncation performed',error.get('message',''))
    return (contract.get('task_id')==CUSTOMER_TASK
        and manifest.get('identity',{}).get('task_id')==CUSTOMER_TASK
        and manifest.get('digests',{}).get('contract_sha256')==CUSTOMER_CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==CUSTOMER_SOURCE
        and audit.get('status')=='failed' and audit.get('identity')==manifest.get('identity')
        and audit.get('runtime_workspace',{}).get('drifted') is False
        and audit.get('worker',{}).get('return_code')==1
        and audit.get('worker',{}).get('process_tree_cleanup',{}).get('remaining') is False
        and worker.get('ok') is False and worker.get('result') is None
        and error.get('type')=='EvaluatorEvidenceError' and match is not None and int(match.group(1))>74000)

EXTRA={
 '02_Office_task_029_monitoring_weekly_docx':('967f54a181a67fe91b7513b6d81d61a6badd7d7def1c6fcc1033d5d69fae762a','93859e60892a717a0adfb8e3d1feb78a7baa6bdd0f33ea707b520e5c3a5af309',55000,'evidence_error: exported evidence exceeds reserved 55000 characters; expand collection/review manually, not a candidate zero'),
 '02_Office_task_030_service_center_consolidation':('1cf27d0d5844d40d08824e606bc92e1efb9514bc0d780051793d85b270d586cc','f29d880bb031209ecca324e32f1761598adf407f354ae8975d2a288d805d2378',74000,'evaluator_error: complete evidence exceeds 74000 reserved characters; collect supplement before semantic scoring, never candidate zero'),
}
def extra_files(attempt,manifest,contract,audit,worker):
    row=EXTRA.get(contract.get('task_id'));error=worker.get('error',{})
    if (not row or manifest['digests']['contract_sha256']!=row[0] or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=row[1]
        or audit.get('status')!='failed' or worker.get('ok') is not False or worker.get('result') is not None
        or error.get('type')!='RuntimeError' or error.get('message')!=row[3]):return None
    folder=Path(attempt)/'infrastructure-evidence/complete-extra-evidence-budget'
    if not folder.exists():folder=Path(attempt)/manifest['runtime']['workspace_argument']/'evaluator_evidence'
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(Path(attempt).resolve()):raise ValueError('EXTRA_COLLECTION_UNSAFE')
    paths=sorted(folder.iterdir());total=0
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.suffix!='.json':raise ValueError('EXTRA_COLLECTION_SCOPE')
        text=path.read_text(encoding='utf-8');data=json.loads(text)
        if isinstance(data,dict) and data.get('truncated') is True:raise ValueError('EXTRA_COLLECTION_TRUNCATED')
        total+=len(text)
    if not paths or total<=row[2]:raise ValueError('EXTRA_COLLECTION_OVERFLOW_NOT_PROVEN')
    return paths
def preserve_extra(rt,attempt,manifest,contract,audit,worker):
    paths=extra_files(attempt,manifest,contract,audit,worker);target=Path(attempt)/'infrastructure-evidence/complete-extra-evidence-budget';target.mkdir(parents=True,exist_ok=False)
    for path in paths:shutil.copyfile(path,target/path.name)
    return [{'path':p.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(p)} for p in extra_files(attempt,manifest,contract,audit,worker)]
def verify_extra(rt,attempt,manifest,contract,audit,worker,records):
    actual=[{'path':p.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(p)} for p in extra_files(attempt,manifest,contract,audit,worker)]
    if actual!=records:raise ValueError('EXTRA_COLLECTION_PROOF_DRIFT')
def prd_failure(manifest,contract,audit,worker):
    error=worker.get('error',{})
    match=re.fullmatch(r'EVALUATOR_EVIDENCE_BUDGET: (\d+) characters require larger collection budget; do not truncate or score a partial plan',error.get('message',''))
    return (contract.get('task_id')==PRD_TASK and manifest['digests']['contract_sha256']==PRD_CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==PRD_SOURCE
        and audit.get('status')=='failed' and worker.get('ok') is False and worker.get('result') is None
        and error.get('type')=='RuntimeError' and match is not None and int(match.group(1))>72000)
def files(attempt,manifest,contract,audit,worker):
    error=worker.get('error',{})
    if (contract.get('task_id')!=TASK or manifest['digests']['contract_sha256']!=CONTRACT
        or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE
        or audit.get('status')!='failed' or worker.get('ok') is not False or worker.get('result') is not None
        or error.get('type')!='EvidenceError' or error.get('message')!=ERROR):return None
    folder=Path(attempt)/PRESERVED
    if not folder.exists():folder=Path(attempt)/manifest['runtime']['workspace_argument']/'evaluator_evidence_018'
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(Path(attempt).resolve()):raise ValueError('COMPLETE_EVIDENCE_FAILURE_UNSAFE')
    rows=[];total=0
    for path in sorted(folder.iterdir()):
        if (path.is_symlink() or not path.is_file()
            or not re.fullmatch(r'(?:00_manifest|01_truth_\d{3}|10_candidate_\d{3}_\d{3})\.json',path.name)):raise ValueError('COMPLETE_EVIDENCE_FAILURE_SCOPE')
        text=path.read_text(encoding='utf-8');data=json.loads(text)
        if len(text)>18000 or data.get('truncated') is not False:raise ValueError('COMPLETE_EVIDENCE_FAILURE_TRUNCATED')
        total+=len(text);rows.append(path)
    if not rows or total<=74000 or not any(p.name=='00_manifest.json' for p in rows):raise ValueError('COMPLETE_EVIDENCE_FAILURE_NOT_PROVEN')
    return rows
def preserve(rt,attempt,manifest,contract,audit,worker):
    paths=files(attempt,manifest,contract,audit,worker)
    target=Path(attempt)/PRESERVED;target.mkdir(parents=True,exist_ok=False)
    for path in paths:shutil.copyfile(path,target/path.name)
    records=[{'path':p.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(p)} for p in files(attempt,manifest,contract,audit,worker)]
    proof={'profile':'complete-business-evidence-resource-failure/v1','files':records,'original_bytes_retained':True}
    path=target.parent/'complete-business-evidence-budget-proof.json';rt._write_new_json(path,proof)
    return {'path':path.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(path)}
def verify(rt,attempt,manifest,contract,audit,worker,binding):
    path=Path(attempt)/binding['path']
    if path.is_symlink() or not path.resolve().is_relative_to(Path(attempt).resolve()) or rt._sha256_file(path)!=binding['sha256']:raise ValueError('COMPLETE_EVIDENCE_FAILURE_PROOF_DRIFT')
    proof=rt._read_json(path);records=[{'path':p.relative_to(attempt).as_posix(),'sha256':rt._sha256_file(p)} for p in files(attempt,manifest,contract,audit,worker)]
    if proof.get('files')!=records or proof.get('original_bytes_retained') is not True:raise ValueError('COMPLETE_EVIDENCE_FAILURE_PROOF_DRIFT')
