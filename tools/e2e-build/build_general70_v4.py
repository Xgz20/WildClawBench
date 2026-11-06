#!/usr/bin/env python3
"""Freeze the full 70-task reference-only release and its exact admissions."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from eval_general_e2e.datasets.bundle import (
    DATASETS, GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION,
    compile_dataset, dataset_manifest_path, load_manifest_lock,
)

INFO004 = '01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'
sha = lambda data: hashlib.sha256(data).hexdigest()
encode = lambda data: (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def outputs():
    historical = []
    for definition in DATASETS.values():
        if definition.dataset_id == GENERAL70_V4_DEFINITION.dataset_id:
            continue
        manifest, members = compile_dataset(ROOT, definition=definition)
        if manifest != load_manifest_lock(dataset_manifest_path(definition.dataset_id)):
            raise ValueError('HISTORICAL_DATASET_DRIFT:' + definition.dataset_id)
        historical.append(definition.dataset_id)
        del members
    before = load_manifest_lock(dataset_manifest_path(GENERAL70_V3_DEFINITION.dataset_id))
    after, members = compile_dataset(ROOT, definition=GENERAL70_V4_DEFINITION)
    contracts = {json.loads(m.data)['task_id']: json.loads(m.data) for m in members
                 if m.path.endswith('/private-scoring/contract.json')}
    del members
    previous = {t['task_id']: t for t in before['tasks']}
    assert [t['task_id'] for t in after['tasks']] == [t['task_id'] for t in before['tasks']]
    assert after['statistics'] == before['statistics'] and after['task_count'] == 70
    changed = []
    for task in after['tasks']:
        old = previous[task['task_id']]
        if task != old:
            changed.append(task['task_id'])
        for key in ['prompt_sha256', 'workspace_exec_sha256', 'execution_contract_sha256']:
            assert task['digests'][key] == old['digests'][key], (task['task_id'], key)
        assert task['grading_weights'] == old['grading_weights']
    assert changed == [INFO004], changed

    dataset = {'id': after['dataset_id'], 'digest': after['dataset_digest']}
    profiles = {}
    for task in after['tasks']:
        old = previous[task['task_id']]
        profiles[old['digests']['scoring_contract_sha256']] = {
            'task_id': task['task_id'],
            'contract_sha256': task['digests']['scoring_contract_sha256'],
            'automated_source_sha256': sha(contracts[task['task_id']]['automated_checks'].encode()),
            'dataset': dataset,
        }
    identities = encode({'schema_version': 'general-e2e-reviewed-source-identities/v1',
                         'dataset': after['dataset_id'], 'baseline_dataset': {
                             'id': before['dataset_id'], 'digest': before['dataset_digest']},
                         'profiles': profiles})
    globs = json.loads((ROOT / 'tools/report/skills/general-e2e/score-general-e2e/data/reviewed-generated-file-globs-v3.json').read_text())
    globs['schema_version'] = 'general-e2e-reviewed-generated-file-globs/v4'
    by_id = {t['task_id']: t for t in after['tasks']}
    for row in globs['profiles']:
        assert row['contract_sha256'] == by_id[row['task_id']]['digests']['scoring_contract_sha256']
        row['dataset'] = dataset
    glob_bytes = encode(globs)
    audit = {'schema_version': 'general70-reference-only-release/v1', 'dataset': dataset,
             'baseline_dataset': {'id': before['dataset_id'], 'digest': before['dataset_digest']},
             'task_count': 70, 'unchanged_task_count': 69, 'changed_task_ids': changed,
             'all_public_prompts_and_execution_inputs_unchanged': True,
             'grading_weights_unchanged': True, 'historical_locks_verified': historical,
             'info004_pdf_sha256': 'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455',
             'task_record_sha256': {t['task_id']: sha(encode(t)) for t in after['tasks']}}
    result = {dataset_manifest_path(after['dataset_id']): encode(after),
              ROOT / 'tools/report/skills/general-e2e/score-general-e2e/data/general70-source-identities-v4.json': identities,
              ROOT / 'eval_general_e2e/datasets/audits/general-custom70-v4-reference-release.json': encode(audit)}
    for name in ['score-general-e2e', 'orchestrate-general-e2e']:
        result[ROOT / f'tools/report/skills/general-e2e/{name}/data/reviewed-generated-file-globs-v4.json'] = glob_bytes
    return result, {'identity_catalog_sha256': sha(identities), 'glob_catalog_sha256': sha(glob_bytes)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    files, hashes = outputs()
    for path, data in files.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif not path.is_file() or path.read_bytes() != data:
            raise SystemExit('REVISION_OUTPUT_DRIFT:' + str(path))
    print(json.dumps({'status': 'PASS', 'task_count': 70, 'unchanged_tasks': 69, **hashes}))
