"""Regress short collapsed-card titles while keeping frozen Prompt provenance."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from src.e2e.backend import AStudioSandboxDriver
from src.e2e.common import E2EError, atomic_json
from src.e2e.preprocessing import augment_prompt
from src.e2e.prompt_transport import ASTUDIO_CARD_PROFILE


def sha(value):
    return hashlib.sha256(value).hexdigest()


class PromptTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = '[执行环境]\n操作系统：Windows；默认终端：PowerShell。\n\n请审核费用并保存结果。\n'.encode()
        source = self.root / 'case/execution'; source.mkdir(parents=True)
        (source / 'PROMPT.md').write_bytes(self.base)
        self.state = {}
        self.driver = object.__new__(AStudioSandboxDriver)
        self.driver.batch = self.root
        self.driver.staging = self.root / 'staging'
        self.driver.key = 'u/run-0001/case'
        self.driver.store = SimpleNamespace(get=lambda _: self.state)
        self.driver.task = {'input_root': 'case', 'scene': 'general', 'prompt_sha256': sha(self.base),
                            'workspace_path_profile': 'wildclawbench.workspace-paths/v1'}

    def test_actual_title_is_content_bound_and_only_framework_heading_changes(self):
        payload, metadata = self.driver._prompt_input(freeze=True)
        self.assertEqual(payload.split(b'\n', 1)[1], self.base.split(b'\n', 1)[1])
        self.assertIn(sha(self.base)[:32], payload.decode().splitlines()[0])
        self.assertEqual(metadata['base_prompt_sha256'], sha(self.base))
        self.assertEqual(metadata['effective_prompt_sha256'], sha(payload))
        self.assertEqual(metadata['prompt_transport']['profile'], ASTUDIO_CARD_PROFILE)
        self.assertEqual((self.root / 'case/execution/PROMPT.md').read_bytes(), self.base)
        self.assertEqual(self.driver._prompt_input(), (payload, metadata))
        self.state['dispatch_armed_at'] = 'earlier'
        self.assertEqual(self.driver._prompt_input(), (payload, metadata))

    def test_plugin_references_survive_and_are_bound_into_transport_identity(self):
        self.driver.prompt_directives = {'plugin_mentions': ['sites-skills']}
        payload, metadata = self.driver._prompt_input(freeze=True)
        self.assertEqual(payload.decode().count('@sites-skills'), 1)
        self.assertEqual(metadata['plugin_mentions'], ['sites-skills'])
        augmented, _ = augment_prompt(self.base.decode(), self.driver.prompt_directives, None, scene='general')
        self.assertEqual(metadata['prompt_transport']['source_prompt_sha256'], sha(augmented.encode()))
        self.driver.prompt_directives = {'plugin_mentions': ['other-plugin']}
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_DRIFT'):
            self.driver._prompt_input()

    def test_legacy_armed_attempt_keeps_original_bytes(self):
        self.state['dispatch_armed_at'] = 'earlier'
        payload, metadata = self.driver._prompt_input()
        self.assertEqual(payload, self.base)
        self.assertFalse(metadata['changed'])
        self.assertFalse((self.driver.staging / 'metadata/prompt.json').exists())

    def test_new_armed_attempt_cannot_fall_back_when_both_lock_files_disappear(self):
        _, metadata = self.driver._prompt_input(freeze=True)
        self.state.update(dispatch_armed_at='earlier', prompt=metadata)
        for name in ('effective-prompt.md', 'prompt.json'):
            (self.driver.staging / 'metadata' / name).unlink()
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_LOCK_MISSING'):
            self.driver._prompt_input()

    def test_legacy_plugin_lock_is_not_rewritten_even_before_dispatch(self):
        directives = {'plugin_mentions': ['sites-skills']}
        self.driver.prompt_directives = directives
        prompt, metadata = augment_prompt(self.base.decode(), directives, None, scene='general')
        target = self.driver.staging / 'metadata'; target.mkdir(parents=True)
        (target / 'effective-prompt.md').write_text(prompt)
        atomic_json(target / 'prompt.json', metadata)
        self.assertEqual(self.driver._prompt_input(freeze=True), (prompt.encode(), metadata))
        self.driver.prompt_directives = {'plugin_mentions': []}
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_DRIFT'):
            self.driver._prompt_input()

    def test_lock_and_original_prompt_drift_still_fail(self):
        self.driver._prompt_input(freeze=True)
        target = self.driver.staging / 'metadata/effective-prompt.md'
        target.write_bytes(target.read_bytes() + b'changed')
        with self.assertRaisesRegex(E2EError, 'EXECUTION_PROMPT_DRIFT'):
            self.driver._prompt_input()
        (self.root / 'case/execution/PROMPT.md').write_bytes(self.base + b'changed')
        with self.assertRaisesRegex(E2EError, 'FROZEN_TASK_PROMPT_DRIFT'):
            self.driver._prompt_input()

    def test_other_products_and_prompts_are_unchanged(self):
        self.driver.product = 'workbuddy'
        self.assertEqual(self.driver._prompt_input()[0], self.base)
        self.driver.product = 'astudio'
        self.driver.task.pop('workspace_path_profile')
        self.assertEqual(self.driver._prompt_input()[0], self.base)

    def test_public_context_offsets_and_sent_hash_bind_actual_handoff_text(self):
        from src.e2e.handoff import _sent_prompt_metadata
        from src.e2e.prompt_transport import astudio_environment_card
        public = '只读取公开材料；不得修改输入。'
        text = '[执行环境]\nWindows\n\n工作区公开指令：\n' + public + '\n\n任务：审核费用'
        base = text.encode()
        prompt, metadata = augment_prompt(text, {'plugin_mentions': []}, None, scene='general')
        actual, metadata = astudio_environment_card(prompt, metadata)
        original = {'sent_sha256': sha(base), 'public_context_delivery': [
            {'char_offset': text.index(public), 'char_count': len(public)}]}
        bound = _sent_prompt_metadata(original, base, actual.encode(), metadata)
        row = bound['public_context_delivery'][0]
        self.assertEqual(actual[row['char_offset']:row['char_offset']+row['char_count']], public)
        self.assertEqual(bound['sent_sha256'], sha(actual.encode()))
        self.assertEqual(original['sent_sha256'], sha(base))
