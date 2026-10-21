import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e import production_sandbox_probe as probe
from eval_memory_e2e.io import MemoryEvaluationError


class ProductionSandboxProbeTests(unittest.TestCase):
    def test_fixture_paths_reject_absolute_and_parent_escape(self):
        for relative in ('../memory.md', '/Users/foreign/memory.md', 'active/../../memory.md'):
            with self.assertRaises(MemoryEvaluationError):
                probe.fixture_path('/Users/synthetic/debug/probe', relative)
        self.assertEqual(str(probe.fixture_path('/Users/synthetic/debug/probe', 'old-case/memory.md')),
                         '/Users/synthetic/debug/probe/fixture/old-case/memory.md')

    def test_unowned_or_foreign_roots_cannot_start_a_kernel_or_backend(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); debug = root / 'debug'; debug.mkdir()
            with patch.object(probe, 'machine_paths', return_value={'debug': debug}), \
                    patch.object(probe, 'kernel_identity') as kernel, \
                    patch.object(probe.subprocess, 'Popen') as spawn:
                with self.assertRaises(MemoryEvaluationError):
                    probe.run(root / 'foreign')
                with self.assertRaises(FileNotFoundError):
                    probe.backend_probe(debug, {}, {})
                kernel.assert_not_called(); spawn.assert_not_called()

    def test_native_profile_keeps_network_and_readonly_limits_and_denies_old_units(self):
        value = tomllib.loads(probe.profile_config('/Users/synthetic/probe'))
        profile = value['permissions'][probe.PROFILE]
        self.assertIs(profile['network']['enabled'], False)
        for name in ('non-target', 'old-case', 'old-repeat', 'active/private'):
            self.assertEqual(profile['filesystem'][str(probe.fixture_path('/Users/synthetic/probe', name))], 'deny')
        self.assertEqual(profile['filesystem']['/Users/synthetic/probe/fixture/active/readonly'], 'read')
        self.assertNotIn('features', value)

    def test_native_probe_does_not_inherit_authentication_or_kernel_overrides(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'SYNTHETIC-SECRET', 'ACODE_API_KEY': 'SYNTHETIC-SECRET',
                                    'ASTUDIO_ACODE_BIN': '/synthetic/custom', 'ACODE_EXEC_SERVER_URL': 'ws://synthetic'}):
            environment = probe.probe_environment('/Users/synthetic/private', '/Users/synthetic/tmp')
        self.assertEqual(environment['ACODE_HOME'], '/Users/synthetic/private')
        for name in ('OPENAI_API_KEY', 'ACODE_API_KEY', 'CODEX_HOME', 'ASTUDIO_ACODE_BIN', 'ACODE_EXEC_SERVER_URL', 'DYLD_INSERT_LIBRARIES'):
            self.assertNotIn(name, environment)
