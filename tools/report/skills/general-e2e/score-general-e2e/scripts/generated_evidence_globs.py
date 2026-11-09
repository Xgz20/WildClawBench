"""Reviewed contract filename globs; exact task/source/contract/dataset binding.

Only the filename may contain glob syntax. No recursive directory matching,
symlink traversal, arbitrary namespaces or missing-file fallback is allowed.
"""
from __future__ import annotations
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath

PROFILE='reviewed-generated-file-globs/v1'
CATALOG_SHA='edb3f823f536d9d0ab25fd3f0147582e95cbb1dc42af8723623501e455f0dac4'
CATALOG_V2_SHA='7bb0e0d8a5877c2406ffd575d42adacbbdf31223e9dc5b894eaaa3851f76054b'
CATALOG_V3_SHA='7cb950bb8610663cf22d85f9fc62bdbbbeab0bbaee04149bc48ea3e1711fc8c1'
CATALOG_V4_SHA='b7945f7ee10d477c89cb06ace410e97ad7c4b00443d04fc3ec5d1b6faaa79452'
CATALOG_V5_SHA='5f0eec302f18d98408b564423d41ab8e9278d41cf237beb6addcfe04209ae406'
ERROR_KIND='declared-evidence-glob-implementation-repair/v1'


def registry(dataset_id=None):
    version={'general-custom70-v2':'v2','general-custom70-v3':'v3','general-custom70-v4':'v4','general-custom70-v5':'v5'}.get(dataset_id,'v1')
    expected={'v1':CATALOG_SHA,'v2':CATALOG_V2_SHA,'v3':CATALOG_V3_SHA,'v4':CATALOG_V4_SHA,'v5':CATALOG_V5_SHA}[version]
    raw=(Path(__file__).resolve().parents[1]/('data/reviewed-generated-file-globs-'+version+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('EVIDENCE_GLOB_CATALOG_DRIFT')
    return json.loads(raw)['profiles']


def policy(manifest,contract):
    rows=[r for r in registry(manifest.get('dataset',{}).get('id')) if r['task_id']==manifest.get('identity',{}).get('task_id')]
    if not rows:return None
    row=rows[0];source=contract.get('automated_checks')
    declared=[e.get('path') for e in (contract.get('judge_evidence') or {}).get('required',[]) if isinstance(e,dict)]
    if (len(rows)!=1 or contract.get('task_id')!=row['task_id'] or not isinstance(source,str)
            or manifest.get('digests',{}).get('contract_sha256')!=row['contract_sha256']
            or manifest.get('dataset')!=row['dataset']
            or hashlib.sha256(source.encode('utf-8')).hexdigest()!=row['source_sha256']
            or not set(row['patterns']).issubset(declared)):
        return None
    return row


def descriptor(manifest,contract):
    row=policy(manifest,contract)
    catalog_sha={'general-custom70-v2':CATALOG_V2_SHA,'general-custom70-v3':CATALOG_V3_SHA,'general-custom70-v4':CATALOG_V4_SHA,'general-custom70-v5':CATALOG_V5_SHA}.get(manifest.get('dataset',{}).get('id'),CATALOG_SHA)
    return None if row is None else {'profile':PROFILE,'catalog_sha256':catalog_sha,
        'contract_sha256':row['contract_sha256'],'source_sha256':row['source_sha256'],'patterns':row['patterns']}


def targets(workspace,relative,manifest,contract):
    workspace=Path(workspace);row=policy(manifest,contract)
    if row is None or relative not in row['patterns']:return [workspace/relative]
    path=PurePosixPath(relative)
    if (path.is_absolute() or '..' in path.parts or len(path.parts)<2 or path.parts[0]!='evaluator_evidence'
            or any(any(c in part for c in '*?[') for part in path.parts[:-1]) or '**' in path.name):
        raise ValueError('EVIDENCE_GLOB_PATTERN_INVALID')
    parent=workspace
    for part in path.parts[:-1]:
        parent=parent/part
        if parent.is_symlink():raise ValueError('EVIDENCE_GLOB_LINK_INVALID')
        if not parent.exists():return []
        if not parent.is_dir():raise ValueError('EVIDENCE_GLOB_PARENT_INVALID')
    if not parent.resolve().is_relative_to(workspace.resolve()):raise ValueError('EVIDENCE_GLOB_PATH_ESCAPE')
    found=sorted(p for p in parent.iterdir() if fnmatch.fnmatchcase(p.name,path.name))
    if any(p.is_symlink() or not p.is_file() for p in found):raise ValueError('EVIDENCE_GLOB_MATCH_NOT_REGULAR_FILE')
    return found
