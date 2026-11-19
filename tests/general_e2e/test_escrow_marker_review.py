from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock


class EscrowMarkerReviewTests(unittest.TestCase):
    def scope(self):
        task = next((REPO_ROOT / 'tasks/general/work').rglob(RUNTIME.escrow_state_review.TASK + '.md'))
        index = REPO_ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json'
        item = json.loads(index.read_text())['files'][task.relative_to(REPO_ROOT).as_posix()]
        source = _strip_codeblock(_parse_task_source(index.parent / item['snapshot'])[1]['Automated Checks'])
        manifest = {'identity': {'task_id': RUNTIME.escrow_state_review.TASK},
                    'digests': {'contract_sha256': 'c93e50e83a8ac8eb9d6ba9e02510a762952b4011e8495c763073029a42bfff75'},
                    'runtime': {'rule_review_profile': 'escrow-status-equivalence-review/v5'}}
        code, receipt = RUNTIME._effective_rule_source(manifest, source)
        scope = {'_GENERAL_E2E_RULE_REVIEW': RUNTIME.rule_review.worker_configuration(
            'discover', profile='escrow-status-equivalence-review/v5')}
        exec(code, scope)
        return scope, receipt

    def test_original_unknown_marker_question_keeps_candidate_text_and_original_row(self):
        scope, receipt = self.scope()
        row = {'金额影响': '收款金额1200，结算差额待确认', '_candidate_location': 'synthetic.xlsx|表|行2'}
        original = deepcopy(row)
        scope['_GE2E_ESCROW_ROWS'] = {id(row): ('待补与差异', {}, deepcopy(row))}
        self.assertFalse(scope['_ge2e_escrow_marker']('待补与差异', '金额影响', row, '待确认'))
        contexts = scope['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts), 1)
        key, context = next(iter(contexts.items()))
        self.assertEqual(context['kind'], 'escrow-unknown-marker-equivalence')
        self.assertEqual(context['original_row'], original)
        self.assertEqual(context['candidate_value'], original['金额影响'])
        self.assertEqual(context['expected_original_marker'], '待确认')
        for decision in [True, False]:
            scope['_GENERAL_E2E_RULE_REVIEW'] = RUNTIME.rule_review.worker_configuration(
                'apply', {key: decision}, profile='escrow-status-equivalence-review/v5')
            self.assertIs(scope['_ge2e_escrow_marker']('待补与差异', '金额影响', row, '待确认'), decision)
        self.assertEqual(row, original)
        self.assertFalse(receipt['numeric_decisions_assigned'])

    def test_missing_marker_decision_is_not_guessed(self):
        scope, _ = self.scope()
        row = {'金额影响': '未知文字', '_candidate_location': 'synthetic.xlsx|表|行2'}
        scope['_GE2E_ESCROW_ROWS'] = {id(row): ('待补与差异', {}, deepcopy(row))}
        scope['_GENERAL_E2E_RULE_REVIEW'] = RUNTIME.rule_review.worker_configuration('apply', profile='escrow-status-equivalence-review/v5')
        with self.assertRaisesRegex(RuntimeError, 'DECISION_MISSING'):
            scope['_ge2e_escrow_marker']('待补与差异', '金额影响', row, '不适用')

    def test_marker_boolean_is_independent_of_exactly_one_state_choice(self):
        request = {'contexts': [
            {'id': 'state-a', 'context': {'kind': 'escrow-status-equivalence', 'group_id': 'g'}},
            {'id': 'state-b', 'context': {'kind': 'escrow-status-equivalence', 'group_id': 'g'}},
            {'id': 'marker-a', 'context': {'kind': 'escrow-unknown-marker-equivalence', 'expected_original_marker': '待确认', 'original_row': {}}},
        ]}
        for marker in [True, False, None]:
            RUNTIME.escrow_state_review.validate_choices(request, {'state-a': True, 'state-b': False, 'marker-a': marker})
        with self.assertRaises(ValueError):
            RUNTIME.escrow_state_review.validate_choices(request, {'state-a': True, 'state-b': True, 'marker-a': False})


if __name__ == '__main__':
    unittest.main()
