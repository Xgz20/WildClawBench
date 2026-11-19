"""An exact producer's missing-deck branch has status, not candidate pages."""
import hashlib
import json
from pathlib import Path
import generated_evidence_globs

PROFILE = 'declared-missing-deck-evidence-absence/v1'
TASK = '02_Office_task_017_ipad_product_presentation'
PATTERN = 'evaluator_evidence/02_candidate_*.json'
CONTRACT = 'ef714863523034a7c467a51e6768bf0dda607cd550537b5491fda52c85853943'
SOURCE = '1b1db22b6427ab8cfe4fe3472e7af62e32adf2a0e72484345805af963221fc46'

def new_marker(contract, contract_sha, dataset):
    return marker({'identity':{'task_id':contract.get('task_id')},
                   'digests':{'contract_sha256':contract_sha},'dataset':dataset},contract)

def marker(manifest, contract):
    row = generated_evidence_globs.policy(manifest, contract)
    if (row is None or row['task_id'] != TASK or row['contract_sha256'] != CONTRACT
        or row['source_sha256'] != SOURCE or row['dataset']['id'] != 'general-custom70-v6'):
        return None
    return {'profile': PROFILE, 'contract_sha256': CONTRACT, 'source_sha256': SOURCE,
            'conditional_pattern': PATTERN}

def absence(root, workspace, relative, manifest, contract):
    expected = marker(manifest, contract)
    frozen = manifest.get('runtime', {}).get('conditional_generated_evidence_profile')
    if frozen is not None and frozen != expected:raise ValueError('CONDITIONAL_EVIDENCE_PROFILE_DRIFT')
    if expected is None or relative != PATTERN:return None
    root,workspace=Path(root),Path(workspace)
    suffix=Path(manifest['runtime']['workspace_argument']).relative_to(manifest['paths']['runtime_workspace'])
    original=root/manifest['paths']['candidate_original']/suffix
    for base in (original,workspace):
        results=base/'results'
        if results.is_symlink():return None
        if results.exists() and (not results.is_dir() or any(p.suffix.lower()=='.pptx' and p.is_file()
            and not p.name.startswith('~$') for p in results.rglob('*'))):return None
    if (workspace/'evaluator_evidence').is_symlink():return None
    path=workspace/'evaluator_evidence/00_status.json'
    if path.is_symlink() or not path.is_file():return None
    raw=path.read_bytes();status=json.loads(raw)
    expected_status={'candidate_status':'missing','candidates':[],'reference_verified':True,
        'native_probe_is_grader_action_not_agent_self_check':True,'native_editable_page_ratio':0.0,
        'delivery_usable':0.0,'evidence_files':['01_reference.json'],
        'evidence_complete_within_collector_budget':True}
    if (status!=expected_status or any(type(status[k]) not in (int,float)
        for k in ['native_editable_page_ratio','delivery_usable'])):return None
    worker=json.loads((root/'worker/result.json').read_text(encoding='utf-8'))
    if (worker.get('ok') is not True or worker.get('raw_result',{}).get('diagnostics')!=status
        or worker.get('result')!={'delivery_usable':0.0,'overall_score':0.0}):return None
    return {**expected,'status_relative_path':'evaluator_evidence/00_status.json',
        'status_sha256':hashlib.sha256(raw).hexdigest(),'candidate_deck_count':0,
        'candidate_pages_present':False,'placeholder_created':False,
        'numeric_decisions_assigned':False,'source_receipts_modified':False}
