"""Synthetic policy/transport tests; no production task, Harness or Judge runs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tests.general_e2e.test_external_quota_admission import native_failure, encoded
from tests.general_e2e.test_general_scoring_orchestration import Fixture, SCORE_RUNTIME as SCORE, ORCHESTRATOR

POLICY = SCORE.execution_accountability


class ExecutionAccountabilityTests(unittest.TestCase):
    def test_unregistered_native_failures_prepare_for_every_grading_type_without_sdk_terminal(self):
        for grading in ('automated', 'hybrid', 'llm_judge'):
            with self.subTest(grading=grading), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory), task_ids=('not-in-any-task-registry',), grading_type=grading)
                execution, _ = native_failure(f, f.task_ids[0], message='provider tool transport failed')
                before = f.execution_records[f.task_ids[0]].read_bytes()
                result = f.initialize()
                state = json.loads((Path(result['orchestration_root']) / 'orchestration-state.json').read_bytes())
                task = state['tasks'][0]
                self.assertIsNotNone(task['attempt_path'])
                root = Path(result['orchestration_root']) / task['attempt_path']
                manifest = json.loads((root / 'attempt-manifest.json').read_bytes())
                self.assertEqual(manifest['evidence_admission'], POLICY.FAILED_ADMISSION)
                self.assertEqual(manifest['runtime']['evidence_accountability_profile'], POLICY.PROFILE)
                receipt = json.loads((root / 'private/evidence-admission.json').read_bytes())
                self.assertFalse(receipt['sdk_terminal_required_for_admission'])
                self.assertFalse(receipt['numeric_decisions_assigned'])
                self.assertEqual(json.loads((root / 'private/execution-record.json').read_bytes()), execution)
                self.assertEqual(f.execution_records[f.task_ids[0]].read_bytes(), before)
                self.assertFalse(list(root.rglob('score.json')))
                self.assertEqual(SCORE.verify_attempt(root)['status'], 'PASS')
                self.assertEqual(SCORE.verify_attempt(root, require_runtime=False)['status'], 'PASS')
                SCORE._remove_tree(root)

    def test_admission_checks_prompt_native_identity_and_failure_source_bytes(self):
        for mutation in ('prompt', 'turn_id', 'native_error', 'source'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory), task_ids=('arbitrary-task',))
                execution, files = native_failure(f, f.task_ids[0], message='native failure')
                if mutation == 'prompt':
                    execution['prompt']['sha256'] = 'a' * 64
                elif mutation == 'turn_id':
                    execution['session']['turn_id'] = 'another-turn'
                elif mutation == 'native_error':
                    execution['execution']['error']['message'] = 'rewritten failure'
                else:
                    files['original-state.json'] += b' '
                with self.assertRaises(ValueError):
                    SCORE.failure_evidence.validate_accountable(execution, {'task_id': 'arbitrary-task'}, files)

    def test_missing_final_answer_extractor_handoff_keeps_original_numeric_rule(self):
        rule = """def _final_answer(transcript):
    completed = []
    if not completed:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')
    return 'answer', {}

def grade(transcript, workspace_path):
    answer, evidence = _final_answer(transcript)
    return {'candidate_work': 0.5, 'overall_score': 0.5}
"""
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), task_ids=('new-task-with-known-extractor',), grading_type='automated',
                        contract_overrides={'automated_checks': rule})
            native_failure(f, f.task_ids[0], message='native provider failure')
            result = f.initialize()
            root = Path(result['orchestration_root'])
            task = json.loads((root / 'orchestration-state.json').read_bytes())['tasks'][0]
            attempt = root / task['attempt_path']
            manifest = json.loads((attempt / 'attempt-manifest.json').read_bytes())
            self.assertEqual(manifest['runtime']['interrupted_answer_delivery_profile']['profile'],
                             SCORE.interrupted_answer_delivery.GENERAL_PROFILE)
            result = SCORE.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
            self.assertEqual(result['rule_component']['score'], .5)
            self.assertEqual(json.loads((attempt / 'private/contract.json').read_bytes())['automated_checks'], rule)
            self.assertFalse(list(attempt.rglob('score.json')))
            SCORE._remove_tree(attempt)

    def test_read_only_assessment_distinguishes_native_failure_unsent_and_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), task_ids=('native', 'unsent', 'unknown'))
            native_failure(f, 'native', message='native transport failed')
            record = json.loads(f.execution_records['unsent'].read_bytes())
            record.update(phase='FAILED', prompt={'send_status': 'not_sent'})
            record['execution']['business_status'] = 'infrastructure_error'
            f.execution_records['unsent'].write_bytes(encoded(record))
            record = json.loads(f.execution_records['unknown'].read_bytes())
            record.update(phase='FAILED', prompt={'send_status': 'unknown'})
            record['execution']['business_status'] = 'infrastructure_error'
            f.execution_records['unknown'].write_bytes(encoded(record))
            before = {k: p.read_bytes() for k, p in f.execution_records.items()}
            decisions = {k: SCORE.assess_execution(unit_root=f.unit_root, execution_record_path=p)
                         for k, p in f.execution_records.items()}
            self.assertEqual(decisions['native']['disposition'], 'score_original_execution')
            self.assertEqual(decisions['unsent']['disposition'], 'repair_before_execution')
            self.assertEqual(decisions['unknown']['disposition'], 'needs_user_decision')
            issue = decisions['unknown']['decision_request']
            self.assertEqual(issue['prompt_send_status'], 'unknown')
            self.assertTrue(issue['required_review'])
            self.assertTrue(issue['decision_question'])
            self.assertEqual(before, {k: p.read_bytes() for k, p in f.execution_records.items()})
            self.assertFalse(list(f.unit_root.rglob('score.json')))

    def test_collected_native_error_admits_stale_status_without_rewriting_old_record(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), task_ids=('collected-native-error',))
            execution, files = native_failure(f, f.task_ids[0], message='native item/tool/call error')
            execution.pop('failure_evidence')
            record = f.execution_records[f.task_ids[0]]
            record.write_bytes(encoded(execution))
            state = json.loads(files['original-state.json'])
            state['session']['native_status'] = 'running'
            state['history'] = [{'phase': 'FAILED', 'event': 'NATIVE_TERMINAL_OBSERVED',
                                 'native_status': 'running', 'turn_state': 'error'}]
            prompt = f.unit_root / 'execution/tasks/collected-native-error/PROMPT.md'
            prompt.parent.mkdir(parents=True);prompt.write_bytes(files['PROMPT.md'])
            state['prompt']['path'] = str(prompt)
            state_path = record.parent / 'execution/automation-state.json'
            state_path.parent.mkdir();state_path.write_bytes(encoded(state))
            from tests.general_e2e.test_general_scoring_orchestration import sha256_bytes
            manifest = {'identity': execution['identity'], 'artifacts': [{
                'path': state_path.relative_to(f.unit_root).as_posix(),
                'sha256': sha256_bytes(state_path.read_bytes()), 'size': state_path.stat().st_size}]}
            record.with_name('evidence-manifest.json').write_bytes(encoded(manifest))
            before = record.read_bytes()
            assessment = SCORE.assess_execution(unit_root=f.unit_root, execution_record_path=record)
            self.assertEqual(assessment['disposition'], 'score_original_execution')
            result = f.initialize()
            root = Path(result['orchestration_root'])
            task = json.loads((root / 'orchestration-state.json').read_bytes())['tasks'][0]
            attempt = root / task['attempt_path']
            self.assertEqual(SCORE.verify_attempt(attempt, require_runtime=False)['status'], 'PASS')
            receipt = json.loads((attempt / 'private/evidence-admission.json').read_bytes())
            self.assertEqual(receipt['native_session_status_projection'], 'running')
            self.assertFalse(receipt['numeric_decisions_assigned'])
            self.assertEqual(record.read_bytes(), before)
            state_path.write_bytes(state_path.read_bytes() + b' ')
            self.assertEqual(SCORE.assess_execution(unit_root=f.unit_root, execution_record_path=record)['disposition'], 'needs_user_decision')
            SCORE._remove_tree(attempt)

    def test_unresolved_requires_actionable_evaluator_or_source_issue(self):
        request = {'evidence_accountability_policy': POLICY.POLICY}
        issue = {'criterion_key': 'C7', 'origin': 'task_source', 'problem': '缺少当时工具契约',
                 'missing_evidence': '原session_meta未提供registry的完整inputSchema',
                 'evidence_checked': '已查原SDK首行和全部调用回执',
                 'why_rules_cannot_decide': '调用成功不能证明参数完全符合当时schema',
                 'repair_execution_impact': '补参考不改变原作答，无法补齐时需用户决定',
                 'proposed_actions': ['补充绑定版本的原接口定义'], 'decision_question': '是否能提供该版本接口定义？'}
        response = {'criteria': [{'key': 'C7', 'status': 'unresolved', 'score': None}],
                    'decision_requests': [issue]}
        POLICY.validate_response(request, response)
        listed = copy.deepcopy(response)
        listed['decision_requests'][0]['evidence_checked'] = ['已查原始SDK首行', '已查全部工具回执，缺少接口参照']
        POLICY.validate_response(request, listed)
        listed['decision_requests'][0]['evidence_checked'] = []
        with self.assertRaises(ValueError): POLICY.validate_response(request, listed)
        for invalid in ('harness', 'empty', 'missing'):
            changed = copy.deepcopy(response)
            if invalid == 'harness': changed['decision_requests'][0]['origin'] = 'harness'
            elif invalid == 'empty': changed['decision_requests'][0]['evidence_checked'] = ''
            else: changed['decision_requests'] = []
            with self.assertRaises(ValueError): POLICY.validate_response(request, changed)

    def test_missing_candidate_proof_can_be_judged_zero_without_whole_task_zero(self):
        POLICY.validate_response({'evidence_accountability_policy': POLICY.POLICY}, {
            'criteria': [{'key': 'C1', 'status': 'judged', 'score': .5},
                         {'key': 'C7', 'status': 'judged', 'score': 0}], 'decision_requests': []})
        self.assertIsNone(POLICY.policy({'runtime': {}}))

    def test_blocked_framework_execution_surfaces_review_instead_of_silent_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), task_ids=('unsent',))
            record = json.loads(f.execution_records['unsent'].read_bytes())
            record.update(phase='FAILED', prompt={'send_status': 'not_sent'})
            record['execution']['business_status'] = 'infrastructure_error'
            f.execution_records['unsent'].write_bytes(encoded(record))
            result = f.initialize()
            state = json.loads((Path(result['orchestration_root']) / 'orchestration-state.json').read_bytes())
            review = state['tasks'][0]['execution_review']
            self.assertEqual(review['disposition'], 'repair_before_execution')
            actions = result['recommended_actions']
            self.assertEqual(actions[0]['action'], 'REPAIR_AND_REEXECUTE')
            self.assertFalse(actions[0]['requires_user_decision'])
            self.assertFalse(actions[0]['score_assigned'])
            self.assertFalse(list(f.output_root.rglob('score.json')))


if __name__ == '__main__':
    unittest.main()
