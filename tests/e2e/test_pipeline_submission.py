from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.e2e.common import atomic_json, read_json
from src.e2e.pipeline import record_submission
from src.e2e.selection import compose_results
from src.e2e.store import BatchStore


class WebSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.batch = Path(self.temp.name).resolve() / 'batch'
        self.batch.mkdir()
        self.identity = {'batch_id': 'batch-r0001', 'unit_id': 'web', 'task_id': 't1', 'attempt_id': 'exec-1'}
        self.manifest = {'schema': 'wildclawbench.sandbox-batch/v1',
                         'plan': {'batch_id': 'batch', 'runs': 1},
                         'units': [{'unit_id': 'web', 'scene': 'web', 'task_ids': ['t1']}],
                         'tasks': [{'task_id': 't1'}]}
        atomic_json(self.batch / 'batch.json', self.manifest)
        self.item = {'key': 'web/run-0001/t1', 'unit_id': 'web', 'run_index': 1, 'task_id': 't1', 'attempt_id': 'exec-1'}
        self.store = BatchStore(self.batch)
        self.store.initialize(self.manifest, [self.item])
        self.store.update(self.item['key'], 'COMPLETED')
        self.ready = {'backup_sha256': 'a' * 64, 'identity': self.identity, 'actual_model': 'spark-x2.6'}
        self.store.publish_ready(self.item['key'], self.ready)
        self.claim = self.store.claim_score('owner', 1, mode='streaming')
        self.root = self.batch / 'scoring'
        self.root.mkdir()
        self.store.score_update(self.item['key'], self.claim['claim_id'], 'RUNNING',
                                context={'installed_skills': str(self.batch / 'skills')},
                                orchestration={'scene': 'web', 'root': str(self.root), 'script': 'frozen-control.mjs'})

    def tearDown(self):
        self.temp.cleanup()

    def admit(self, evaluation):
        document = {'batch_id': 'batch-r0001', 'task_ids': ['t1'],
                    'unit': {'harness_id': 'astronstudio', 'model_id': 'spark-x2.6'},
                    'tasks': [{'evaluation': evaluation}]}
        atomic_json(self.root / 'submission.json', document)
        with patch('src.e2e.pipeline.verify_ready', return_value=self.ready), patch('src.e2e.pipeline._run', return_value={}):
            receipt = record_submission(self.batch, self.item['key'], self.claim['claim_id'])
        return document, receipt

    def test_web_evaluation_error_retains_audit_and_full_unscored_scope(self):
        document, receipt = self.admit({'status': 'evaluation_error', 'error': 'public Browser has no test clock',
                                        'aesthetic': {'status': 'completed'}})
        claim = self.store.scoring_rows()[0]
        self.assertEqual(claim['phase'], 'FAILED')
        self.assertEqual(claim['error']['code'], 'SCORING_INFRASTRUCTURE_ERROR')
        self.assertEqual(receipt['score_status'], 'unscored')
        self.assertEqual(read_json(self.root / 'submission.json'), document)
        with patch('src.e2e.selection.verify_ready', return_value=self.ready):
            selected = compose_results(self.batch)
        self.assertEqual(selected['status_counts'], {'unscored': 1})
        self.assertEqual(selected['tasks'][0]['error']['code'], 'SCORING_INFRASTRUCTURE_ERROR')
        self.assertEqual(selected['tasks'][0]['submission_sha256'], receipt['sha256'])
        self.assertFalse((self.batch / 'units/web/runs/run-0001/submission/submission.json').exists())

    def test_aesthetic_infrastructure_error_is_not_valid_completion(self):
        self.admit({'status': 'completed', 'aesthetic': {'status': 'evaluation_error'}})
        self.assertEqual(self.store.scoring_rows()[0]['phase'], 'FAILED')

    def test_completed_web_score_still_admits_normally(self):
        self.admit({'status': 'completed', 'aesthetic': {'status': 'completed'}})
        self.assertEqual(self.store.scoring_rows()[0]['phase'], 'SCORED')


if __name__ == '__main__':
    unittest.main()
