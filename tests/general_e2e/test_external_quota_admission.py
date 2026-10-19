"""Synthetic native-failure evidence; no Harness, provider or Judge is run."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_general_scoring_orchestration import (
    Fixture, ORCHESTRATOR, SCORE_RUNTIME, sha256_bytes,
)

FAILURE = SCORE_RUNTIME.failure_evidence
QUOTA_MESSAGE = 'unexpected status 402 Payment Required: astron_points_exhausted, url: http://127.0.0.1:12345/v1/responses'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def native_failure(fixture, task_id, message=QUOTA_MESSAGE):
    record = fixture.execution_records[task_id]
    execution = json.loads(record.read_bytes())
    prompt = b'Synthetic prompt, not a production task.'
    execution.update(phase='FAILED', harness={'id': 'astronstudio'},
                     prompt={'send_status': 'sent', 'sha256': sha256_bytes(prompt)},
                     session={'verified': True, 'thread_id': 'arbitrary-thread', 'turn_id': 'arbitrary-turn',
                              'session_id': 'arbitrary-native-session', 'cwd': '/synthetic/workspace'})
    execution['execution'] = {'business_status': 'candidate_error',
                              'error': {'code': 'ASTRONSTUDIO_TURN_ERROR', 'message': message}}
    execution['evidence'] = {'completeness': 'partial', 'missing': ['native-failure'],
                             'transcript_path': None, 'trace_index_path': None, 'final_response_path': None}
    original = copy.deepcopy(execution)
    state = copy.deepcopy(execution)
    state['session']['native_status'] = 'error'
    state['send'] = {'dispatch_attempt_count': 1}
    files = {'original-execution-record.json': encoded(original), 'original-state.json': encoded(state), 'PROMPT.md': prompt}
    manifest = {'identity': execution['identity'], 'artifacts': [
        {'path': 'evidence/synthetic/execution/automation-state.json', 'sha256': sha256_bytes(files['original-state.json'])}]}
    files['original-evidence-manifest.json'] = encoded(manifest)
    proof = {'schema': FAILURE.ADMISSION, 'identity': execution['identity'],
             'source_record_sha256': sha256_bytes(files['original-execution-record.json']),
             'files': [{'path': k, 'sha256': sha256_bytes(v), 'size': len(v)} for k, v in files.items()]}
    files['proof.json'] = encoded(proof)
    directory = record.parent / 'failure-proof'
    directory.mkdir()
    for name, value in files.items():
        (directory / name).write_bytes(value)
    execution['failure_evidence'] = {'schema': FAILURE.ADMISSION,
                                    'path': (directory / 'proof.json').relative_to(fixture.unit_root).as_posix(),
                                    'sha256': sha256_bytes(files['proof.json'])}
    record.write_bytes(encoded(execution))
    return execution, files


class ExternalQuotaAdmissionTests(unittest.TestCase):
    def test_native_quota_stops_all_grading_types_without_score_or_submission(self):
        for grading_type in ('automated', 'hybrid', 'llm_judge'):
            with self.subTest(grading_type=grading_type), tempfile.TemporaryDirectory() as temp:
                fixture = Fixture(Path(temp), task_ids=('arbitrary-task',), grading_type=grading_type)
                native_failure(fixture, 'arbitrary-task')
                before = fixture.execution_records['arbitrary-task'].read_bytes()
                with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, 'EXECUTION_EXTERNAL_QUOTA_EXHAUSTED'):
                    fixture.initialize()
                self.assertFalse(list(fixture.output_root.rglob('score.json')))
                self.assertFalse(list(fixture.output_root.rglob('submission.json')))
                self.assertFalse(list(fixture.output_root.glob('*.staging-*')))
                self.assertEqual(fixture.execution_records['arbitrary-task'].read_bytes(), before)

    def test_quota_stop_does_not_prepare_later_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp), task_ids=('quota-task', 'normal-task'))
            native_failure(fixture, 'quota-task')
            original = ORCHESTRATOR._run_score_command
            prepared = []
            def command(lock, arguments, **kwargs):
                if arguments[0] == 'prepare':
                    prepared.append(arguments[arguments.index('--task-id') + 1])
                return original(lock, arguments, **kwargs)
            with patch.object(ORCHESTRATOR, '_run_score_command', side_effect=command):
                with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, 'EXECUTION_EXTERNAL_QUOTA_EXHAUSTED'):
                    fixture.initialize()
            self.assertEqual(prepared, ['quota-task'])
            self.assertFalse(list(fixture.output_root.rglob('submission.json')))

    def test_missing_quota_proof_is_not_silently_unscored(self):
        for missing_proof in (True, False):
            with self.subTest(missing_proof=missing_proof), tempfile.TemporaryDirectory() as temp:
                fixture = Fixture(Path(temp), task_ids=('quota-task',))
                execution, _ = native_failure(fixture, 'quota-task')
                if missing_proof:
                    execution.pop('failure_evidence')
                else:
                    execution['execution']['business_status'] = 'infrastructure_error'
                fixture.execution_records['quota-task'].write_bytes(encoded(execution))
                with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, 'EXTERNAL_QUOTA_EVIDENCE_INVALID'):
                    fixture.initialize()
                self.assertFalse(list(fixture.output_root.rglob('submission.json')))

    def test_detached_score_skill_preserves_the_human_recovery_stop(self):
        from tests.general_e2e.test_e2e_build import BUILD, FIXED_REVISION, REPO_ROOT
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            built = BUILD.build_skill_package(REPO_ROOT, root / 'packages', 'score-general-e2e', source_revision=FIXED_REVISION)
            archive = root / 'packages' / built['archive']
            BUILD.verify_skill_package(archive, built)
            installed = BUILD._safe_extract(archive, root / 'detached')
            fixture = Fixture(root / 'fixture', task_ids=('detached-quota',))
            native_failure(fixture, 'detached-quota')
            with patch('tests.general_e2e.test_general_scoring_orchestration.SCORE_SKILL', installed):
                with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, 'EXECUTION_EXTERNAL_QUOTA_EXHAUSTED'):
                    fixture.initialize()
            self.assertFalse(list(fixture.output_root.rglob('orchestration-state.json')))

    def test_recognition_requires_native_error_code_and_exact_provider_status(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp), task_ids=('test-task',))
            execution, _ = native_failure(fixture, 'test-task')
            self.assertTrue(FAILURE.is_external_quota(execution))
            for message in ['402', 'astron_points_exhausted',
                            QUOTA_MESSAGE.replace('402', '403'), QUOTA_MESSAGE.replace('astron_points_exhausted', 'other_error'),
                            'candidate said: ' + QUOTA_MESSAGE, QUOTA_MESSAGE + '\nother content']:
                changed = copy.deepcopy(execution)
                changed['execution']['error']['message'] = message
                self.assertFalse(FAILURE.is_external_quota(changed), message)
            for key, value in [('code', 'CANDIDATE_OUTPUT'), ('code', []), ('message', None)]:
                changed = copy.deepcopy(execution)
                changed['execution']['error'][key] = value
                self.assertFalse(FAILURE.is_external_quota(changed))
            changed = copy.deepcopy(execution)
            changed['harness']['id'] = 'unreviewed-harness'
            self.assertFalse(FAILURE.is_external_quota(changed))
            for malformed in (None, [], 'candidate error'):
                changed = copy.deepcopy(execution)
                changed['execution']['error'] = malformed
                self.assertFalse(FAILURE.is_external_quota(changed))

    def test_proof_identity_prompt_candidate_and_error_binding_reject_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp), task_ids=('test-task',))
            execution, files = native_failure(fixture, 'test-task')
            FAILURE.validate_external_quota(execution, files)
            changes = [
                lambda e: e['identity'].update(attempt_id='wrong-attempt'),
                lambda e: e['candidate'].update(frozen_sha256='0' * 64),
                lambda e: e['candidate'].update(drift_status='changed'),
                lambda e: e['prompt'].update(sha256='0' * 64),
                lambda e: e['prompt'].update(send_status='unknown'),
                lambda e: e['session'].update(verified=False),
                lambda e: e['session'].update(turn_id='wrong-turn'),
                lambda e: e['failure_evidence'].update(sha256='0' * 64),
                lambda e: e['execution']['error'].update(message=QUOTA_MESSAGE.replace('12345', '54321')),
            ]
            for change in changes:
                with self.subTest(change=change):
                    changed = copy.deepcopy(execution)
                    change(changed)
                    with self.assertRaises(ValueError):
                        FAILURE.validate_external_quota(changed, files)
            changed_files = dict(files)
            changed_files['original-state.json'] += b' '
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_SHA'):
                FAILURE.validate_external_quota(execution, changed_files)

    def test_tampered_or_symlinked_proof_stops_initialization_instead_of_becoming_unscored(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as temp:
                fixture = Fixture(Path(temp), task_ids=('test-task',))
                execution, _ = native_failure(fixture, 'test-task')
                proof = fixture.unit_root / execution['failure_evidence']['path']
                if symlink:
                    other = Path(temp) / 'outside-proof.json'
                    other.write_bytes(proof.read_bytes())
                    proof.unlink()
                    proof.symlink_to(other)
                else:
                    proof.write_bytes(proof.read_bytes() + b' ')
                with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, 'EXTERNAL_QUOTA_EVIDENCE_INVALID'):
                    fixture.initialize()
                self.assertFalse(list(fixture.output_root.rglob('submission.json')))

    def test_non_quota_failures_keep_reviewed_contract_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp), task_ids=('test-task',))
            execution, files = native_failure(fixture, 'test-task', 'native max_output_tokens')
            self.assertFalse(FAILURE.is_external_quota(execution))
            contract = {'task_id': 'test-task', 'grading_type': 'hybrid'}
            digest = sha256_bytes(json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
            policy = Path(temp) / 'policy.json'
            policy.write_bytes(encoded({'schema_version': 'wildclawbench.failed-output-evidence-policy/v1', 'profiles': {
                digest: {**contract, 'candidate_required': True, 'tool_history_required': False, 'final_response_required': False}}}))
            with patch.object(FAILURE, 'POLICY_PATH', policy):
                self.assertTrue(FAILURE.validate(execution, contract, files)['original_failure_preserved'])
                with self.assertRaisesRegex(ValueError, 'CONTRACT_NOT_REVIEWED'):
                    FAILURE.profile(execution, {**contract, 'grading_type': 'llm_judge'})


if __name__ == '__main__':
    unittest.main()
