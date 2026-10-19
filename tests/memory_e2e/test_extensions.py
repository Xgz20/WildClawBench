import copy
import tempfile
import unittest
from pathlib import Path

from eval_memory_e2e.batch import prepare, load_batch, default_profiles
from eval_memory_e2e.dataset import load_dataset, materialize
from eval_memory_e2e.io import publish, sha, MemoryEvaluationError, read_json
from eval_memory_e2e.native_profiles import driver_dependencies
from eval_memory_e2e.runner import advance, next_action


def recipe():
    return {'dataset_id': 'complex-memory-v2', 'version': 2, 'scenarios': [{
        'id': 'MEM-complex-001', 'dimension': 'updates', 'title': '多工作区更新', 'difficulty': 'hard',
        'experience_gain': True, 'fixtures': [], 'scopes': ['A', 'B', 'C'],
        'learning': {'mode': 'explicit', 'formation': {'kind': 'elapsed_observation', 'minimum_seconds': 0}},
        'variables': {'budget': {'kind': 'integer', 'min': 8000, 'max': 12000},
                      'record': {'kind': 'token', 'prefix': 'REC-', 'length': 16}},
        'steps': [{'id': 'learn', 'phase': 'seed', 'session': 'new', 'scope': 'A', 'prompt': '请记住 {project} 的预算 {budget}，记录号 {record}。'},
                  {'id': 'noise', 'phase': 'interference', 'session': 'new', 'scope': 'C', 'prompt': '计算17乘23。'},
                  {'id': 'ask', 'phase': 'probe', 'session': 'new', 'scope': 'A', 'prompt': '回忆 {project} 的预算。'}],
        'checkpoints': [{'id': 'budget', 'step_id': 'ask', 'metric': 'update_accuracy', 'expectation': '预算 {budget}', 'required': True}]}]}


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def dataset(self, data):
        path = self.base / 'dataset.json'; publish(path, data); return path

    def test_astudio_transport_budgets_are_frozen_in_new_profiles_only(self):
        from eval_memory_e2e.native_profiles import native_profiles
        path = self.base / 'profiles.json'; native_profiles(path); profiles = read_json(path)
        self.assertEqual(profiles['AstronStudio']['pre_click_rpc_wait_seconds'], 30)
        self.assertEqual(profiles['AstronStudio']['pre_click_focus_wait_seconds'], 60)
        self.assertEqual(profiles['AstronStudio']['driver_timeout_seconds'], 300)
        self.assertEqual(profiles['AstronStudio']['cdp_timeout_ms'], 30000)
        self.assertEqual(profiles['AstronStudio']['native_acceptance_wait_seconds'], 120)
        self.assertNotIn('native_acceptance_wait_seconds', default_profiles()['AstronStudio'])
        self.assertNotIn('cdp_timeout_ms', default_profiles()['AstronStudio'])
        self.assertNotIn('pre_click_rpc_wait_seconds', profiles['WorkBuddy'])
        root = self.base / 'batch'
        prepare(root, batch_id='new-budgets', seed='new-budgets', dataset_path=self.dataset(recipe()),
                profiles=profiles, harnesses=['AstronStudio'])
        profiles['AstronStudio']['native_acceptance_wait_seconds'] = 600
        profiles['AstronStudio']['pre_click_focus_wait_seconds'] = 120
        self.assertEqual(load_batch(root)['profiles']['AstronStudio']['native_acceptance_wait_seconds'], 120)
        self.assertEqual(load_batch(root)['profiles']['AstronStudio']['pre_click_focus_wait_seconds'], 60)

    def test_v2_variable_cardinality_three_scopes_and_recovery_roundtrip(self):
        path = self.dataset(recipe()); data = load_dataset(path)
        one = materialize(data['scenarios'][0], 'seed', 1)
        self.assertEqual(one, materialize(data['scenarios'][0], 'seed', 1))
        self.assertNotEqual(one['facts']['budget'], None)
        root = self.base / 'batch'
        prepare(root, batch_id='v2-fixture', seed='seed', mode='fixture', dataset_path=path, harnesses=['QwenWork'])
        manifest = load_batch(root)
        self.assertEqual(set(manifest['episodes'][0]['workspaces']), {'A', 'B', 'C'})
        for item in manifest['episodes']:
            while next_action(root, item['id'])['status'] != 'COMPLETED':
                advance(root, item['id'])
        self.assertEqual(len(manifest['episodes']), 2)

    def test_v2_unsupported_branch_and_undeclared_scope_fail(self):
        for mutation in ('branch', 'scope', 'reserved'):
            with self.subTest(mutation=mutation):
                data = recipe()
                if mutation == 'branch': data['scenarios'][0]['control_flow'] = 'dag'
                elif mutation == 'scope': data['scenarios'][0]['steps'][0]['scope'] = '../private'
                else: data['scenarios'][0]['steps'][0]['id'] = 'prepare'
                path = self.base / (mutation + '.json'); publish(path, data)
                with self.assertRaises(MemoryEvaluationError): load_dataset(path)

    def test_native_event_gate_without_an_adapter_rejects_before_creating_batch(self):
        data = recipe(); data['scenarios'][0]['learning']['formation'] = {'kind': 'native_event', 'event': 'phase2_completed'}
        path = self.dataset(data); root = self.base / 'batch'
        with self.assertRaises(MemoryEvaluationError) as error:
            prepare(root, batch_id='gate', seed='seed', dataset_path=path, harnesses=['AstronStudio'])
        self.assertEqual(error.exception.code, 'FORMATION_ADAPTER_NOT_ADMITTED')
        self.assertFalse(root.exists())

    def test_automatic_mode_does_not_inject_an_explicit_storage_instruction(self):
        from eval_memory_e2e import AUTOMATIC_EXECUTION_GUARD
        data = recipe(); data['scenarios'][0]['learning']['mode'] = 'automatic'
        data['scenarios'][0]['steps'][0]['prompt'] = '分析 {project} 的方案，预算 {budget}。'
        path = self.dataset(data); root = self.base / 'batch'
        prepare(root, batch_id='automatic', seed='automatic', dataset_path=path, harnesses=['QwenWork'])
        manifest = load_batch(root)
        for episode in manifest['episodes']:
            plan = read_json(root / episode['plan_path'])
            self.assertTrue(all(s['prompt'].startswith(AUTOMATIC_EXECUTION_GUARD + '\n\n') for s in plan['steps']))
            self.assertNotIn('允许使用当前客户端的原生记忆机制保存', plan['steps'][0]['prompt'])

    def test_driver_closure_includes_shared_helpers_and_locks_not_other_clients(self):
        root = self.base / 'repo'; root.mkdir()
        (root / 'common.mjs').write_text('export const shared = true;')
        (root / 'folder.swift').write_text('// native helper')
        (root / 'package.json').write_text('{}'); (root / 'package-lock.json').write_text('{}')
        (root / 'wb.mjs').write_text("import './common.mjs'; const helper = 'folder.swift';")
        (root / 'doubao.mjs').write_text("import './common.mjs';")
        hashes = driver_dependencies(root / 'wb.mjs', root)
        self.assertIn(str(root / 'common.mjs'), hashes)
        self.assertIn(str(root / 'folder.swift'), hashes)
        self.assertIn(str(root / 'package-lock.json'), hashes)
        self.assertNotIn(str(root / 'doubao.mjs'), hashes)

    def test_selected_harness_ignores_unrelated_driver_drift_but_shared_drift_blocks(self):
        shared = self.base / 'shared.mjs'; shared.write_text('shared')
        wb = self.base / 'wb.mjs'; wb.write_text('wb')
        db = self.base / 'doubao.mjs'; db.write_text('doubao')
        profiles = default_profiles()
        for name, own in [('WorkBuddy', wb), ('DoubaoWork', db)]:
            profiles[name].update(driver_command=['node', str(own)], driver_sources={str(p): sha(p.read_bytes()) for p in [own, shared]})
        root = self.base / 'batch'
        prepare(root, batch_id='sources', seed='sources', harnesses=['WorkBuddy', 'DoubaoWork'], scenario_ids=['MEM-01'], profiles=profiles)
        db.write_text('new doubao')
        self.assertEqual(next_action(root, 'WorkBuddy__MEM-01__r01__cold')['status'], 'READY')
        with self.assertRaises(MemoryEvaluationError): load_batch(root)
        shared.write_text('new shared')
        with self.assertRaises(MemoryEvaluationError): next_action(root, 'WorkBuddy__MEM-01__r01__cold')

    def test_execution_progress_never_becomes_an_implicit_capability_score(self):
        from eval_memory_e2e.report import aggregate
        root = self.base / 'batch'
        prepare(root, batch_id='execution-progress', seed='execution-progress', harnesses=['WorkBuddy'], scenario_ids=['MEM-01'], mode='fixture')
        episode = 'WorkBuddy__MEM-01__r01__cold'
        while next_action(root, episode)['status'] != 'COMPLETED':
            advance(root, episode)
        report = aggregate(root, include_fixture=True)
        self.assertEqual(report['units']['WorkBuddy']['execution']['completed_episodes'], 1)
        self.assertEqual(report['units']['WorkBuddy']['execution']['completed_prompt_steps'], 1)
        self.assertEqual(report['episodes'][0]['execution_status'], 'completed')
        self.assertEqual(report['episodes'][0]['status'], 'unscored')
        self.assertIsNone(report['episodes'][0]['score'])
