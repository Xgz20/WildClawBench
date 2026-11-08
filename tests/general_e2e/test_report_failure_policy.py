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

POLICY = REPORT.report_run_audit.report_failure_policy
REPO = Path(__file__).resolve().parents[2]
NODE = os.environ.get('GENERAL_E2E_NODE') or shutil.which('node')


@unittest.skipUnless(NODE, 'Node required for native proof integration')
class ReportFailurePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        result = subprocess.run([NODE, str(REPO / 'tests/general_e2e/fixtures/write-native-start-rejection.mjs'), str(cls.root)],
                                capture_output=True, text=True, check=True)
        cls.paths = json.loads(result.stdout)
        cls.record_path = Path(cls.paths['record'])
        cls.record = json.loads(cls.record_path.read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.row = {'unit_id': 'astronstudio-macos', 'task_id': 'task', 'execution_attempt_id': 'original',
                    'total_score': None, 'score_status': 'unscored', 'lineage': {
                        'source_unit_root': str(self.root), 'source_unit_id': 'astronstudio-macos',
                        'source_execution_record': str(self.record_path),
                        'execution_record_sha256': hashlib.sha256(self.record_path.read_bytes()).hexdigest()}}
        self.human = {'schema_version': 'general70-human-conditional-failure-disposition/v1',
                      'context_task': 'task', 'human_statement': 'Synthetic test: non-framework failure gets zero.',
                      'question_item_id': 'synthetic-fixture', 'conditions': {
                          'proven_non_framework_failure': 'zero', 'unresolved_attribution': 'remain null'}}
        self.decision = {'schema_version': 'general70-authorized-failure-zero-decision/v1',
                         'identity': self.record['identity'], 'classification': 'proven-harness-native-start-failure',
                         'failure_policy_score': 0, 'rubric_score': None, 'score_valid': False, 'scope': ['task'],
                         'prompt_sha256': self.record['prompt']['sha256'],
                         'native_failure_proof': {'sha256': self.record['evidence']['native_start_rejection']['sha256']}}

    def normalize(self):
        refs = []
        for name, data in [('human', self.human), ('decision', self.decision)]:
            path = self.root / (name + '.json'); path.write_text(json.dumps(data))
            refs.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        self.item = {'task_id': 'task', 'execution_attempt_id': 'original', 'decision': refs[1], 'human_policy': refs[0]}
        def verify_refs(items):
            result = []
            for item in items:
                path, digest, size = REPORT.report_run_audit.checked_file(item['path'], item['sha256'])
                result.append({'path': str(path), 'sha256': digest, 'size': size})
            return result
        return POLICY.normalize([self.item], [self.row], verify_refs, node=NODE)

    def test_real_frozen_proof_replay_and_secondary_score_preserve_rubric(self):
        decisions = self.normalize()
        valid = {**self.row, 'task_id': 'other', 'score_status': 'valid', 'total_score': .8}
        unknown = {**self.row, 'task_id': 'unknown'}
        data = {'tasks': [self.row, valid, unknown]}
        POLICY.prepare(data, {'units': [{'failure_zero_decisions': decisions}]})
        self.assertEqual([row['e2e_score'] for row in data['tasks']], [0, .8, None])
        self.assertEqual([row['total_score'] for row in data['tasks']], [None, .8, None])
        self.assertEqual(self.row['score_status'], 'unscored')
        views = {'总览': {'headers': ['模型@Harness', '总平均分'], 'rows': [['model', 80]], 'formats': {}, 'notes': []}}
        POLICY.attach_views(data, views, {'astronstudio-macos': 'model'})
        self.assertEqual(views['总览']['rows'][0][-3:], [40, 1, 2])
        self.assertEqual(len(views['端到端计分']['rows']), 3)
        self.assertIsNone(views['端到端计分']['rows'][-1][5])

    def test_policy_cannot_replace_valid_score_or_grading_error(self):
        for status in ['valid', 'evaluation_error']:
            self.row['score_status'] = status
            with self.assertRaisesRegex(ValueError, 'selected unscored'):
                self.normalize()

    def test_selected_execution_copy_replays_original_formal_native_state(self):
        folder=self.root/'scoring/execution-records';folder.mkdir(parents=True,exist_ok=True)
        selected=folder/'task.json';selected.write_bytes(self.record_path.read_bytes())
        self.row['lineage']['source_execution_record']=str(selected)
        self.assertEqual(self.normalize()[0]['failure_policy_score'],0)

    def test_wrong_attempt_or_human_scope_is_rejected(self):
        self.decision['identity'] = {**self.record['identity'], 'attempt_id': 'foreign'}
        with self.assertRaisesRegex(ValueError, 'selected collected'):
            self.normalize()
        self.decision['identity'] = self.record['identity']; self.human['context_task'] = 'foreign'
        with self.assertRaisesRegex(ValueError, 'human conditional'):
            self.normalize()

    def test_tampered_native_proof_cannot_become_zero(self):
        self.decision['native_failure_proof']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'proof binding'):
            self.normalize()

    def test_no_decisions_keeps_existing_data_unchanged(self):
        data = {'tasks': [copy.deepcopy(self.row)]}; before = copy.deepcopy(data)
        POLICY.prepare(data, {'units': []})
        self.assertEqual(data, before)

    def test_inherited_generic_rule_keeps_original_human_context(self):
        parent = {**self.human, 'context_task': 'original-context-task'}
        path = self.root / 'original-human-policy.json'; path.write_text(json.dumps(parent))
        self.human.update(derived_application=True, source_context_task=parent['context_task'],
                          source_policy={'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
                          application_basis='ongoing-round-generic-conditional-failure-rule', batch_id='batch')
        self.assertEqual(len(self.normalize()[0]['evidence']), 8)
        self.human['human_statement'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'application provenance'):
            self.normalize()

    def test_idle_prewarm_native_profile_is_replayed_without_cancelling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            result = subprocess.run([NODE, str(REPO / 'tests/general_e2e/fixtures/write-native-start-rejection.mjs'),
                                     str(root), '--idle-prewarm'], capture_output=True, text=True, check=True)
            paths = json.loads(result.stdout); record_path = Path(paths['record'])
            record = json.loads(record_path.read_bytes())
            self.row['lineage'].update(source_unit_root=str(root), source_execution_record=str(record_path),
                                       execution_record_sha256=hashlib.sha256(record_path.read_bytes()).hexdigest())
            self.decision['native_failure_proof']['sha256'] = record['evidence']['native_start_rejection']['sha256']
            self.assertEqual(self.normalize()[0]['failure_policy_score'], 0)
