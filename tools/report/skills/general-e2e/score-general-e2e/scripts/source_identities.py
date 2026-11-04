"""Exact reviewed v2 identities; no historical contract bytes are relabelled."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

CATALOG_SHA = "1c78f388a4a476e43141fa08426b21381acfa3335d7ea3e58b90e0d5b163c449"
V3_CATALOG_SHA = "10cbcb4e20102385e84e2f76fd6d6e7412790fd62296439a3793298407d93f1d"

def registry():
    data=(Path(__file__).resolve().parents[1]/'data/general70-source-identities-v2.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=CATALOG_SHA:raise ValueError('SOURCE_IDENTITY_CATALOG_DRIFT')
    return json.loads(data)['profiles']

def accepted_contracts(original):
    row=registry().get(original)
    values={original,row['contract_sha256']} if row else {original}
    revisions=revision_registry()
    return values | {revisions[key]['contract_sha256'] for key in values if key in revisions}

def accepted_source_hashes(original):
    rows=[row for row in registry().values() if row.get('original_automated_source_sha256')==original]
    revisions=revision_registry()
    return {original,*[row['automated_source_sha256'] for row in rows],
        *[revisions[row['contract_sha256']]['automated_source_sha256'] for row in rows if row['contract_sha256'] in revisions]}


def revision_registry():
    data=(Path(__file__).resolve().parents[1]/'data/general70-source-identities-v3.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=V3_CATALOG_SHA:raise ValueError('SOURCE_V3_IDENTITY_CATALOG_DRIFT')
    return json.loads(data)['profiles']


def materialized_rule_review_profile(contract,contract_sha):
    source=contract.get('automated_checks')
    if not isinstance(source,str):return None
    source_sha=hashlib.sha256(source.encode()).hexdigest()
    rows=[row for row in revision_registry().values() if row['task_id']==contract.get('task_id')
          and row['contract_sha256']==contract_sha and row['automated_source_sha256']==source_sha]
    return rows[0].get('rule_review_profile') if len(rows)==1 else None

def registry_variants(rows):
    result=list(rows)
    for row in rows:
        variant=registry().get(row.get('contract_sha256'))
        if variant is None or variant['task_id']!=row['task_id']:continue
        value=deepcopy(row);value['contract_sha256']=variant['contract_sha256']
        for key in ('source_sha256','automated_source_sha256'):
            if key in value:value[key]=variant['automated_source_sha256']
        if 'dataset' in value:value['dataset']=variant['dataset']
        result.append(value)
    revisions=revision_registry()
    for row in list(result):
        variant=revisions.get(row.get('contract_sha256'))
        if variant is None or variant['task_id']!=row['task_id']:continue
        value=deepcopy(row);value['contract_sha256']=variant['contract_sha256']
        for key in ('source_sha256','automated_source_sha256'):
            if key in value:value[key]=variant['automated_source_sha256']
        if 'dataset' in value:value['dataset']=variant['dataset']
        if value not in result:result.append(value)
    return result
