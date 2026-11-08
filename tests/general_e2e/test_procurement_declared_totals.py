"""Explicit declarations retain source values, units and evidence boundaries."""
from copy import deepcopy
import unittest

from tests.general_e2e import test_procurement_unmatched_gross as fixtures


class DeclaredTotalsTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.UnmatchedGrossTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.current_priority_scope()

    def evaluate(self, rows):
        f = self.fx
        table = {'sheet': '汇总', 'kind': 'summary', 'rows': rows}
        original = deepcopy(table)
        result = f.scope['summary_diagnostics']([table], f.records, f.metrics, f.numeric, f.truth)
        self.assertEqual(table, original)
        return result

    def source_rows(self):
        return [
            {'row': 5, 'values': ['项目', '笔数', '数量', '金额（元）', '备注']},
            {'row': 6, 'values': ['采购订单（源表）', 3, 60, 600, 'source orders']},
            {'row': 7, 'values': ['入库记录（源表）', 2, 14, 140, 'source receipts']},
            {'row': 9, 'values': ['其中：已匹配入库', 1, 9, 90, 'receipt side']},
            {'row': 10, 'values': ['差额合计（入库-订单）', '—', -46, -460, 'direction explicit']},
        ]

    def reconcile_rows(self):
        labels = ['① 已匹配金额差额（金额差异表净差额）', '② 加：无对应订单入库金额',
                  '③ 减：未入库订单金额（取绝对值）', '④ 明细推算总差额 ＝①＋②－③',
                  '⑤ 源表总差额 ＝ 入库总额－订单总额', '⑥ 校验差异 ＝⑤－④（应为 0.00）',
                  '⑦ 数量勾稽：已匹配两侧数量差（应为 0）']
        return [{'row': 35, 'values': ['勾稽项', None, None, '数值', '校验说明']}] + [
            {'row': 36+i, 'values': [label, None, None, value, 'declared relation']}
            for i, (label, value) in enumerate(zip(labels, [-10, 50, 500, -460, -460, 0, -1]))]

    def test_source_totals_keep_each_column_and_receipt_side(self):
        result = self.evaluate(self.source_rows())
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        self.assertEqual(len(result['claims']), 11)
        self.assertTrue(all(c['matches'] for c in result['claims']))
        claims = {c['value_location']: c for c in result['claims']}
        self.assertEqual(claims['汇总!C9']['expected'], '9')
        self.assertEqual(claims['汇总!D9']['expected'], '90')

    def test_known_relations_compute_nonzero_differences_and_reject_wrong_zero(self):
        rows = self.reconcile_rows()
        result = self.evaluate(rows)
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        self.assertEqual(len(result['claims']), 7)
        self.assertTrue(all(c['matches'] for c in result['claims']))
        rows[-1]['values'][3] = 0
        result = self.evaluate(rows)
        claim = next(c for c in result['claims'] if c['value_location'] == '汇总!D42')
        self.assertEqual(claim['expected'], '-1')
        self.assertFalse(claim['matches'])

    def test_incomplete_details_do_not_turn_reconciliation_into_zero(self):
        self.fx.records['missing'].pop()
        result = self.evaluate(self.reconcile_rows())
        claims = {c['value_location']: c for c in result['claims']}
        for location in ['汇总!D38', '汇总!D39', '汇总!D41', '汇总!D42']:
            self.assertIsNone(claims[location]['expected'])
            self.assertIsNone(claims[location]['matches'])

    def test_hidden_headers_and_unknown_numeric_columns_still_fail_closed(self):
        rows = self.source_rows()
        rows[0]['hidden_columns'] = [2]
        claims = self.evaluate(rows)['claims']
        self.assertTrue(all(not c['matches'] for c in claims if c['value_location'].startswith('汇总!C')))
        rows = self.source_rows()
        rows[1]['values'].append(123)
        result = self.evaluate(rows)
        self.assertIn({'sheet': '汇总', **rows[1]}, result['unrecognized_numeric_rows'])

    def test_cause_total_needs_both_explicit_partition_rows(self):
        rows = [{'row': 20, 'values': ['成因', '笔数', '金额差额（元）', '说明']},
                {'row': 21, 'values': ['数量差异导致（单价一致）', 1, -10, 'qty']},
                {'row': 22, 'values': ['单价差异导致（数量一致）', 0, 0, 'price']},
                {'row': 23, 'values': ['合计', 1, -10, 'amount partition']}]
        result = self.evaluate(rows)
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        self.assertEqual(len(result['claims']), 6)
        self.assertTrue(all(c['matches'] for c in result['claims']))
        result = self.evaluate([rows[0], rows[1], rows[3]])
        self.assertIn({'sheet': '汇总', **rows[3]}, result['unrecognized_numeric_rows'])


if __name__ == '__main__':
    unittest.main()
