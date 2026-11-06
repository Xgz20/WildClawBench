from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tests.general_e2e.test_report_general_e2e import REPORT

POLICY = REPORT.report_run_audit.report_native_interruption_policy
NODE = os.environ.get('GENERAL_E2E_NODE') or shutil.which('node')
REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(NODE, 'Node required for native interruption proof replay')
class NativeInterruptionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.fixtures = []
        for name, extra in [('native', []), ('missing', ['--missing-provider'])]:
            result = subprocess.run([NODE, str(REPO / 'tests/general_e2e/fixtures/write-native-interruption.mjs'),
                                     str(cls.root / name), *extra], capture_output=True, text=True, check=True)
            cls.fixtures.append(json.loads(result.stdout))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.paths = self.fixtures[0]
        self.human = {'schema_version': 'general70-human-native-interruption-zero-policy/v1',
                      'human_statement': 'Synthetic authorization: native interruptions count as failure zero.',
                      'question_item_id': 'fixture', 'batch_id': 'fixture-batch', 'dataset_id': 'fixture-dataset',
                      'harness_scope': ['astronstudio'], 'current_task_ids': ['interrupted-task'],
                      'includes_future_same_round_native_interruptions': True}

    def normalize(self, execution_status='cancelled'):
        p = self.root / 'human-native-zero.json'; p.write_text(json.dumps(self.human))
        record_path = Path(self.paths['record']); record = json.loads(record_path.read_bytes())
        self.row = {'unit_id': 'astronstudio-macos', 'task_id': 'interrupted-task', 'execution_attempt_id': 'original',
                    'execution_status': execution_status, 'score_status': 'unscored', 'total_score': None,
                    'lineage': {'source_unit_root': self.paths['unit'], 'source_unit_id': 'astronstudio-macos',
                                'source_execution_record': str(record_path), 'execution_record_sha256': hashlib.sha256(record_path.read_bytes()).hexdigest()}}
        self.seen = []
        def refs(items, allow_empty=False):
            output = []
            for item in items:
                path, digest, size = REPORT.report_run_audit.checked_file(item['path'], item.get('sha256'))
                if not allow_empty:
                    self.assertGreater(size, 0)
                self.seen.append((size, allow_empty))
                output.append({'path': str(path), 'sha256': digest, 'size': size})
            return output
        return POLICY.normalize({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()},
                                [self.row], refs, node=NODE)

    def test_native_abort_zero_keeps_original_unknown_rubric_and_cause(self):
        result = self.normalize()
        self.assertEqual(result[0]['failure_policy_score'], 0)
        self.assertIn('no inference', result[0]['cause_assignment'])
        data = {'tasks': [self.row]}
        REPORT.report_run_audit.report_failure_policy.prepare(data, {'units': [{'failure_zero_decisions': result}]})
        self.assertEqual(data['tasks'][0]['e2e_score'], 0)
        self.assertIsNone(data['tasks'][0]['total_score'])
        self.assertEqual(data['tasks'][0]['score_status'], 'unscored')

    def test_verified_empty_native_projection_is_not_fabricated(self):
        self.paths = self.fixtures[1]
        self.assertEqual(self.normalize()[0]['failure_policy_score'], 0)
        self.assertIn((0, True), self.seen)

    def test_wrong_policy_batch_and_other_execution_status_do_not_zero(self):
        self.human['batch_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'source identity'):
            self.normalize()
        self.assertEqual(self.normalize(execution_status='completed'), [])

    def test_native_proof_drift_is_rejected(self):
        record = json.loads(Path(self.paths['record']).read_bytes())
        index_path = Path(self.paths['unit']) / record['evidence']['trace_index_path']
        index = json.loads(index_path.read_bytes())
        path = index_path.parent / 'bindings/runtime-interruption-proof.json'
        old = path.read_bytes()
        try:
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'replay failed'):
                self.normalize()
        finally:
            path.write_bytes(old)
