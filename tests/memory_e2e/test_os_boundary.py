import ctypes
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from eval_memory_e2e.os_boundary import profile_text, non_target_roots, _attempt, OPERATIONS
from eval_memory_e2e.io import MemoryEvaluationError


class BoundaryTests(unittest.TestCase):
    def test_non_target_paths_are_literals_not_reads_or_resolutions(self):
        with patch('pathlib.Path.stat', side_effect=AssertionError('must not inspect real roots')), \
             patch('pathlib.Path.read_bytes', side_effect=AssertionError('must not read real roots')):
            # machine_paths resolves only the OS home, so stub the already
            # validated account home and ensure target paths are never visited.
            with patch('eval_memory_e2e.os_boundary.machine_paths', return_value={'home':Path('/Users/synthetic')}):
                roots = non_target_roots()
        self.assertIn(Path('/Users/synthetic/.codex'), roots)
        self.assertNotIn(Path('/Users/synthetic/.acode'), roots)
        self.assertIn(Path('/Users/synthetic/.workbuddy'), roots)

    def test_profile_denies_reads_writes_alias_and_apple_events(self):
        profile = profile_text([Path('/Users/synthetic/.codex')])
        self.assertIn('(deny file-read* file-write*', profile)
        self.assertIn('(subpath "/System/Volumes/Data/Users/synthetic/.codex")', profile)
        self.assertIn('(deny appleevent-send)', profile)
        self.assertNotIn('(allow file-read', profile)

    def test_profile_rejects_other_locations_and_control_characters(self):
        for root in ['/tmp/foreign', '/Users/synthetic/bad\npath', '/Users/synthetic/bad\x00path']:
            with self.assertRaises(MemoryEvaluationError): profile_text([root])

    def test_denial_requires_permission_error_not_missing_file(self):
        def error(number):
            raise OSError(number, 'fixture')
        self.assertTrue(_attempt('read', lambda:error(1), True)['pass'])
        self.assertTrue(_attempt('read', lambda:error(13), True)['pass'])
        self.assertFalse(_attempt('read', lambda:error(2), True)['pass'])
        self.assertFalse(_attempt('read', lambda:None, True)['pass'])
        self.assertTrue(_attempt('control', lambda:None, False)['pass'])

    def test_arm64_variadic_os_api_declares_fixed_arguments(self):
        from eval_memory_e2e.os_boundary import check_policy
        class Call:
            def __call__(self, *args):
                self.called=args
                return 1
        call=Call()
        with patch('eval_memory_e2e.os_boundary.ctypes.CDLL') as lib, \
             patch('eval_memory_e2e.os_boundary.ctypes.c_int.in_dll',return_value=ctypes.c_int(1<<30)):
            lib.return_value.sandbox_check=call
            self.assertEqual(check_policy(100,'/Users/synthetic/fixture','file-read-data'),1)
        self.assertEqual(call.argtypes,[ctypes.c_int,ctypes.c_char_p,ctypes.c_int])

    def test_positive_control_is_not_accepted_when_os_query_fails(self):
        from eval_memory_e2e.os_boundary import check_policy
        class Call:
            def __call__(self,*args): return -1
        with patch('eval_memory_e2e.os_boundary.ctypes.CDLL') as lib, \
             patch('eval_memory_e2e.os_boundary.ctypes.c_int.in_dll',return_value=ctypes.c_int(1<<30)):
            lib.return_value.sandbox_check=Call()
            with self.assertRaises(MemoryEvaluationError):check_policy(100,'/Users/synthetic/file','file-read-data')
