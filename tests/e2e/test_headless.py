import json
import os
from pathlib import Path
import stat
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.e2e.common import E2EError, file_sha256, digest
from src.e2e.headless import normalize_config, inspect_container, owned, _private_environment, _check_files, _result_row
from src.e2e.headless import _admit_immutable_inputs, score_one
from src.e2e.artifacts import remove_temporary_tree, inventory


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

    @patch('src.e2e.headless.docker')
    def test_unready_terminal_execution_keeps_its_failure_without_a_worker(self, docker):
        for phase in ('FAILED', 'CANCELLED', 'NEEDS_ATTENTION'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'batch/execution').mkdir(parents=True)
                reason = 'CONTROLLER_EXECUTION_INCOMPLETE: task_timeout'
                item = {'key': 'k', 'task_id': 't', 'unit_id': 'u', 'run_index': 1, 'attempt_id': 'original',
                        'phase': phase, 'execution_root': 'execution', 'error': {'message': reason}}
                args = (root / 'batch', item, {}, self.config(), root / 'job', 'job', 'synthetic-key')
                result = score_one(*args)
                self.assertEqual(result['status'], 'unscored')
                self.assertEqual(result['error'], reason)
                self.assertTrue(result['execution_not_ready'])
                self.assertTrue(result['container_released'])
                self.assertIsNone(result['total_score'])
                self.assertEqual(score_one(*args), result)
                docker.assert_not_called()

    def test_context_keeps_relative_links_and_rejects_link_target_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'batch').mkdir()
            item = {'key': 'k', 'task_id': 't', 'unit_id': 'u', 'run_index': 1,
                    'attempt_id': 'original', 'phase': 'COMPLETED', 'execution_root': 'execution'}
            def materialize(batch, key, target, **kwargs):
                (target / 'workspace/cache').mkdir(parents=True)
                (target / 'workspace/guard.txt').write_text('sealed original')
                (target / 'workspace/other.txt').write_text('other original')
                (target / 'workspace/cache/link').symlink_to('../guard.txt')
                (target / 'installed').mkdir()
                (target / 'installed/skill.txt').write_text('frozen skill')
                (target / 'handoff.json').write_text('{}')
                return {'installed_skills': str(target / 'installed')}
            args = (root / 'batch', item, {'tasks': [{'task_id': 't', 'scene': 'general'}]},
                    self.config(), root / 'job', 'job', 'synthetic-key')
            with patch('src.e2e.headless.verify_ready'), patch('src.e2e.headless.BatchStore') as store, \
                 patch('src.e2e.headless.export_scoring_context', side_effect=materialize), \
                 patch('src.e2e.headless.owned', return_value=None), \
                 patch('src.e2e.headless.docker', side_effect=E2EError('FIXTURE_STOP_BEFORE_CREATE')):
                store.return_value.scoring_rows.return_value = []
                result = score_one(*args)
                self.assertEqual(result['error'], 'FIXTURE_STOP_BEFORE_CREATE')
                context = root / 'job/work/context'
                link = context / 'workspace/cache/link'
                self.assertTrue(link.is_symlink())
                state = json.loads((root / 'job/control/state.json').read_text())
                self.assertEqual(state['source_context_sha256'], digest(inventory(context, allow_symlinks=True)))
                link.unlink();link.symlink_to('../other.txt')
                self.assertEqual(score_one(*args)['error'], 'SCORING_SOURCE_CONTEXT_DRIFT')
                link.unlink();link.symlink_to('../../../../outside')
                self.assertIn('WORKSPACE_LINK_TARGET_OUTSIDE', score_one(*args)['error'])

    def test_explicit_score_skill_freezes_complete_inventory_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'skill-metadata.json').write_text(json.dumps({'name': 'score-general-e2e',
                'contract_version': 'general-e2e-contract-v1', 'version': 'fixture'}))
            (root / 'grader.py').write_text('original rule reader')
            configured = self.config(score_skill_dir=str(root))
            self.assertEqual(len(configured['score_skill_inventory_sha256']), 64)
            (root / 'grader.py').write_text('changed reader')
            with self.assertRaisesRegex(E2EError, 'HEADLESS_SCORE_SKILL_DRIFT'):
                normalize_config(configured)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS bind-mount input protection')
    def test_host_admission_blocks_office_inode_replacement_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'result.xlsx'
            original.write_bytes(b'original frozen bytes')
            original.chmod(0o444)
            expected = {'result.xlsx': file_sha256(original)}
            try:
                receipt = _admit_immutable_inputs(root, expected)
                self.assertEqual(receipt['files'], ['result.xlsx'])
                self.assertEqual(original.read_bytes(), b'original frozen bytes')
                self.assertTrue(original.stat().st_flags & stat.UF_IMMUTABLE)
                replacement = root / 'new.xlsx'
                replacement.write_bytes(b'host metadata replacement')
                with self.assertRaises(PermissionError):
                    replacement.replace(original)
                original2 = root / 'drift.xlsx'
                original2.write_bytes(b'already changed')
                with self.assertRaisesRegex(E2EError, 'IMMUTABLE_INPUT_DRIFT'):
                    _admit_immutable_inputs(root, {'drift.xlsx': expected['result.xlsx']})
                self.assertFalse(original2.stat().st_flags & stat.UF_IMMUTABLE)
            finally:
                remove_temporary_tree(root)


if __name__ == '__main__':
    unittest.main()
