import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.e2e.common import E2EError, file_sha256
from src.e2e.headless import normalize_config, inspect_container, owned, _private_environment, _check_files, _result_row


class HeadlessContractTests(unittest.TestCase):
    def config(self, **extra):
        return normalize_config({'harness': 'codex', 'model': 'requested-model', 'base_url': 'https://gateway.test/v1',
                                 'image': 'shared-cli:test', **extra})

    def test_model_and_harness_configuration_is_explicit_and_no_secret_values_allowed(self):
        self.assertEqual(self.config()['model'], 'requested-model')
        self.assertEqual(self.config()['reasoning_effort'], 'high')
        self.assertEqual(self.config(harness='deepseek-harness')['reasoning_effort'], 'none')
        with self.assertRaisesRegex(E2EError, 'UNKNOWN_FIELDS'):
            self.config(api_key='should-not-enter-public-config')
        with self.assertRaisesRegex(E2EError, 'CONCURRENCY'):
            self.config(concurrency=0)

    @patch('src.e2e.headless.docker')
    def test_unknown_daemon_state_is_not_treated_as_missing_container(self, command):
        command.return_value = subprocess.CompletedProcess([], 1, '', 'Cannot connect to Docker daemon')
        with self.assertRaisesRegex(E2EError, 'OBSERVATION_UNKNOWN'):
            inspect_container(self.config(), 'stable-job-name')
        command.return_value = subprocess.CompletedProcess([], 1, '', 'No such container: stable-job-name')
        self.assertIsNone(inspect_container(self.config(), 'stable-job-name'))

    @patch('src.e2e.headless.inspect_container')
    def test_shared_image_does_not_grant_ownership_of_another_job(self, inspect):
        inspect.return_value = {'Config': {'Image': 'shared-cli:test', 'Labels': {'org.astron.eval.score-job': 'other'}}}
        with self.assertRaisesRegex(E2EError, 'NOT_OWNED'):
            owned(self.config(), 'name', 'this-job')

    def test_private_environment_is_mode_600_and_immutable_input_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'private.env'
            _private_environment(key, 'synthetic-test-credential')
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            with self.assertRaisesRegex(E2EError, 'CREDENTIAL_REQUIRED'):
                _private_environment(key, 'one\ntwo')
            source = root / 'input.json'
            source.write_text('{}')
            hashes = {'input.json': file_sha256(source)}
            _check_files(root, hashes)
            source.write_text('{"modified":true}')
            with self.assertRaisesRegex(E2EError, 'IMMUTABLE_INPUT_DRIFT'):
                _check_files(root, hashes)

    def test_valid_zero_and_evaluator_error_null_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'attempt').mkdir()
            score_file = root / 'attempt/score.json'
            item = {'key': 'k', 'task_id': 't', 'unit_id': 'u', 'run_index': 1, 'attempt_id': 'original'}
            for valid, value, expected in [(True, 0.0, 'valid'), (False, None, 'evaluation_error')]:
                score_file.write_text(json.dumps({'identity': {'attempt_id': 'judge-a'}, 'result': {'valid': valid, 'total_score': value}}))
                checksum = file_sha256(score_file)
                (root / 'result.json').write_text(json.dumps({'score_path': 'attempt/score.json', 'attempt_root': 'attempt', 'score_sha256': checksum, 'agent_used': True}))
                result = _result_row(item, {'verified': True, 'verification': {'status': 'PASS'}, 'score_sha256': checksum}, root)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['total_score'], value)
                score_file.write_text('{}')
                with self.assertRaisesRegex(E2EError, 'RESULT_DRIFT'):
                    _result_row(item, {'verified': True, 'verification': {}, 'score_sha256': checksum}, root)


if __name__ == '__main__':
    unittest.main()
