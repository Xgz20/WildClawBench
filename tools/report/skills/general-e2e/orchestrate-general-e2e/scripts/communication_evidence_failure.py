"""Preserve a source-bound complete business-evidence resource failure."""
from pathlib import Path
import hashlib,json,re,shutil
TASK='02_Office_task_018_targeted_repair_communication_pack'
CONTRACT='303328777610178aab42baa175aa2e3c65dd0ccf868b5200d200a0597704e107'
SOURCE='d2e1e3adf18ce595499464db66e3bc1a728ccabc64bc887d02ef70356eac17bf'
ERROR='evaluator_error: complete evidence exceeds 74000 characters; supplementary collection required, never candidate zero'
PRESERVED='infrastructure-evidence/complete-business-evidence-budget'
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
