"""Reference-only release preserves historical inputs and scoring weights."""
import json
from pathlib import Path
import unittest

from eval_general_e2e.datasets.bundle import (compile_dataset, load_manifest_lock,
    dataset_manifest_path, GENERAL116_DEFINITION, GENERAL70_V2_DEFINITION,
    GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION, GENERAL70_V5_DEFINITION,
    GENERAL70_V6_DEFINITION)
from tests.general_e2e.test_local_scoring_runtime import RUNTIME
import source_identities

ROOT = Path(__file__).resolve().parents[2]
TASK = '01_Information_Search_Organization_task_001_acl2024_long_context_qa'


class General70V6ReferenceTests(unittest.TestCase):
    def test_old_manifests_remain_identical_after_reference_update(self):
        for definition in (GENERAL116_DEFINITION, GENERAL70_V2_DEFINITION,
                GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION, GENERAL70_V5_DEFINITION):
            with self.subTest(dataset=definition.dataset_id):
                current, _ = compile_dataset(ROOT, definition=definition)
                self.assertEqual(current, load_manifest_lock(dataset_manifest_path(definition.dataset_id)))

    def test_only_info001_grading_reference_changes_public_inputs_and_weights_do_not(self):
        before, old_members = compile_dataset(ROOT, definition=GENERAL70_V5_DEFINITION)
        after, new_members = compile_dataset(ROOT, definition=GENERAL70_V6_DEFINITION)
        self.assertEqual(after, load_manifest_lock(dataset_manifest_path('general-custom70-v6')))
        old_tasks = {r['task_id']: r for r in before['tasks']}
        old_contracts = {json.loads(m.data)['task_id']: json.loads(m.data)
                         for m in old_members if m.path.endswith('/private-scoring/contract.json')}
        new_contracts = {json.loads(m.data)['task_id']: json.loads(m.data)
                         for m in new_members if m.path.endswith('/private-scoring/contract.json')}
        changed = []
        for row in after['tasks']:
            tid = row['task_id']; previous = old_tasks[tid]
            for key in ('prompt_sha256', 'execution_contract_sha256', 'workspace_exec_sha256'):
                self.assertEqual(row['digests'][key], previous['digests'][key], (tid, key))
            self.assertEqual(old_contracts[tid]['grading_weights'], new_contracts[tid]['grading_weights'])
            if old_contracts[tid] != new_contracts[tid]: changed.append(tid)
        self.assertEqual(changed, [TASK])
        catalog = source_identities._qa_reference_release_catalog()
        self.assertEqual(len(catalog['profiles']), 70)
        self.assertEqual(catalog['baseline_dataset']['id'], before['dataset_id'])


if __name__ == '__main__': unittest.main()
