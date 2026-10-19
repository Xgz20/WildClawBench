import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.machine import machine_paths, paths_for_home, astudio_kernel, machine_identity
from eval_memory_e2e.batch import prepare, load_batch, default_profiles
from eval_memory_e2e.io import MemoryEvaluationError
from eval_memory_e2e.io import events
from eval_memory_e2e.runner import advance


class MachineTests(unittest.TestCase):
    def test_launcher_home_cannot_redirect_target_or_lock_to_codex(self):
        before = machine_paths()
        with patch.dict(os.environ, {'HOME': '/tmp/foreign/.codex', 'CODEX_HOME': '/tmp/foreign/.codex'}):
            self.assertEqual(machine_paths(), before)
        self.assertEqual(before['ui_lock'], before['debug'] / '.memory-native-ui.lock')
        self.assertEqual(before['astudio_db'], before['home'] / '.acode/acode/userdata/state.sqlite')

    def test_arm_kernel_is_selected_and_x64_only_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp).resolve() / 'AStudio.app'
            root = app / 'Contents/Resources/bin'
            root.mkdir(parents=True)
            x64 = root / 'acode-darwin-x64'
            x64.write_bytes(b'x64'); x64.chmod(0o700)
            with self.assertRaises(MemoryEvaluationError):
                astudio_kernel(app, architecture='arm64', inspect=lambda p: ['x86_64'])
            arm = root / 'acode-darwin-arm64'
            arm.write_bytes(b'arm64'); arm.chmod(0o700)
            self.assertEqual(astudio_kernel(app, architecture='arm64', inspect=lambda p: ['arm64']), arm)
            with self.assertRaises(MemoryEvaluationError):
                astudio_kernel(app, architecture='arm64', inspect=lambda p: ['x86_64'])

    def test_universal_kernel_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp).resolve() / 'AStudio.app'
            root = app / 'Contents/Resources/bin'
            root.mkdir(parents=True)
            universal = root / 'acode-darwin-universal'
            universal.write_bytes(b'universal'); universal.chmod(0o700)
            self.assertEqual(astudio_kernel(app, architecture='arm64', inspect=lambda p: ['x86_64','arm64']), universal)
            (root / 'acode-darwin-arm64').symlink_to(universal)
            with self.assertRaises(MemoryEvaluationError):
                astudio_kernel(app, architecture='arm64', inspect=lambda p: ['arm64'])

    def test_foreign_profile_fails_before_batch_or_intent_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'batch'
            profiles = default_profiles()
            identity = machine_identity(); identity['paths'] = {k:str(v) for k,v in paths_for_home('/Users/old-machine').items()}
            profiles['AstronStudio']['machine'] = identity
            with self.assertRaisesRegex(MemoryEvaluationError, 'Create a new local native Profile'):
                prepare(root, batch_id='foreign', seed='new', harnesses=['AstronStudio'], profiles=profiles)
            self.assertFalse(root.exists())

    def test_local_batch_cannot_resume_under_a_different_machine_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'batch'
            profiles = default_profiles()
            identity = machine_identity()
            profiles['AstronStudio']['machine'] = identity
            prepare(root, batch_id='local', seed='new', harnesses=['AstronStudio'],
                    scenario_ids=['MEM-10'], profiles=profiles)
            with patch('eval_memory_e2e.batch.machine_identity', return_value={**identity, 'host': 'another-machine'}):
                with self.assertRaises(MemoryEvaluationError) as error:
                    load_batch(root)
                self.assertEqual(error.exception.code, 'MACHINE_DRIFT')

    def test_unverified_boundary_stops_before_driver_or_new_prompt_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'batch'
            profiles = default_profiles()
            profiles['AstronStudio']['non_target_memory_boundary'] = {'required': True, 'status': 'not_enforced'}
            prepare(root, batch_id='boundary-closed', seed='new', harnesses=['AstronStudio'],
                    scenario_ids=['MEM-10'], profiles=profiles)
            with patch('eval_memory_e2e.runner.next_action', return_value={'status':'READY','request':{'action':'execute_step'}}), \
                    patch('eval_memory_e2e.runner.subprocess.run') as driver:
                with self.assertRaises(MemoryEvaluationError) as error:
                    advance(root, 'AstronStudio__MEM-10__r01__cold')
                self.assertEqual(error.exception.code, 'NATIVE_MEMORY_FILESYSTEM_BOUNDARY_UNVERIFIED')
                driver.assert_not_called()
            self.assertFalse(any(e['kind']=='INTENT' for e in events(root)))
