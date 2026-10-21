import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e import native_kernel, native_executor, os_boundary
from eval_memory_e2e.io import MemoryEvaluationError
from eval_memory_e2e.production import require_production_environment, require_production_lease


class ProductionPolicyTests(unittest.TestCase):
    def rejected(self, action):
        with self.assertRaises(MemoryEvaluationError) as error:
            action()
        self.assertEqual(error.exception.code, 'ASTUDIO_PRODUCTION_PACKAGE_REQUIRED')

    def test_source_build_actions_stop_before_processes_or_output_creation(self):
        with tempfile.TemporaryDirectory() as raw, patch('subprocess.Popen') as spawn:
            output = Path(raw) / 'must-not-exist'
            actions = [native_kernel.environment, native_kernel.export_patch,
                       lambda: native_kernel.approve_binary(output),
                       lambda: native_kernel.approve_kernel(output, output),
                       lambda: native_kernel.run('build-kernel', output),
                       lambda: native_kernel.run('fmt', output),
                       lambda: native_executor.selftest(output, output),
                       lambda: native_executor.start(output, {}),
                       lambda: native_executor.specification(output, output, output, mode='astudio-owned-session',
                                                            runtime=output, acode_home=output, temp=output),
                       lambda: os_boundary.selftest(output, native_build=output),
                       lambda: os_boundary.selftest(output, compiled_kernel=output)]
            for action in actions:
                self.rejected(action)
            self.assertFalse(output.exists())
            spawn.assert_not_called()

    def test_old_leases_reject_before_kernel_read_or_launch(self):
        for contract in ('macos-seatbelt-astudio-native-executor/v2', 'macos-seatbelt-astudio-compiled-kernel/v3'):
            with tempfile.TemporaryDirectory() as raw, patch('eval_memory_e2e.os_boundary._folder') as folder, \
                    patch('eval_memory_e2e.os_boundary.kernel_identity') as identity:
                root = Path(raw).resolve(); folder.return_value = root
                (root / 'lease.json').write_text(json.dumps({'contract': contract}))
                self.rejected(lambda: os_boundary.load_lease(root / 'lease.json'))
                self.rejected(lambda: os_boundary.launch(root))
                identity.assert_not_called()
        for key in ('compiled_kernel', 'native_executor'):
            self.rejected(lambda: require_production_lease({'contract': os_boundary.ADAPTER, key: None}))

    def test_inherited_overrides_stop_before_any_launch_mutation(self):
        require_production_environment({})
        for key in ('ASTUDIO_ACODE_BIN', 'ACODE_EXEC_SERVER_URL'):
            with patch.dict('os.environ', {key: '/synthetic/override'}), \
                    patch('eval_memory_e2e.os_boundary._folder') as folder:
                self.rejected(lambda: os_boundary.launch('/synthetic/nonexistent'))
                folder.assert_not_called()
