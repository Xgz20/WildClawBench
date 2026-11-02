"""Exact reviewed v2 identities; no historical contract bytes are relabelled."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

CATALOG_SHA = "1c78f388a4a476e43141fa08426b21381acfa3335d7ea3e58b90e0d5b163c449"

def registry():
    data=(Path(__file__).resolve().parents[1]/'data/general70-source-identities-v2.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=CATALOG_SHA:raise ValueError('SOURCE_IDENTITY_CATALOG_DRIFT')
    return json.loads(data)['profiles']

def accepted_contracts(original):
    row=registry().get(original)
    return {original,row['contract_sha256']} if row else {original}

def accepted_source_hashes(original):
    return {original, *[row['automated_source_sha256'] for row in registry().values()
                       if row.get('original_automated_source_sha256')==original]}

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
    return result
