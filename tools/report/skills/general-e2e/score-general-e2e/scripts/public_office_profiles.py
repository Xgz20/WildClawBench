"""Opt-in, exact-contract public Office metadata equivalence for new attempts.

Legacy manifests have no marker and retain their original effective source.
The original candidate, contract, public files and numeric formulas are intact.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import office_input_compat

PROFILE = 'canonical-public-office-cwm-only/v2'
CATALOG_SHA = '567a53a22dc35e198bd72696676cd444e55963b0a72b549b9989c875e8c48313'


def registry():
    path = Path(__file__).resolve().parents[1]/'data/public-input-baselines/general116-office-inputs-v2.json'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=CATALOG_SHA:
        raise ValueError('PUBLIC_OFFICE_V2_CATALOG_DRIFT')
    return json.loads(data)['profiles']


def marker(contract, contract_sha256):
    for row in registry():
        if (row['task_id']==contract.get('task_id') and row['contract_sha256']==contract_sha256
                and row['automated_source_sha256']==hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()):
            return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,
                    'contract_sha256':contract_sha256,'source_sha256':row['automated_source_sha256']}
    return None


MATCHER = '''
def _ge2e_public_office_matches(path, expected_sha256, workspace, *, role='input_snapshot'):
    workspace=_ge2e_Path(workspace)
    path=_ge2e_Path(path)
    try:
        relative=path.relative_to(workspace).as_posix()
        if not path.resolve().is_relative_to(workspace.resolve()):
            return False
    except (ValueError,OSError):
        return False
    if role=='input_snapshot':
        baseline_path=relative
    elif role=='unchanged_template':
        baseline_path=_GE2E_PUBLIC_OFFICE_PROFILE['output_template_paths'].get(relative)
    else:
        return False
    baseline=next((row for row in _GE2E_PUBLIC_OFFICE_PROFILE['files']
                   if row['path']==baseline_path and row['sha256']==expected_sha256),None)
    if baseline is None or not path.is_file():
        return False
    try:
        proof=compare_office_cwm(_ge2e_base64.b64decode(baseline['base64'],validate=True),
                                 path.read_bytes(),expected_sha256)
    except (ValueError,KeyError,_ge2e_zipfile.BadZipFile,_ge2e_et.ParseError):
        return False
    if proof is None:
        return False
    evidence_dir=workspace/_GE2E_PUBLIC_OFFICE_PROFILE['evidence_directory']
    if evidence_dir.is_symlink() or not evidence_dir.resolve().is_relative_to(workspace.resolve()):
        raise ValueError('PUBLIC_OFFICE_V2_UNSAFE_AUDIT_DIRECTORY')
    evidence_dir.mkdir(exist_ok=True)
    output=evidence_dir/'00_public_office_metadata_variance.json'
    if output.exists() and (output.is_symlink() or output.stat().st_nlink!=1):
        raise ValueError('PUBLIC_OFFICE_V2_UNSAFE_AUDIT_FILE')
    rows=_ge2e_json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    proof.update(profile='canonical-public-office-cwm-only/v2',
                 public_input_path=baseline_path,observed_path=relative,comparison_role=role,
                 original_contract_sha256=_GE2E_PUBLIC_OFFICE_PROFILE['contract_sha256'],
                 original_source_sha256=_GE2E_PUBLIC_OFFICE_PROFILE['automated_source_sha256'],
                 not_agent_action_evidence=True)
    if proof not in rows:
        rows.append(proof)
    output.write_text(_ge2e_json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return True
'''


def effective_source(manifest, original, current, previous_receipt):
    frozen = manifest.get('runtime',{}).get('public_office_input_profile')
    if frozen is None:
        return current, previous_receipt
    task_id = manifest.get('identity',{}).get('task_id')
    original_sha = hashlib.sha256(original.encode('utf-8')).hexdigest()
    contract_sha = manifest.get('digests',{}).get('contract_sha256')
    rows = [r for r in registry() if r['task_id']==task_id and r['contract_sha256']==contract_sha
            and r['automated_source_sha256']==original_sha]
    expected = {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,
                'contract_sha256':contract_sha,'source_sha256':original_sha}
    if len(rows)!=1 or frozen!=expected:
        raise ValueError('PUBLIC_OFFICE_V2_FROZEN_PROFILE_MISMATCH')
    row = rows[0]
    for patch in row['replacements']:
        if current.count(patch['original'])!=1:
            raise ValueError('PUBLIC_OFFICE_V2_SOURCE_SPAN_MISMATCH')
        current = current.replace(patch['original'],patch['replacement'])
    # Embed the unchanged v1 comparator. It validates every business OPC member
    # and all non-CWM metadata; it never rewrites any source Office file.
    helper = Path(office_input_compat.__file__).read_text(encoding='utf-8')
    payload = {key:row[key] for key in ['files','evidence_directory','output_template_paths',
                                      'contract_sha256','automated_source_sha256']}
    effective = helper+'\n_GE2E_PUBLIC_OFFICE_PROFILE = '+repr(payload)+'\n'+MATCHER+'\n'+current
    receipt = {'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
               'correction_id':PROFILE,'task_id':task_id,
               'original_source_sha256':original_sha,
               'effective_source_sha256':hashlib.sha256(effective.encode('utf-8')).hexdigest(),
               'contract_sha256':contract_sha,'baseline_catalog_sha256':CATALOG_SHA,
               'canonical_public_inputs':[{'path':f['path'],'sha256':f['sha256']} for f in row['files']],
               'candidate_rewritten':False,'audit_directory':row['evidence_directory'],
               'reason':'仅接受已冻结公开输入的严格CWM属性变体，业务OPC部件、公式、样式及其他元数据保持原字节；保持原分母、权重和计算公式。'}
    if previous_receipt is not None:
        receipt['prior_correction'] = previous_receipt
    return effective, receipt
