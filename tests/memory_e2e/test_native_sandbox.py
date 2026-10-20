import copy
import unittest

from eval_memory_e2e.io import MemoryEvaluationError, sha
from eval_memory_e2e.native_sandbox import intersect_permissions, native_path, transform_request
from eval_memory_e2e.seatbelt_composition import compose, HEADER


class NativePolicyResearchTests(unittest.TestCase):
    def setUp(self):
        self.native = {'type': 'managed', 'network': 'restricted', 'file_system': {
            'type': 'restricted', 'entries': [
                {'path': {'type': 'path', 'path': 'file:///'}, 'access': 'read'},
                {'path': {'type': 'path', 'path': 'file:///unit'}, 'access': 'write'},
                {'path': {'type': 'path', 'path': 'file:///unit/private'}, 'access': 'none'}]}}

    def test_prefix_math_preserves_native_exclusions_and_network_without_mutating_input(self):
        before = copy.deepcopy(self.native)
        result = intersect_permissions(self.native, [('/', 'read'), ('/unit', 'write'), ('/old', 'none')])
        entries = {native_path(e['path']['path']): e['access'] for e in result['file_system']['entries']}
        self.assertEqual(entries['/unit'], 'write')
        self.assertEqual(entries['/unit/private'], 'none')
        self.assertEqual(entries['/old'], 'none')
        self.assertEqual(result['network'], 'restricted')
        self.assertEqual(self.native, before)

    def test_explicit_grants_below_denied_outer_root_stay_denied_lexically(self):
        self.native['file_system']['entries'].append({'path': {'type': 'path', 'path': 'file:///old/child'}, 'access': 'write'})
        result = intersect_permissions(self.native, [('/', 'read'), ('/old', 'none')])
        self.assertEqual(result['file_system']['entries'][-1]['access'], 'none')

    def test_unrecognized_profile_and_dynamic_permissions_fail_closed(self):
        for profile in [{'type': 'disabled'}, {'type': 'external', 'network': 'enabled'},
                        dict(self.native, unsupported=True), dict(self.native, network='unknown')]:
            with self.assertRaises(MemoryEvaluationError):
                intersect_permissions(profile, [('/', 'read')])
        for entry in [{'path': {'type': 'glob', 'pattern': '/unit/*'}, 'access': 'read'},
                      {'path': {'type': 'special', 'value': 'project_roots'}, 'access': 'write'},
                      {'path': {'type': 'path', 'path': 'file:///unit'}, 'access': 'write', 'missing_path_behavior': 'skip'}]:
            bad = copy.deepcopy(self.native); bad['file_system']['entries'].append(entry)
            with self.assertRaises(MemoryEvaluationError):
                intersect_permissions(bad, [('/', 'read')])

    def test_file_uri_validation_does_not_touch_filesystem(self):
        self.assertEqual(native_path('file:///unit/a%20b'), '/unit/a b')
        for value in ['/absolute', 'https://invalid/', 'file://remote/unit', 'file:///unit/../old',
                      'file:///unit/%2e%2e/old', 'file:///unit?grant=all', 'file:///unit%00hidden']:
            with self.assertRaises(MemoryEvaluationError):
                native_path(value)

    def test_prefix_bridge_is_never_an_application_boundary(self):
        message = {'id': 1, 'method': 'fs/readFile', 'params': {'path': 'file:///old'}}
        for spec in [{}, {'synthetic_only': True},
                     {'synthetic_only': True, 'diagnostic_peer': {}, 'application_integration_allowed': True}]:
            with self.assertRaises(MemoryEvaluationError) as exc:
                transform_request(message, spec)
            self.assertEqual(exc.exception.code, 'NATIVE_PREFIX_NOT_ADMITTED')

    def test_controller_execution_features_and_unknown_apis_remain_blocked(self):
        spec = {'synthetic_only': True, 'diagnostic_peer': {}, 'application_integration_allowed': False,
                'mandatory': [('/', 'read')], 'runtime': '/unit'}
        for params in [{'shellSnapshot': {'shell': 'zsh'}}, {'networkProxy': {'enabled': True}},
                       {'managedNetwork': {'proxy': 'anything'}}, {'enforceManagedNetwork': True}]:
            with self.assertRaises(MemoryEvaluationError):
                transform_request({'method': 'process/start', 'params': params}, spec)
        with self.assertRaises(MemoryEvaluationError):
            transform_request({'method': 'unknown/data/read'}, spec)


class SeatbeltCompositionTests(unittest.TestCase):
    def setUp(self):
        self.native = '(version 1)\n(deny default)\n(allow file-read* (subpath (param "ROOT")))\n'
        self.outer = HEADER + '(deny file-read* file-write* (subpath "/synthetic/non-target"))\n(deny appleevent-send)\n'

    def test_native_profile_is_byte_preserved_without_appending_any_controller_grant(self):
        result = compose(self.native, sha(self.native.encode()), self.outer, sha(self.outer.encode()))
        self.assertTrue(result['profile'].startswith(self.native))
        self.assertNotIn('(allow default)', result['profile'])
        self.assertEqual(result['profile'].count('(version 1)'), 1)
        self.assertFalse(result['controller_grants_appended'])
        self.assertFalse(result['automatic_consolidation_admitted'])

    def test_hash_drift_is_refused(self):
        with self.assertRaises(MemoryEvaluationError):
            compose(self.native + ' ', sha(self.native.encode()), self.outer, sha(self.outer.encode()))

    def test_extra_grants_macros_imports_and_code_are_refused(self):
        for body in ['(allow file-read*)', '(include "anything")', '(define deny allow)',
                     '(deny file-read* (begin (allow default)))', '(deny file-read* (subpath "relative"))',
                     '(deny file-read* (require-not (subpath "/a") (subpath "/b")))', '(deny)',
                     '(deny file-read* (subpath "/a")) )', '(deny file-read* (subpath "/a")']:
            outer = HEADER + body
            with self.assertRaises((MemoryEvaluationError, ValueError)):
                compose(self.native, sha(self.native.encode()), outer, sha(outer.encode()))


if __name__ == '__main__':
    unittest.main()
