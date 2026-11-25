import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.artifacts import inventory
from src.e2e.backend import AStudioSandboxDriver, ObservationPaused
from src.e2e.common import E2EError, atomic_json, digest
from src.e2e.engine import _publish, _reconcile_sealed, verify_ready
from src.e2e.preprocessing import execution_prompt
from src.e2e.protocol import snapshot
from src.e2e.store import BatchStore
from src.e2e.trace import normalize_rollout
from tests.e2e.test_scheduler import native_fixture, GUEST


class PromptPluginExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.batch = Path(self.directory.name) / 'batch'
        self.public = self.batch / 'inputs/web/execution'
        (self.public / 'workspace').mkdir(parents=True)
        self.base = '创建一个站点。\r\n保留原任务。\r\n'.encode()
        (self.public / 'PROMPT.md').write_bytes(self.base)
        self.task = {'task_id': 'web', 'input_root': 'inputs/web', 'scene': 'web', 'requirements': {},
                     'prompt_sha256': hashlib.sha256(self.base).hexdigest(),
                     'definition_inventory': inventory(self.public.parent)}
        self.unit = {'unit_id': 'astudio-web', 'model': 'spark-x2.6', 'harness': 'astronstudio',
                     'reasoning_effort': 'high', 'timeout_override': 7200, 'template': 'fixture', 'task_ids': ['web']}
        self.task['public_inventory'] = []
        self.item = {'key': 'astudio-web/run-0001/web', 'task_id': 'web', 'unit_id': 'astudio-web', 'run_index': 1,
                     'attempt_id': 'exec-fixture', 'execution_root': 'units/astudio-web/runs/run-0001/tasks/web/executions/exec-fixture'}
        self.config = AgentCubeConfig(user_id='fixture', auth_token='synthetic')

    def initialize(self, enabled, *, replacement=True, runtime_validation=False):
        manifest = {'schema': 'wildclawbench.sandbox-batch/v1', 'plan': {'batch_id': 'batch'},
                    'units': [self.unit], 'tasks': [self.task]}
        if enabled:
            bindings = {'astudio-web': {'default': {'version_id': 1, 'version': 1, 'name': 'Sites',
                'steps': [{'kind': 'plugin', 'target': 'sites-skills', 'timeout': 20}]}, 'overrides': {},
                'prompt_directives': {'default': ['sites-skills'], 'overrides': {}}}}
            if not replacement:
                bindings['astudio-web']['default'] = None
            if runtime_validation:
                bindings['astudio-web']['prompt_plugin_validation'] = 'installed-plugin-v1'
            atomic_json(self.batch / 'preprocessing.json', bindings)
            manifest['preprocessing_bindings_sha256'] = digest(bindings)
        atomic_json(self.batch / 'batch.json', manifest)
        self.manifest = manifest
        self.store = BatchStore(self.batch)
        self.store.initialize(manifest, [self.item])
        self.store.update(self.item['key'], 'PREPARING', session_id='fixture-session')

    def driver(self):
        client = Mock()
        client.download.return_value = json.dumps({'schema_version': 2, 'status': 'completed'}).encode()
        driver = AStudioSandboxDriver(batch_root=self.batch, store=self.store, item=self.item,
            task=self.task, unit=self.unit, config=self.config, stop_event=Event(), client_factory=lambda _: client)
        driver._health = Mock(); driver._prepare_runtime = Mock(); driver._inventory_native = Mock(return_value={})
        driver._checked_job = Mock(); driver._cleanup_processes = Mock(return_value={'success': True})
        collect = driver.staging / 'collect';collect.mkdir(exist_ok=True)
        driver._download_tree = Mock(return_value=collect)

        def dispatch(*args, **kwargs):
            self.store.update(self.item['key'], 'RUNNING', dispatch_armed_at='2026-11-24T00:00:00+00:00')
            return {'exit_code': 0}
        driver._job = Mock(side_effect=dispatch)

        def bind(_sid, _before, report, identity, prompt, _stage):
            native = driver.staging / 'rollout-fixture.jsonl'
            native.write_text(native_fixture(prompt, 'fixture-thread', 'fixture-turn'))
            return native, normalize_rollout(native, identity=identity, prompt=prompt, guest_cwd=GUEST,
                requested_model='spark-x2.6', requested_effort='high', report=report)
        driver._bound_native = Mock(side_effect=bind)
        return driver

    def execute(self, driver):
        with patch('src.e2e.backend.windows_preprocess.apply_recipe'), \
                patch('src.e2e.backend.windows_preprocess.verify_remote_plugins'), \
                patch('src.e2e.backend.windows_preprocess.bind_running_acode'), \
                patch('src.e2e.backend.validate_collect'):
            return driver.execute()

    def test_real_driver_dispatches_normal_prompt_without_byte_or_payload_changes(self):
        self.initialize(False);driver = self.driver()
        result = self.execute(driver)
        uploaded = next(call.args[2] for call in driver.client.upload.call_args_list if call.args[1] == '/run/wgui/instruction.txt')
        self.assertEqual(uploaded, self.base)
        self.assertFalse((driver.staging / 'metadata/prompt.json').exists())
        self.assertNotIn('prompt', self.store.get(self.item['key']))
        self.assertNotIn('prompt', snapshot(self.batch)['executions'][0])
        self.assertEqual(result['binding']['prompt_sha256'], hashlib.sha256(self.base).hexdigest())

    def test_reference_without_replacement_is_verified_before_dispatch_and_after_completion(self):
        self.initialize(True, replacement=False, runtime_validation=True)
        driver = self.driver()
        plugin = {'name': 'sites-skills', 'enabled': True, 'version': '1.0.16', 'marketplace': 'fixture',
                  'source_path': 'C:/fixture', 'tree_sha256': 'a' * 64}
        driver.client.windows_execute.return_value = {'output': json.dumps({'status': 'passed', 'plugins': [plugin]})}
        result = self.execute(driver)
        self.assertIn('@sites-skills', driver._prompt_input()[0].decode())
        self.assertEqual(result['binding']['prompt_sha256'], self.store.get(self.item['key'])['prompt']['effective_prompt_sha256'])
        self.assertEqual(driver.client.windows_execute.call_count, 3)  # workspace mkdir + pre/post witnesses
        witness = self.store.get(self.item['key'])['prompt_plugin_witness']
        self.assertTrue(witness['verified_after_execution'])
        self.assertEqual(witness['plugins'][0]['version'], '1.0.16')
        self.assertIsNone(driver.preprocess_recipe)
        self.assertEqual(snapshot(self.batch)['executions'][0]['prompt_plugins'], witness)

    def test_missing_referenced_plugin_stops_before_dispatch_with_explicit_failure(self):
        self.initialize(True, replacement=False, runtime_validation=True)
        driver = self.driver()
        driver.client.windows_execute.return_value = {'output': '{"status":"failed","error":"PROMPT_PLUGIN_NOT_INSTALLED"}'}
        with self.assertRaisesRegex(E2EError, 'PROMPT_PLUGIN_NOT_INSTALLED'):
            self.execute(driver)
        driver._job.assert_not_called()
        self.assertEqual(self.store.get(self.item['key'])['prompt_plugin_witness']['status'], 'failed')

    def test_new_ready_receipt_binds_plugin_witness_and_rejects_missing_provenance(self):
        self.initialize(True, replacement=False, runtime_validation=True)
        driver = self.driver()
        driver.client.windows_execute.return_value = {'output': json.dumps({'status': 'passed', 'plugins': [
            {'name': 'sites-skills', 'enabled': True, 'tree_sha256': 'a' * 64}]})}
        result = self.execute(driver)
        item = self.store.get(self.item['key'])
        _publish(self.batch, self.store, item, self.manifest, self.unit, self.task, result)
        ready = verify_ready(self.batch, item, self.manifest)
        self.assertEqual(len(ready['prompt_plugins_sha256']), 64)
        path = driver.root / 'execution-ready.json'
        path.chmod(0o644)
        del ready['prompt_plugins_sha256']
        path.write_text(json.dumps(ready))
        with self.assertRaisesRegex(E2EError, 'PROMPT_PLUGIN_WITNESS_DRIFT'):
            verify_ready(self.batch, item, self.manifest)

    def test_plugin_drift_keeps_original_witness_and_never_redispatches(self):
        self.initialize(True, replacement=False, runtime_validation=True)
        driver = self.driver()
        plugin = {'name': 'sites-skills', 'enabled': True, 'tree_sha256': 'a' * 64}
        driver.client.windows_execute.side_effect = [
            {'output': ''},
            {'output': json.dumps({'status': 'passed', 'plugins': [plugin]})},
            {'output': json.dumps({'status': 'passed', 'plugins': [{**plugin, 'tree_sha256': 'b' * 64}]})}]
        with self.assertRaisesRegex(E2EError, 'PROMPT_PLUGIN_CHANGED_DURING_EXECUTION'):
            self.execute(driver)
        self.assertEqual(driver._job.call_count, 1)
        original = json.loads((driver.staging / 'metadata/prompt-plugins-before.json').read_text())
        self.assertEqual(original['plugins'][0]['tree_sha256'], 'a' * 64)

    def test_real_driver_records_and_resumes_the_exact_plugin_prompt_without_uploading_twice(self):
        self.initialize(True);driver = self.driver()
        result = self.execute(driver)
        effective = (driver.staging / 'metadata/effective-prompt.md').read_bytes()
        self.assertTrue(effective.startswith(self.base))
        self.assertIn(b'@sites-skills', effective)
        metadata = self.store.get(self.item['key'])['prompt']
        self.assertEqual(metadata['effective_prompt_sha256'], result['binding']['prompt_sha256'])
        self.assertEqual(snapshot(self.batch)['executions'][0]['prompt'], metadata)
        resumed = self.driver()
        self.execute(resumed)
        resumed.client.upload.assert_not_called()
        resumed._health.assert_not_called()
        self.assertEqual(self.store.get(self.item['key'])['prompt'], metadata)
        self.assertEqual(resumed._bound_native.call_args.args[4].encode(), effective)

    def test_resumed_dispatch_rejects_prompt_drift_and_missing_lock_before_observing_another_job(self):
        self.initialize(True);driver = self.driver();self.execute(driver)
        path = driver.staging / 'metadata/effective-prompt.md'
        path.write_bytes(b'changed')
        resumed = self.driver()
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_DRIFT'):
            self.execute(resumed)
        resumed._job.assert_not_called()
        path.unlink()
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_LOCK_MISSING'):
            self.execute(resumed)

    def test_pre_dispatch_partial_lock_is_completed_without_modifying_existing_bytes(self):
        self.initialize(True);driver = self.driver();driver.preflight()
        payload, metadata = driver._prompt_input(freeze=True)
        (driver.staging / 'metadata/prompt.json').unlink()
        self.assertEqual(driver._prompt_input(freeze=True), (payload, metadata))
        self.assertEqual(execution_prompt(driver.staging, self.base, metadata), payload)

    def test_sealed_publication_recovery_uses_the_effective_prompt_without_new_dispatch(self):
        self.initialize(True);driver = self.driver();outcome = self.execute(driver)
        item = self.store.get(self.item['key'])
        _publish(self.batch, self.store, item, self.manifest, self.unit, self.task, outcome)
        proof = json.loads((driver.root / 'original/trace/bindings/execution-proof.json').read_text())
        self.assertEqual(proof['prompt_sha256'], outcome['binding']['prompt_sha256'])
        self.assertEqual(proof['base_prompt_sha256'], self.task['prompt_sha256'])
        ready = driver.root / 'execution-ready.json'
        expected = json.loads(ready.read_text())
        ready.unlink()
        _reconcile_sealed(self.batch, self.store, item, self.manifest, self.unit, self.task)
        self.assertEqual(verify_ready(self.batch, item, self.manifest)['identity'], expected['identity'])
        self.assertEqual(driver._job.call_count, 1)
