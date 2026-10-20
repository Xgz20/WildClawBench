import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.io import MemoryEvaluationError, sha
from eval_memory_e2e.native_kernel import load_kernel


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
