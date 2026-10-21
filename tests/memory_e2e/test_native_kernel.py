import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.io import MemoryEvaluationError, sha
from eval_memory_e2e.native_kernel import load_kernel
from eval_memory_e2e.batch import default_profiles, verify_profile_kernel, prepare, load_batch


class CompiledKernelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        mocked = patch('eval_memory_e2e.native_kernel.TOOLS', self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.binary = self.root / 'approved-kernel/synthetic/acode'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'SYNTHETIC-KERNEL')
        self.source = self.root / 'source.patch'
        self.source.write_bytes(b'SYNTHETIC-SOURCE')
        source = {'sha256': sha(self.source.read_bytes())}
        self.build = self.root / 'build.json'
        self.built = {'status': 'PASS', 'command': ['cargo', 'build', '--locked', '-p', 'codex-cli', '--bin', 'acode'],
                      'source_before': source, 'source_after': dict(source)}
        self.build.write_text(json.dumps(self.built))
        self.manifest = self.root / 'kernel.json'
        self.value = {'contract': 'astudio-compiled-app-kernel/v1', 'diagnostic_only': True,
                      'installed_astudio_modified': False, 'path': str(self.binary), 'sha256': sha(self.binary.read_bytes()),
                      'source_patch': {'path': str(self.source), 'sha256': sha(self.source.read_bytes())},
                      'build': {'path': str(self.build), 'sha256': sha(self.build.read_bytes())}}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.value))

    def test_frozen_build_binary_and_source_must_remain_unchanged(self):
        self.assertEqual(load_kernel(self.manifest), self.value)
        for file in (self.binary, self.source, self.build):
            with self.subTest(file=file.name):
                original = file.read_bytes()
                file.write_bytes(b'SYNTHETIC-DRIFT')
                with self.assertRaises(MemoryEvaluationError):
                    load_kernel(self.manifest)
                file.write_bytes(original)

    def test_failed_build_or_source_change_during_build_cannot_be_admitted(self):
        for changed in ({**self.built, 'status': 'FAIL'},
                        {**self.built, 'source_after': {'sha256': '0' * 64}},
                        {**self.built, 'command': ['cargo', 'check']}):
            self.build.write_text(json.dumps(changed))
            self.value['build']['sha256'] = sha(self.build.read_bytes())
            self.save()
            with self.assertRaises(MemoryEvaluationError):
                load_kernel(self.manifest)

    def test_installed_replacement_and_non_diagnostic_manifest_are_rejected(self):
        for key, changed in (('diagnostic_only', False), ('installed_astudio_modified', True)):
            original = self.value[key]
            self.value[key] = changed
            self.save()
            with self.assertRaises(MemoryEvaluationError):
                load_kernel(self.manifest)
            self.value[key] = original

    def test_a_symlink_cannot_substitute_the_frozen_binary(self):
        replacement = self.root / 'outside-acode'
        replacement.write_bytes(self.binary.read_bytes())
        self.binary.unlink()
        self.binary.symlink_to(replacement)
        with self.assertRaises(MemoryEvaluationError):
            load_kernel(self.manifest)


class ProfileKernelTests(unittest.TestCase):
    def setUp(self):
        self.installed = {'path': '/synthetic/installed/acode', 'sha256': '0' * 64, 'version': 'installed', 'architecture': 'arm64'}
        self.compiled = {'path': '/synthetic/approved/acode', 'sha256': '1' * 64, 'version': 'diagnostic', 'architecture': 'arm64'}
        self.adapter = 'macos-seatbelt-astudio-compiled-kernel/v3'
        self.unit = {'contract': 'astudio-case-memory-unit/v1', 'unit_id': 'synthetic-unit', 'scope': '/synthetic/scope.json'}
        self.boundary = {'required': True, 'admitted_adapter': self.adapter, 'status': 'os_enforced', 'lease': '/synthetic/lease.json'}
        self.profile = {**default_profiles()['AstronStudio'], 'kernel': self.compiled,
                        'installed_kernel_reference': self.installed, 'astudio_scope': self.unit,
                        'non_target_memory_boundary': self.boundary,
                        'memory_protocol': {'compiled_kernel_diagnostic': True, 'formal_scoring_allowed': False}}
        self.lease = {'contract': self.adapter, 'kernel': self.installed,
                      'compiled_kernel': {'identity': self.compiled}, 'astudio_scope': self.unit}
        identity = patch('eval_memory_e2e.batch.kernel_identity', return_value=self.installed)
        identity.start(); self.addCleanup(identity.stop)
        loader = patch('eval_memory_e2e.os_boundary.load_lease', return_value=self.lease)
        self.loader = loader.start(); self.addCleanup(loader.stop)

    def test_legacy_installed_identity_is_preserved_and_cannot_admit_a_substitute(self):
        verify_profile_kernel('AstronStudio', {'kernel': self.installed})
        self.loader.assert_not_called()
        for harness, profile in [('AstronStudio', {'kernel': self.compiled}), ('WorkBuddy', {'kernel': self.installed})]:
            with self.assertRaises(MemoryEvaluationError):
                verify_profile_kernel(harness, profile)

    def test_legacy_diagnostic_profiles_are_rejected_even_when_fully_bound_and_unscored(self):
        for profile in [self.profile, {'installed_kernel_reference': self.installed},
                        {'memory_protocol': {'automatic_generation_diagnostic_allowed': True}},
                        {'non_target_memory_boundary': {'admitted_adapter': 'macos-seatbelt-astudio-native-executor/v2'}}]:
            with self.subTest(profile=profile), self.assertRaises(MemoryEvaluationError) as error:
                verify_profile_kernel('AstronStudio', profile)
            self.assertEqual(error.exception.code, 'ASTUDIO_PRODUCTION_PACKAGE_REQUIRED')
        self.loader.assert_not_called()

    def test_invalid_profile_cannot_create_a_batch_or_bind_a_unit(self):
        with tempfile.TemporaryDirectory() as raw, patch('eval_memory_e2e.astudio_scope.bind_batch') as bind:
            batch = Path(raw).resolve() / 'batch'
            with self.assertRaises(MemoryEvaluationError) as error:
                prepare(batch, batch_id='rejected', seed='synthetic', harnesses=['AstronStudio'],
                        profiles={'AstronStudio': self.profile})
            self.assertEqual(error.exception.code, 'ASTUDIO_PRODUCTION_PACKAGE_REQUIRED')
            self.assertFalse(batch.exists())
            bind.assert_not_called()

    def test_loading_an_old_batch_cannot_reenable_the_diagnostic_kernel(self):
        from eval_memory_e2e.io import digest
        dataset = Path(__file__).resolve().parents[2] / 'tasks/memory-e2e/canaries/scoped-forgetting-v3.1.json'
        with tempfile.TemporaryDirectory() as raw:
            batch = Path(raw).resolve() / 'batch'
            profile = {**default_profiles()['AstronStudio'], 'kernel': self.installed}
            prepare(batch, batch_id='production-binding', seed='synthetic', harnesses=['AstronStudio'],
                    profiles={'AstronStudio': profile}, dataset_path=dataset)
            self.assertEqual(load_batch(batch)['profiles']['AstronStudio']['kernel'], self.installed)
            manifest = json.loads((batch / 'manifest.json').read_text())
            manifest['profiles']['AstronStudio'] = self.profile
            (batch / 'manifest.json').write_text(json.dumps(manifest))
            (batch / 'manifest.sha256').write_text(digest(manifest) + '\n')
            with self.assertRaises(MemoryEvaluationError) as error:
                load_batch(batch)
            self.assertEqual(error.exception.code, 'ASTUDIO_PRODUCTION_PACKAGE_REQUIRED')
