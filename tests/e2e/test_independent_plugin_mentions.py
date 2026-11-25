from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import shutil
import subprocess
import sys
from unittest.mock import Mock, patch

from src.e2e import prompt_plugins_guest as guest
from src.e2e.common import atomic_json
from src.e2e.preprocessing import augment_prompt, normalize_binding, selection, PLUGIN_VALIDATION
from src.e2e.preparation import normalize_plan


class InstalledPluginTests(unittest.TestCase):
    def test_uploaded_worker_imports_its_helper_in_isolated_python_mode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(guest.__file__).parent
            shutil.copyfile(source / 'prompt_plugins_guest.py', root / 'check_plugins.py')
            shutil.copyfile(source / 'preprocess_windows_guest.py', root / 'preprocess_windows_guest.py')
            result = subprocess.run([sys.executable, '-I', '-c',
                "import runpy,sys;runpy.run_path(sys.argv[1],run_name='import-check')", str(root / 'check_plugins.py')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.slot = self.plugin('market', '1.0.16')
        self.rpc = Mock()
        self.rpc.call.return_value = {'marketplaces': [], 'data': []}
        @contextmanager
        def runtime(*_args):
            yield self.rpc
        self.enterContext(patch.object(guest, 'runtime', side_effect=runtime))
        self.enterContext(patch.object(guest, 'user_path', side_effect=lambda p: p.resolve(strict=True)))

    def plugin(self, market, version):
        directory = self.home / 'plugins/cache' / market / 'sites-skills'
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(directory / guest.REMOTE_PLUGIN_METADATA, {'schema_version': 1, 'remote_plugin_id': 'fixture-' + market})
        root = directory / version
        (root / '.codex-plugin').mkdir(parents=True, exist_ok=True)
        atomic_json(root / '.codex-plugin/plugin.json', {'name': 'sites-skills', 'version': version})
        (root / 'SKILL.md').write_text('fixture')
        return root

    def inspect(self):
        return guest.inspect_plugins(None, self.home, self.home, ['sites-skills'])

    def test_preinstalled_plugin_is_read_only_and_records_actual_version_and_source(self):
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        value = self.inspect()[0]
        self.assertEqual(value['version'], '1.0.16')
        self.assertEqual(value['source_path'], str(self.slot.resolve()))
        self.assertEqual(value['availability_evidence'], 'remote-cache-and-config')
        self.assertFalse(value['runtime_observed'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertNotIn('plugin/install', [call.args[0] for call in self.rpc.call.call_args_list])

    def test_missing_disabled_and_unregistered_cache_are_not_silently_accepted(self):
        (self.home / 'config.toml').write_text('[plugins."sites-skills@market"]\nenabled=false\n')
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_DISABLED'):
            self.inspect()
        (self.home / 'config.toml').unlink()
        (self.slot.parent / guest.REMOTE_PLUGIN_METADATA).unlink()
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_NOT_INSTALLED'):
            self.inspect()

    def test_same_name_multiple_markets_requires_resolution_and_explicit_disable_can_resolve(self):
        self.plugin('other-market', '1.0.17')
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_SOURCE_AMBIGUOUS'):
            self.inspect()
        (self.home / 'config.toml').write_text('[plugins."sites-skills@other-market"]\nenabled=false\n')
        self.assertEqual(self.inspect()[0]['marketplace'], 'market')

    def test_runtime_disabled_state_wins_over_filesystem_cache(self):
        self.rpc.call.side_effect = lambda method, _: {'marketplaces': [{'name': 'market', 'plugins': [
            {'id': 'sites-skills@market', 'installed': True, 'enabled': False}]}]} if method == 'plugin/installed' else {'data': []}
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_DISABLED'):
            self.inspect()

    def test_replacement_payload_version_is_not_confused_with_market_cache_slot(self):
        atomic_json(self.slot / '.codex-plugin/plugin.json', {'name': 'sites-skills', 'version': '1.0.17'})
        value = self.inspect()[0]
        self.assertEqual((value['version'], value['cache_version']), ('1.0.17', '1.0.16'))

    def test_generated_python_bytecode_is_not_a_source_version_change(self):
        original = self.inspect()[0]['tree_sha256']
        cache = self.slot / '__pycache__'
        cache.mkdir()
        (cache / 'generated.cpython-312.pyc').write_bytes(b'generated')
        self.assertEqual(self.inspect()[0]['tree_sha256'], original)
        (self.slot / 'SKILL.md').write_text('changed source')
        self.assertNotEqual(self.inspect()[0]['tree_sha256'], original)

    def test_runtime_remote_identity_must_match_the_cached_installation(self):
        self.rpc.call.side_effect = lambda method, _: {'marketplaces': [{'name': 'market', 'plugins': [
            {'id': 'sites-skills@market', 'installed': True, 'enabled': True, 'remotePluginId': 'other-identity'}]}]} if method == 'plugin/installed' else {'data': []}
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_IDENTITY_MISMATCH'):
            self.inspect()

    def test_multiple_cached_versions_use_actual_enabled_skill_root(self):
        newer = self.plugin('market', '1.0.17')
        with self.assertRaisesRegex(guest.StepError, 'PROMPT_PLUGIN_SOURCE_AMBIGUOUS'):
            self.inspect()
        self.rpc.call.side_effect = lambda method, _: {'marketplaces': []} if method == 'plugin/installed' else {
            'data': [{'skills': [{'path': str(newer / 'SKILL.md'), 'enabled': True}]}]}
        self.assertEqual(self.inspect()[0]['version'], '1.0.17')

    def test_all_four_recipe_and_mention_combinations_keep_source_prompt_unchanged(self):
        recipe = {'version_id': 1, 'version': 1, 'name': 'fixture', 'steps': []}
        # Prompt formatting is independent from availability checking.
        for environment in (None, recipe):
            for names in ([], ['sites-skills']):
                source = 'task\r\noriginal\r\n'
                result, metadata = augment_prompt(source, {'plugin_mentions': names}, environment)
                self.assertEqual(result.startswith(source), True)
                self.assertEqual(metadata['changed'], bool(names))
                self.assertEqual('@sites-skills' in result, bool(names))
                if not names:
                    self.assertEqual(result.encode(), source.encode())
        binding = normalize_binding({'default': None, 'overrides': {}, 'prompt_directives': {
            'default': ['sites-skills'], 'overrides': {'b': []}}}, 'astronstudio')
        self.assertEqual(binding['prompt_plugin_validation'], PLUGIN_VALIDATION)
        result = selection([{'unit_id': 'u', 'preprocessing': binding}], [{'task_id': 'a', 'scene': 'web'}, {'task_id': 'b', 'scene': 'web'}])
        self.assertIsNone(result['preprocessing'][0]['cases'][0]['recipe'])
        self.assertEqual(result['preprocessing'][0]['cases'][1]['prompt_directives']['plugin_mentions'], [])

    def test_public_plan_accepts_independent_unit_field_and_rejects_conflicting_legacy_input(self):
        source = {'selection': {'scenario': 'web', 'dataset': 'fixture'}, 'units': [{
            'harness': 'astronstudio', 'model': 'spark-x2.6',
            'prompt_directives': {'default': ['sites-skills'], 'overrides': {}}}]}
        unit = normalize_plan(source)['units'][0]
        self.assertIsNone(unit['preprocessing']['default'])
        self.assertEqual(unit['preprocessing']['prompt_plugin_validation'], PLUGIN_VALIDATION)
        source['units'][0]['preprocessing'] = {'default': None, 'overrides': {}, 'prompt_directives': {
            'default': ['other-plugin'], 'overrides': {}}}
        from src.e2e.common import E2EError
        with self.assertRaisesRegex(E2EError, 'PROMPT_DIRECTIVES_CONFLICT'):
            normalize_plan(source)

    def test_independent_references_also_work_for_general_cases_without_web_wording(self):
        binding = normalize_binding({'default': None, 'overrides': {}, 'prompt_directives': {
            'default': ['sites-skills'], 'overrides': {}}}, 'astronstudio')
        self.assertTrue(selection([{'unit_id': 'u', 'preprocessing': binding}], [{'task_id': 'g', 'scene': 'general'}]))
        prompt, _ = augment_prompt('original', {'plugin_mentions': ['sites-skills']}, None, scene='general')
        self.assertIn('可用插件：@sites-skills', prompt)
        self.assertNotIn('Web 插件', prompt)
