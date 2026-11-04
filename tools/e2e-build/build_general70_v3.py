#!/usr/bin/env python3
"""Freeze v3 while independently rebuilding every historical dataset lock."""
from pathlib import Path
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from eval_general_e2e.datasets.bundle import (DEFAULT_DEFINITION,GENERAL116_DEFINITION,
    GENERAL70_V2_DEFINITION,GENERAL70_V3_DEFINITION,compile_dataset,dataset_manifest_path,load_manifest_lock)

def outputs():
    for definition in [DEFAULT_DEFINITION,GENERAL116_DEFINITION,GENERAL70_V2_DEFINITION]:
        manifest,_=compile_dataset(ROOT,definition=definition)
        if manifest!=load_manifest_lock(dataset_manifest_path(definition.dataset_id)):
            raise ValueError('HISTORICAL_DATASET_DRIFT:'+definition.dataset_id)
    original=load_manifest_lock(dataset_manifest_path('general-custom70-v2'))
    current,members=compile_dataset(ROOT,definition=GENERAL70_V3_DEFINITION)
    previous={t['task_id']:t for t in original['tasks']}
    contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in members if m.path.endswith('/private-scoring/contract.json')}
    profiles={}
    for task in current['tasks']:
        old=previous[task['task_id']]
        for key in ['workspace_exec_sha256','prompt_sha256','workspace_gt_sha256']:
            if key in old['digests'] and task['digests'][key]!=old['digests'][key]:
                raise ValueError('PUBLIC_INPUT_OR_GT_CHANGED:'+task['task_id']+':'+key)
        if task['grading_weights']!=old['grading_weights']:raise ValueError('WEIGHTS_CHANGED')
        if task['digests']['scoring_contract_sha256']==old['digests']['scoring_contract_sha256']:continue
        source=contracts[task['task_id']]['automated_checks']
        profiles[old['digests']['scoring_contract_sha256']]={'task_id':task['task_id'],
            'contract_sha256':task['digests']['scoring_contract_sha256'],
            'automated_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'dataset':{'id':current['dataset_id'],'digest':current['dataset_digest']},
            **({'rule_review_profile':'warranty-recovery-reason-semantic-review/v1'}
               if task['task_id']=='02_Office_task_010_warranty_recovery_allocation' else {})}
    assert len(profiles)==8
    encode=lambda v:(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    globs=json.loads((ROOT/'tools/report/skills/general-e2e/score-general-e2e/data/reviewed-generated-file-globs-v2.json').read_text())
    globs['schema_version']='general-e2e-reviewed-generated-file-globs/v3'
    for row in globs['profiles']:
        row['dataset']={'id':current['dataset_id'],'digest':current['dataset_digest']}
    return {dataset_manifest_path(current['dataset_id']):encode(current),
        **{ROOT/f'tools/report/skills/general-e2e/{name}/data/reviewed-generated-file-globs-v3.json':encode(globs)
           for name in ['score-general-e2e','orchestrate-general-e2e']},
        ROOT/'tools/report/skills/general-e2e/score-general-e2e/data/general70-source-identities-v3.json':encode({
            'schema_version':'general-e2e-reviewed-source-identities/v1','dataset':'general-custom70-v3','profiles':profiles})}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    for path,data in outputs().items():
        if args.write:path.write_bytes(data)
        elif not path.is_file() or path.read_bytes()!=data:raise SystemExit('REVISION_OUTPUT_DRIFT:'+str(path))
    print(json.dumps({'status':'PASS','task_count':70,'historical_locks_verified':3,'materialized_repairs':8}))
