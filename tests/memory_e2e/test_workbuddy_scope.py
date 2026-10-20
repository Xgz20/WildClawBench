import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.workbuddy_scope import current_native_uid, minimal_model_config, APP
from eval_memory_e2e.io import MemoryEvaluationError


class WorkBuddyScopeTests(unittest.TestCase):
    def test_only_the_requested_provider_is_imported_without_other_settings(self):
        wanted = {'id': 'xopglm52', 'name': 'xopglm52', 'url': 'https://synthetic.invalid/v1/chat/completions',
                  'apiKey': 'SYNTHETIC-NOT-A-CREDENTIAL', 'supportsToolCall': True,
                  'reasoning': {'defaultEffort': 'high', 'supportedEfforts': ['high'], 'canDisableThinking': True},
                  'supportsReasoning': True, 'useCustomProtocol': True}
        source = [wanted, {'id': 'another-provider', 'name': 'not imported'}]
        before = copy.deepcopy(source)
        self.assertEqual(minimal_model_config(source), [wanted])
        self.assertEqual(source, before)

    def test_unknown_model_instruction_duplicate_or_missing_auth_is_rejected(self):
        base = {'id': 'xopglm52', 'name': 'xopglm52', 'url': 'https://synthetic.invalid/v1',
                'apiKey': 'SYNTHETIC-NOT-A-CREDENTIAL', 'supportsToolCall': True}
        cases = [[dict(base, systemPrompt='must not be imported')], [base, base], [dict(base, apiKey='')],
                 [dict(base, apiKey='${SYNTHETIC_ENV}')], [dict(base, reasoning={'instructions': 'must not be imported'})]]
        for source in cases:
            with self.subTest(source_keys=[list(x) for x in source]):
                with self.assertRaises(MemoryEvaluationError):
                    minimal_model_config(source)

    def test_native_account_metadata_requires_the_exact_ordinary_home_argument(self):
        binary = str(APP / 'Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.8.6/sandbox-cli')
        ordinary = Path('/Users/SYNTHETIC/.workbuddy')
        rows = '\n'.join([binary + ' --uid correct --app_home ' + str(ordinary),
                          binary + ' --uid private --app_home ' + str(ordinary) + '-another-unit'])
        with patch('eval_memory_e2e.workbuddy_scope.machine_paths', return_value={'workbuddy': ordinary}), \
                patch('eval_memory_e2e.workbuddy_scope.subprocess.check_output', return_value=rows):
            self.assertEqual(current_native_uid(), 'correct')
        with patch('eval_memory_e2e.workbuddy_scope.machine_paths', return_value={'workbuddy': ordinary}), \
                patch('eval_memory_e2e.workbuddy_scope.subprocess.check_output', return_value=rows.splitlines()[1]):
            self.assertIsNone(current_native_uid(optional=True))
            with self.assertRaises(MemoryEvaluationError):
                current_native_uid()
