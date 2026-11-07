from copy import deepcopy
import importlib.util
from pathlib import Path
import textwrap
import unittest
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

spec = importlib.util.spec_from_file_location('_escrow_frontier_tests', Path(RUNTIME.__file__).with_name('escrow_frontier_review.py'))
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class EscrowFrontierTests(unittest.TestCase):
    def collect(self, actual, expected, mode='discover'):
        calls = []
        scope = {'_GENERAL_E2E_RULE_REVIEW': {'mode': mode}, 'actual': actual, 'expected': expected,
                 'STATE_FIELDS': {'问题类别'}, 'TEXT_EXCLUDE': {'来源'},
                 'normalized': lambda v: str(v or '').strip(),
                 'number': lambda v: float(v) if isinstance(v, (int, float)) else None,
                 '_ge2e_escrow_marker': lambda table, field, row, want: calls.append((table, field, deepcopy(row), want))}
        exec(textwrap.dedent(MODULE.FRONTIER), scope)
        return calls

    def test_same_original_object_collects_marker_before_state_key_can_match(self):
        row = {'对象类型': '收款', '业务编号': 'SK2', '问题类别': '收款缺结算引用',
               '金额影响': '收款金额900，结算差额待确认'}
        ref = {'对象类型': '收款', '业务编号': 'SK2', '问题类别': '缺结算引用', '金额影响': '待确认'}
        original = deepcopy(row)
        calls = self.collect({'待补与差异': [row]}, {'待补与差异': [ref]})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ('待补与差异', '金额影响', original, '待确认'))
        self.assertEqual(row, original)

    def test_other_business_object_and_identity_fields_do_not_add_questions(self):
        row = {'对象类型': '收款', '业务编号': 'SK2', '金额影响': '混合说明'}
        expected = {'待补与差异': [
            {'对象类型': '收款', '业务编号': 'SK3', '金额影响': '待确认'},
            {'对象类型': '收款', '业务编号': 'SK2', '合同号': '待确认'},
        ]}
        self.assertEqual(self.collect({'待补与差异': [row]}, expected), [])

    def test_existing_numeric_or_explicit_marker_is_not_reclassified(self):
        ref = {'待补与差异': [{'对象类型': '收款', '业务编号': 'SK2', '金额影响': '待确认'}]}
        for value in [None, '', '待确认', '不适用', 900]:
            row = {'对象类型': '收款', '业务编号': 'SK2', '金额影响': value}
            self.assertEqual(self.collect({'待补与差异': [row]}, ref), [])

    def test_duplicate_reference_paths_are_deduplicated_and_apply_is_not_prejudged(self):
        row = {'对象类型': '收款', '业务编号': 'SK2', '金额影响': '混合说明'}
        ref = {'对象类型': '收款', '业务编号': 'SK2', '金额影响': '待确认'}
        actual, expected = {'待补与差异': [row]}, {'待补与差异': [ref, deepcopy(ref)]}
        self.assertEqual(len(self.collect(actual, expected)), 1)
        self.assertEqual(self.collect(actual, expected, mode='apply'), [])


if __name__ == '__main__':
    unittest.main()
