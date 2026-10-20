import json
import tempfile
import unittest
from copy import deepcopy
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

    def test_diagnostic_kernel_requires_every_scoped_unscored_v3_binding(self):
        verify_profile_kernel('AstronStudio', self.profile)
        self.loader.assert_called_once_with(self.boundary['lease'], self.boundary)
        for field, key, value in [('memory_protocol', 'formal_scoring_allowed', True),
                                  ('memory_protocol', 'compiled_kernel_diagnostic', False),
                                  ('non_target_memory_boundary', 'admitted_adapter', 'macos-seatbelt-astudio-native-executor/v2'),
                                  ('non_target_memory_boundary', 'status', 'not_enforced'),
                                  ('non_target_memory_boundary', 'required', False)]:
            profile = deepcopy(self.profile); profile[field][key] = value
            with self.assertRaises(MemoryEvaluationError):
                verify_profile_kernel('AstronStudio', profile)
        for key in ('kernel', 'installed_kernel_reference', 'astudio_scope'):
            profile = deepcopy(self.profile); profile.pop(key)
            with self.assertRaises(MemoryEvaluationError):
                verify_profile_kernel('AstronStudio', profile)

    def test_lease_cannot_substitute_another_kernel_or_unit(self):
        for replacement in [
            {**self.lease, 'kernel': self.compiled},
            {**self.lease, 'compiled_kernel': {'identity': self.installed}},
            {**self.lease, 'astudio_scope': {**self.unit, 'unit_id': 'another-unit'}},
        ]:
            self.loader.return_value = replacement
            with self.assertRaises(MemoryEvaluationError):
                verify_profile_kernel('AstronStudio', self.profile)

    def test_real_batch_prepare_and_load_keep_the_compiled_binding_and_detect_later_drift(self):
        from eval_memory_e2e.astudio_scope import create, freeze
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve(); ordinary = base / 'ordinary'
            desktop = ordinary / 'acode/userdata'; desktop.mkdir(parents=True)
            (desktop / 'astron-session.json').write_text(json.dumps({'uid': 'synthetic', 'loginMethod': 'sms'}))
            (ordinary / 'config.toml').write_text('[model_providers.astron-spark]\nname="Synthetic"\n')
            (desktop / 'state.sqlite').write_bytes(b'SYNTHETIC-SOURCE-DB')
            batch = base / 'debug/batch'
            paths = {'debug': base / 'debug', 'acode': ordinary,
                     'overlay': ordinary / 'overlay', 'astudio_db': desktop / 'state.sqlite'}
            with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value=paths), \
                 patch('eval_memory_e2e.astudio_scope.installation_witness', return_value={'synthetic': True}):
                unit = create(base / 'debug/unit', case_id='MEM-cleanup-001', repetition=1, batch_root=batch)
                profile = deepcopy(self.profile); profile['astudio_scope'] = freeze(unit['scope'])
                self.lease['astudio_scope'] = profile['astudio_scope']
                dataset = Path(__file__).resolve().parents[2] / 'tasks/memory-e2e/canaries/scoped-forgetting-v3.1.json'
                prepare(batch, batch_id='compiled-binding', seed='synthetic', harnesses=['AstronStudio'],
                        scenario_ids=['MEM-cleanup-001'], profiles={'AstronStudio': profile}, dataset_path=dataset)
                self.assertEqual(load_batch(batch)['profiles']['AstronStudio']['kernel'], self.compiled)
                self.lease['compiled_kernel'] = {'identity': {**self.compiled, 'sha256': '2' * 64}}
                with self.assertRaises(MemoryEvaluationError) as error:
                    load_batch(batch)
                self.assertEqual(error.exception.code, 'KERNEL_DRIFT')
