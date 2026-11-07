from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT

spec = importlib.util.spec_from_file_location('new_escrow_problem_review',
    Path(RUNTIME.__file__).with_name('escrow_problem_review.py'))
REVIEW = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REVIEW)

SOURCE = """STATE_FIELDS={'问题类别','凭证状态'}
def normalized(value):return str(value).strip()
def grade(transcript: list, workspace_path: str) -> dict:
    expected={'表':[{'问题类别':'未执行','凭证状态':'齐全'},{'问题类别':'待重付','凭证状态':'缺凭证'}]}
    actual={'表':[dict(row) for row in transcript]}
    known_states={field:{normalized(row.get(field)) for rows in expected.values() for row in rows if field in row} for field in STATE_FIELDS}
    diagnostic={'review_required':[]}
    for rows in actual.values():
        for row in rows:
            for field in STATE_FIELDS.intersection(row):
                value=normalized(row[field])
                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')
    return {'rows':actual['表'],'overall_score':0.}
"""


class EscrowProblemReviewTests(unittest.TestCase):
    def code(self, profile=REVIEW.PROFILE):
        manifest = {'identity': {'task_id': RUNTIME.escrow_state_review.TASK},
                    'digests': {'contract_sha256': 'synthetic'}, 'runtime': {'rule_review_profile': profile}}
        with patch.object(RUNTIME.escrow_state_review, 'matches', return_value=True):
            return RUNTIME.escrow_grouped_review.effective_source(manifest, SOURCE, SOURCE, None)

    def discover(self, rows, profile=REVIEW.PROFILE):
        code, receipt = self.code(profile)
        scope = {'_GENERAL_E2E_RULE_REVIEW': RUNTIME.rule_review.worker_configuration('discover', profile=profile)}
        exec(code, scope)
        result = scope['grade'](rows, '.')
        return scope, result, receipt

    def test_dynamic_problem_labels_are_independent_and_fixed_fields_stay_grouped(self):
        rows = [{'问题类别': '退款未完成', '凭证状态': '凭证完整', '原因': reason,
                 '_candidate_location': 'synthetic.xlsx|表|行' + str(i)}
                for i, reason in enumerate(['未执行', '冲正后待重付'], 2)]
        original = deepcopy(rows)
        scope, result, receipt = self.discover(rows)
        contexts = scope['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts), 9)
        problem = [c for c in contexts.values() if c['field'] == '问题类别']
        fixed = [c for c in contexts.values() if c['field'] == '凭证状态']
        self.assertEqual(len({c['group_id'] for c in problem}), 2)
        self.assertTrue(all(len(c['all_occurrence_locations']) == 1 and 'original_row' in c for c in problem))
        self.assertTrue(all(len(c['all_occurrence_locations']) == 2 for c in fixed))
        self.assertEqual(result['rows'], original)
        decisions = {}
        for key, c in contexts.items():
            choice = ('待重付' if c.get('original_row', {}).get('原因') == '冲正后待重付' else '未执行') if c['field'] == '问题类别' else '齐全'
            decisions[key] = c['canonical_choice'] == choice
        scope['_GENERAL_E2E_RULE_REVIEW'] = RUNTIME.rule_review.worker_configuration('apply', decisions, profile=REVIEW.PROFILE)
        changed = scope['grade'](rows, '.')['rows']
        self.assertEqual([r['问题类别'] for r in changed], ['未执行', '待重付'])
        self.assertEqual([r['凭证状态'] for r in changed], ['齐全', '齐全'])
        self.assertEqual(rows, original)
        self.assertFalse(receipt['numeric_decisions_assigned'])

    def test_fixed_field_large_repetition_keeps_all_locations_without_expansion(self):
        rows = [{'凭证状态': '凭证完整', '_candidate_location': 'synthetic.xlsx|表|行' + str(i)}
                for i in range(11000)]
        scope, _, _ = self.discover(rows)
        contexts = scope['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts), 3)
        self.assertTrue(all(len(c['all_occurrence_locations']) == 11000 for c in contexts.values()))

    def test_problem_expansion_still_obeys_original_10000_context_limit(self):
        rows = [{'问题类别': '退款未完成', '_candidate_location': 'synthetic.xlsx|表|行' + str(i)}
                for i in range(3334)]
        code, _ = self.code()
        scope = {'_GENERAL_E2E_RULE_REVIEW': RUNTIME.rule_review.worker_configuration('discover', profile=REVIEW.PROFILE)}
        exec(code, scope)
        with self.assertRaisesRegex(RuntimeError, 'RULE_REVIEW_CONTEXT_LIMIT'):
            scope['grade'](rows, '.')
        self.assertEqual(len(scope['_GENERAL_E2E_RULE_REVIEW']['observations']), 10000)

    def test_frozen_v3_still_uses_single_group_for_same_literal(self):
        rows = [{'问题类别': '退款未完成', '原因': reason, '_candidate_location': 'synthetic.xlsx|表|行' + str(i)}
                for i, reason in enumerate(['未执行', '冲正后待重付'], 2)]
        scope, _, _ = self.discover(rows, RUNTIME.escrow_grouped_review.PROFILE)
        contexts = scope['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts), 3)
        self.assertTrue(all('original_row' not in c and len(c['all_occurrence_locations']) == 2 for c in contexts.values()))


if __name__ == '__main__':
    unittest.main()
