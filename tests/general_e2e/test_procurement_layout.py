"""Exercise extraction independently from the frozen grader and its scoring math."""
import ast
import copy
from decimal import Decimal
from pathlib import Path
import re
import unittest

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT

LAYOUT = RUNTIME.dataset_rule_corrections.procurement_layout


def number(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def norm(value):
    return re.sub(r'\s+', '', str(value or '')).lower()


class ProcurementLayoutTests(unittest.TestCase):
    def fixture(self):
        records = {
            'qty': [{'id': 'a', 'values': {'oa': 10, 'ra': 12, 'da': 2}}],
            'amount': [{'id': 'a', 'values': {'oa': 10, 'ra': 12, 'da': 2}},
                       {'id': 'b', 'values': {'oa': 20, 'ra': 18, 'da': -2}}],
            'missing': [{'id': 'c', 'values': {'oa': 5}}],
            'orphan': [{'id': 'd', 'values': {'ra': 3}}],
        }
        return records, {'orders_amount': 100, 'receipts_amount': 98}, {
            'categories': {'amount': {'direction': 1}}}, {k: {r['id']: {} for r in v} for k, v in records.items()}

    def view(self, table, fixture=None):
        data = fixture or self.fixture()
        keys = {'数量差异': 'qty', '金额差异': 'amount', '未入库': 'missing',
                '无对应订单的入库': 'orphan', '数量金额一致': 'clean', '纯单价差异': 'price_only'}
        return LAYOUT._pl_matrix_view([table], *data, norm, keys.get, number)

    def table(self, rows):
        return {'kind': 'summary', 'sheet': '汇总', 'rows': [dict(row=i + 3, values=r) for i, r in enumerate(rows)]}

    def test_matrix_merged_total_and_provenance_do_not_rewrite_raw(self):
        table = self.table([['序号', '对账类别', '笔数', '采购订单金额', '入库记录金额', '金额差额'],
                            [1, '数量差异', 1, 10, 12, 2], ['合计', None, 3, 100, 98, -2]])
        before = copy.deepcopy(table)
        view, expected, locations, _ = self.view(table)
        self.assertEqual(table, before)
        self.assertEqual(expected['matrix_qty_net'], 2)
        self.assertEqual(expected['matrix_clean_net'], 0)
        self.assertEqual(expected['matrix_total_net'], -2)
        self.assertEqual(locations[('汇总', 5, '订单金额合计')]['value_location'], '汇总!D5')
        self.assertIn(['总采购订单数', 3], [r['values'] for r in view[0]['rows']])

    def test_reverse_sign_keeps_original_direction_convention(self):
        records, metrics, numeric, truth = self.fixture()
        numeric['categories']['amount']['direction'] = -1
        for kind in ['qty', 'amount']:
            for r in records[kind]:
                r['values']['da'] *= -1
        _, expected, _, _ = self.view(self.table([['对账类别', '笔数', '金额差额'], ['数量差异', 1, -2]]), (records, metrics, numeric, truth))
        self.assertEqual(expected['matrix_qty_net'], -2)
        self.assertEqual(expected['matrix_price_only_net'], 2)
        self.assertEqual(expected['matrix_total_net'], 2)

    def test_partition_projection_preserves_both_cell_locations(self):
        table = self.table([['差异类型', '笔数', '金额差额合计'], ['数量差异', 1, 2], ['纯单价差异', 1, -2]])
        view, _, locations, provenance = self.view(table)
        self.assertEqual(view[0]['rows'][-1]['values'], ['金额差异净额合计', 0])
        self.assertEqual(locations[('汇总', 3, '金额差异净额合计')]['derived_from'], ['汇总!C4', '汇总!C5'])
        self.assertFalse(provenance[-1]['candidate_statement_synthesized'])

    def test_hidden_header_and_data_stay_inaccessible(self):
        for index in [0, 1]:
            table = self.table([['对账类别', '笔数', '金额差额'], ['数量差异', 1, 2]])
            table['rows'][index]['hidden_columns'] = [2]
            view, _, _, _ = self.view(table)
            self.assertIn(1, view[0]['rows'][-1]['hidden_columns'])

    def test_upstream_missing_or_non_numeric_does_not_become_zero(self):
        data = self.fixture()
        data[0]['qty'][0]['values']['ra'] = None
        _, expected, _, _ = self.view(self.table([]), data)
        self.assertIsNone(expected['matrix_qty_receipt'])
        data = self.fixture()
        data[0]['amount'].pop()
        _, expected, _, _ = self.view(self.table([]), data)
        self.assertIsNone(expected['matrix_amount_order'])
        self.assertIsNone(expected['matrix_price_only_net'])

    def test_unknown_numeric_columns_and_duplicate_categories_fail_closed(self):
        for rows in [[['对账类别', '笔数', '额外列'], ['数量差异', 1, 123]],
                     [['对账类别', '笔数'], ['数量差异', 1], ['数量差异', 99]]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.view(self.table(rows))

    def test_literal_sumif_countifs_and_range_errors(self):
        evaluate = lambda name, args: LAYOUT._pl_conditional(name, args, number)
        self.assertEqual(evaluate('SUMIF', [['是', '否', '否'], '否', [10, 2, 3]]), 5)
        self.assertEqual(evaluate('COUNTIFS', [['是', '否', '否'], '否', [1, 1, 2], 1]), 1)
        for args in [[['否'], '否', [1, 2]], [['是'], '*', [1]], [['否'], '>0', [1]]]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                evaluate('SUMIF', args)

    def test_new_profile_is_opt_in_and_original_scoring_functions_stay_equal(self):
        tid = '02_Office_task_015_procurement_reconciliation'
        _, sections, _ = _parse_task_source(next((REPO_ROOT / 'tasks/general_e2e').rglob(tid + '.md')))
        source = _strip_codeblock(sections['Automated Checks'])
        legacy, old_receipt = RUNTIME.dataset_rule_corrections.effective_source(tid, source)
        current, receipt = RUNTIME.dataset_rule_corrections.effective_source(tid, source, procurement_layout_enabled=True)
        self.assertEqual(old_receipt['correction_id'], 'procurement-header-summary-aliases/v1')
        self.assertEqual(receipt['correction_id'], 'procurement-matrix-formulas/v2')
        def funcs(code):
            return {n.name: ast.dump(n) for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
        a, b = funcs(legacy), funcs(current)
        for name in ['grade', 'population', 'numeric_score', 'summary_key', 'direction']:
            self.assertEqual(a[name], b[name], name)
        self.assertEqual(RUNTIME.dataset_rule_corrections.effective_source(tid, source + '\n', procurement_layout_enabled=True), (source + '\n', None))


if __name__ == '__main__':
    unittest.main()
