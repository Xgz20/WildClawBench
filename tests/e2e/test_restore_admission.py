from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.e2e.cli import _restore
from src.e2e.common import E2EError, atomic_json
from src.e2e.store import BatchStore, controller_lock


class RestoreAdmissionTests(unittest.TestCase):
    def test_completed_case_restores_during_other_execution_but_started_judge_blocks_it(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            batch = workspace / 'batches/frozen'
            batch.mkdir(parents=True)
            manifest = {'schema': 'wildclawbench.sandbox-batch/v1', 'plan': {'batch_id': 'frozen'}}
            atomic_json(batch / 'batch.json', manifest)
            item = {'key': 'u/run-0001/task', 'unit_id': 'u', 'task_id': 'task', 'run_index': 1,
                    'attempt_id': 'execution', 'execution_root': 'units/u/runs/run-0001/tasks/task/executions/execution'}
            store = BatchStore(batch)
            store.initialize(manifest, [item])
            store.update(item['key'], 'COMPLETED')
            args = SimpleNamespace(workspace_root=workspace, batch_id='frozen', execution_key=item['key'], destination=None)
            with patch('src.e2e.artifacts.restore_execution', side_effect=lambda source, target: {'destination': str(target)}):
                with controller_lock(batch):
                    result = _restore(args)
                self.assertIn('/restores/generation-', result['destination'])
                store.publish_ready(item['key'], {'identity': {}, 'backup_sha256': 'a' * 64})
                claim = store.claim_score('fixture', 1, mode='streaming')
                # Preparing a claim has not started a judge; its frozen context is never changed.
                self.assertTrue(_restore(args)['destination'])
                store.score_update(item['key'], claim['claim_id'], 'RUNNING', orchestration={'root': 'owned-judge'})
                with self.assertRaisesRegex(E2EError, 'SCORING_ACTIVE_RESTORE_REQUIRES_QUIESCENT_ATTEMPT'):
                    _restore(args)
