#!/usr/bin/env python3
"""Freeze the reviewed 70-task revision and its exact runtime admissions.

No model/Harness is run. Historical locks and registries are never modified.
--write is an explicit administrator operation; otherwise verify current bytes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from eval_general_e2e.datasets.bundle import (GENERAL70_V2_DEFINITION, GENERAL116_DEFINITION,
    compile_dataset, dataset_manifest_path, load_manifest_lock, _parse_task_source, _strip_codeblock)
from eval_general_e2e.datasets.source_history import frozen_task_path


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()


def outputs(repo):
    original,_=compile_dataset(repo,definition=GENERAL116_DEFINITION)
    if original!=load_manifest_lock(dataset_manifest_path(original['dataset_id'])):
        raise ValueError('HISTORICAL_DATASET_DRIFT')
    new,members=compile_dataset(repo,definition=GENERAL70_V2_DEFINITION)
    old={t['task_id']:t for t in original['tasks']}
    contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in members if m.path.endswith('/private-scoring/contract.json')}
    identities={}
    for task in new['tasks']:
        prev=old[task['task_id']]
        if (task['digests']['workspace_exec_sha256']!=prev['digests']['workspace_exec_sha256']
                or task['digests']['prompt_sha256']!=prev['digests']['prompt_sha256']
                or task['grading_weights']!=prev['grading_weights']):
            raise ValueError('PUBLIC_TASK_OR_BUDGET_CHANGED: '+task['task_id'])
        original_source=_strip_codeblock(_parse_task_source(frozen_task_path(repo/prev['source']['task_path']))[1]['Automated Checks'])
        identities[prev['digests']['scoring_contract_sha256']]={'task_id':task['task_id'],
            'contract_sha256':task['digests']['scoring_contract_sha256'],
            'automated_source_sha256':hashlib.sha256(contracts[task['task_id']]['automated_checks'].encode()).hexdigest(),
            'original_automated_source_sha256':hashlib.sha256(original_source.encode()).hexdigest(),
            'dataset':{'id':new['dataset_id'],'digest':new['dataset_digest']},
            'original_execution_inputs_sha256':prev['digests']['workspace_exec_sha256']}
    skills=repo/'tools/report/skills/general-e2e/score-general-e2e'
    identity_file=skills/'data/general70-source-identities-v2.json'
    identity_bytes=encoded({'schema_version':'general-e2e-reviewed-source-identities/v1','dataset':new['dataset_id'],'profiles':identities})
    helper=skills/'scripts/source_identities.py'
    helper_bytes=re.sub(r'^CATALOG_SHA = "[a-f0-9]{64}"',
        'CATALOG_SHA = "'+hashlib.sha256(identity_bytes).hexdigest()+'"',helper.read_text(),flags=re.MULTILINE).encode()
    folder=repo/'tools/report/e2e-shared/independent-validity'
    legacy=json.loads((folder/'independent_validity_profiles.json').read_text())['profiles'];variants={}
    for tid,spec in legacy.items():
        if tid not in contracts:continue
        row=deepcopy(spec);entry=identities[old[tid]['digests']['scoring_contract_sha256']]
        row['contract_sha256']=entry['contract_sha256'];row['automated_source_sha256']=entry['automated_source_sha256'];variants[tid]=row
    # Reuse the dataset builder's canonical persisted manifest formatting.
    manifest_bytes=(json.dumps(new,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    return {dataset_manifest_path(new['dataset_id']):manifest_bytes,identity_file:identity_bytes,
        helper:helper_bytes,folder/'independent_validity_profiles_70_v2.json':encoded({'schema_version':1,'dataset_id':new['dataset_id'],'profiles':variants})}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    generated=outputs(ROOT)
    for path,data in generated.items():
        if args.write:path.write_bytes(data)
        elif not path.is_file() or path.read_bytes()!=data:raise SystemExit('REVISION_OUTPUT_DRIFT: '+str(path))
    print(json.dumps({'status':'PASS','mode':'write' if args.write else 'check','task_count':70,'files':len(generated)}))


if __name__=='__main__':main()
