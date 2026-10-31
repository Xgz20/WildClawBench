"""Exact original-dataset reference guard repairs; never rewrite reference bytes.

The registry binds the original Git revision, frozen dataset/member and contract.
Only the stale checksum literal changes. Every business comparison stays exact.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

PROFILE='canonical-private-reference-guard/v1'
CATALOG_SHA='f3f26fff6a969866c6c1f825cb34a8b880926330050201b3dd51c7cf9b1950e7'
ERROR_KIND='dataset-private-reference-guard-repair/v1'


def registry():
    path=Path(__file__).resolve().parents[1]/'data/private-reference-guards-v1.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:
        raise ValueError('PRIVATE_REFERENCE_GUARD_CATALOG_DRIFT')
    return json.loads(raw)['profiles']


def registered(contract,contract_sha,dataset):
    source=contract.get('automated_checks','')
    if not isinstance(source,str):return None
    source_sha=hashlib.sha256(source.encode('utf-8')).hexdigest()
    rows=[r for r in registry() if r['task_id']==contract.get('task_id')
        and r['contract_sha256']==contract_sha and r['source_sha256']==source_sha
        and r['dataset_id']==dataset.get('id') and r['dataset_digest']==dataset.get('digest')]
    if len(rows)>1:raise ValueError('PRIVATE_REFERENCE_GUARD_AMBIGUOUS')
    return rows[0] if rows else None


def marker(contract,contract_sha,dataset,entries):
    row=registered(contract,contract_sha,dataset)
    if row is None:return None
    index={e['path']:e for e in entries}
    for ref in row['references']:
        actual=index.get(ref['path'],{})
        if (actual.get('type',actual.get('kind'))!='file' or actual.get('sha256')!=ref['canonical_sha256']
                or actual.get('size')!=ref['size']):
            raise ValueError('PRIVATE_REFERENCE_GUARD_NONCANONICAL_INPUT')
    return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,'task_id':row['task_id'],
        'contract_sha256':contract_sha,'source_sha256':row['source_sha256'],
        'dataset_id':row['dataset_id'],'dataset_digest':row['dataset_digest'],
        'references':row['references']}


def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('private_reference_guard_profile')
    if frozen is None:return current,prior
    contract={'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original}
    expected=marker(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{}),
        manifest.get('private_scoring',{}).get('workspace_entries',[]))
    if expected is None or frozen!=expected:
        raise ValueError('PRIVATE_REFERENCE_GUARD_FROZEN_PROFILE_MISMATCH')
    row=registered(contract,expected['contract_sha256'],manifest['dataset'])
    for ref in row['replacements']:
        old=repr(ref['declared_sha256']);new=repr(ref['canonical_sha256'])
        if current.count(old)!=ref['occurrences']:
            raise ValueError('PRIVATE_REFERENCE_GUARD_SOURCE_SPAN_MISMATCH')
        current=current.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id':PROFILE,'task_id':contract['task_id'],'contract_sha256':expected['contract_sha256'],
        'original_source_sha256':expected['source_sha256'],
        'effective_source_sha256':hashlib.sha256(current.encode('utf-8')).hexdigest(),
        'catalog_sha256':CATALOG_SHA,'canonical_reference_guards':expected['references'],'checksum_literal_repairs':row['replacements'],
        'public_text_transport_guards':row.get('public_text_guards',[]),
        'reference_bytes_rewritten':False,'candidate_rewritten':False,
        'reason':'原提交、版本化数据manifest与冻结ZIP成员逐字节一致，仅修正原规则过时的私有参考校验常量；保持原参考、候选、业务比较、规则权重和分母，任何未注册输入漂移仍拒绝。'}
    if prior:receipt['prior_correction']=prior
    return current,receipt


def matches_old_failure(attempt,manifest,contract,error):
    """Keep the failed old attempt, only after proving its reference is canonical."""
    row=registered(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{}))
    if row is None or error.get('type')!='EvidenceError':return False
    refs=[r for r in row['references'] if error.get('message')=='Private reference mismatch: '+r['path']]
    if len(refs)!=1:return False
    expected=marker(contract,manifest['digests']['contract_sha256'],manifest['dataset'],
        manifest['private_scoring']['workspace_entries'])
    root=Path(attempt).resolve(strict=True)
    for ref in expected['references']:
        path=root/manifest['paths']['gt']/ref['path']
        if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root)
                or path.stat().st_size!=ref['size']
                or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['canonical_sha256']):
            return False
    return True
