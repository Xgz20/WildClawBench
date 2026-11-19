"""Explicit additive summaries retain both original numeric obligations."""
import csv
import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

ROOT = Path(__file__).resolve().parents[2]
TASK = '02_Office_task_015_procurement_reconciliation'


class UnmatchedGrossTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'input').mkdir()
        for name, headers, rows in [
            ('采购订单.csv', ['ORDER_ID', 'ORDER_QTY', 'TOTAL_AMOUNT', 'STATUS'],
             [['A', 10, 100, '已完成'], ['B', 20, 200, '已完成'], ['C', 30, 300, '待确认']]),
            ('入库记录.csv', ['RECEIPT_NO', 'RECV_QTY', 'RECV_AMOUNT'],
             [['A-01', 9, 90], ['D-01', 5, 50]]),
        ]:
            with (self.root / 'input' / name).open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                writer.writerows(rows)
        _, sections, _ = _parse_task_source(ROOT / 'tasks/general/work/02_Office' / (TASK + '.md'))
        self.scope = {}
        exec(_strip_codeblock(sections['Automated Checks']), self.scope)
        self.scope['_PS_ROOT'] = self.root
        self.records = {
            'qty': [{'id': 'A', 'values': {'oq': 10, 'rq': 9, 'dq': -1, 'oa': 100, 'ra': 90, 'da': -10}}],
            'amount': [{'id': 'A', 'values': {'oq': 10, 'rq': 9, 'dq': -1, 'oa': 100, 'ra': 90, 'da': -10}}],
            'missing': [{'id': 'B', 'values': {'oq': 20, 'oa': 200}},
                        {'id': 'C', 'values': {'oq': 30, 'oa': 300}}],
            'orphan': [{'id': 'D-01', 'values': {'rq': 5, 'ra': 50}}],
        }
        self.truth = {k: {r['id']: None for r in rows} for k, rows in self.records.items()}
        self.metrics = {k: Decimal(v) for k, v in {
            'orders': '3', 'receipts': '2', 'orders_amount': '600', 'receipts_amount': '140',
        }.items()}
        self.numeric = {'categories': {k: {'direction': 1} for k in ['qty', 'amount']}}
        self.header = {'row': 3, 'values': ['类别', '笔数', '金额差额/金额合计(元)', '核对口径（对应明细表）']}
        self.row = {'row': 8, 'values': ['两类未匹配金额合计', 3, 550,
                                      '未入库订单金额合计 + 无对应订单入库金额合计']}

    def evaluate(self):
        table = {'sheet': '汇总', 'kind': 'summary', 'rows': [self.header, self.row]}
        return self.scope['summary_diagnostics']([table], self.records, self.metrics, self.numeric, self.truth)

    def claims(self, result):
        return {c['value_location']: c for c in result['claims']}

    def test_explicit_sum_keeps_count_money_and_original_locations(self):
        result = self.evaluate()
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        claims = self.claims(result)
        self.assertEqual(set(claims), {'汇总!B8', '汇总!C8'})
        self.assertEqual([claims[p]['expected'] for p in ['汇总!B8', '汇总!C8']], ['3', '550'])
        self.assertTrue(all(c['matches'] for c in claims.values()))
        self.assertEqual(result['groups']['money']['evaluated_units'], 4)

    def test_incorrect_count_and_money_remain_separate_failures(self):
        self.row['values'][1] = 2
        claims = self.claims(self.evaluate())
        self.assertFalse(claims['汇总!B8']['matches'])
        self.assertTrue(claims['汇总!C8']['matches'])
        self.row['values'][1:] = [3, 450, self.row['values'][3]]
        claims = self.claims(self.evaluate())
        self.assertTrue(claims['汇总!B8']['matches'])
        self.assertFalse(claims['汇总!C8']['matches'])

    def test_sum_does_not_inherit_signed_difference_direction(self):
        self.numeric['categories']['amount']['direction'] = -1
        self.assertEqual(self.claims(self.evaluate())['汇总!C8']['expected'], '550')

    def test_hidden_money_header_remains_inaccessible(self):
        self.header['hidden_columns'] = [2]
        claims = self.claims(self.evaluate())
        self.assertTrue(claims['汇总!B8']['matches'])
        self.assertFalse(claims['汇总!C8']['matches'])

    def test_incomplete_upstream_population_does_not_fill_money_from_reference(self):
        self.records['missing'].pop()
        claim = self.claims(self.evaluate())['汇总!C8']
        self.assertIsNone(claim['expected'])
        self.assertIsNone(claim['matches'])

    def test_unknown_net_or_unlabelled_expression_still_requires_review(self):
        for label, note in [
            ('两类未匹配金额合计', '未入库订单金额合计 - 无对应订单入库金额合计'),
            ('两类未匹配金额合计', '见明细'),
            ('未知汇总', '未入库订单金额合计 + 无对应订单入库金额合计'),
        ]:
            with self.subTest(label=label, note=note):
                self.row['values'][0] = label
                self.row['values'][3] = note
                result = self.evaluate()
                self.assertEqual(result['unrecognized_numeric_rows'], [{'sheet': '汇总', **self.row}])
                self.assertEqual(result['claims'], [])

    def test_unknown_numeric_column_is_not_discarded(self):
        self.row['values'].append(123)
        self.assertEqual(self.evaluate()['unrecognized_numeric_rows'], [{'sheet': '汇总', **self.row}])

    def test_ambiguous_count_headers_do_not_create_claims(self):
        self.header['values'].insert(2, '笔数')
        self.row['values'].insert(2, 3)
        self.assertEqual(self.evaluate()['unrecognized_numeric_rows'], [{'sheet': '汇总', **self.row}])

    def test_mixed_header_keeps_every_declared_count_and_money_column(self):
        rows = [self.header]
        for index, (label, count, amount, note) in enumerate([
            ('数量差异', 1, -10, '对应「数量差异」表，金额差额(订单-入库)列合计'),
            ('金额差异', 1, -10, '对应「金额差异」表，金额差额(订单-入库)列合计'),
            ('未入库订单', 2, 500, '对应「未入库订单」表，订单金额列合计'),
            ('无对应订单的入库记录', 1, 50, '对应「无对应订单入库记录」表，入库金额列合计'),
        ], 4):
            rows.append({'row': index, 'values': [label, count, amount, note]})
        rows.append(self.row)
        result = self.scope['summary_diagnostics'](
            [{'sheet': '汇总', 'kind': 'summary', 'rows': rows}],
            self.records, self.metrics, self.numeric, self.truth)
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        self.assertEqual(len(result['claims']), 10)
        self.assertEqual({c['value_location'] for c in result['claims']},
                         {'汇总!' + col + str(row) for col in 'BC' for row in range(4, 9)})
        self.assertTrue(all(c['matches'] for c in result['claims']))
        self.assertEqual(result['groups']['money']['missing_required'], [])
        self.assertEqual(result['groups']['money']['evaluated_units'], 5)

    def test_reported_difference_is_checked_against_submitted_column(self):
        self.header['values'] = ['类别', '笔数', '金额差额/金额合计(元)', '核对口径（对应明细表）']
        self.row['values'] = ['金额差异', 1, -9, '对应「金额差异」表，金额差额(订单-入库)列合计']
        self.records['amount'][0]['values']['da'] = -9
        # Numeric correctness is a separate original rule obligation. A matching
        # subtotal is compared with the submitted column, without a second charge.
        self.assertTrue(self.claims(self.evaluate())['汇总!C8']['matches'])

    def current_priority_scope(self):
        from src.wildclawbench_grading_core import source_repairs
        digest = '7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b'
        task = ROOT / 'tasks/general/work/02_Office' / (TASK + '.md')
        index = ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json'
        row = json.loads(index.read_text())['files'][task.relative_to(ROOT).as_posix()]
        _, sections, _ = _parse_task_source(index.parent / row['snapshot'])
        original = _strip_codeblock(sections['Automated Checks'])
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), digest)
        historical, _ = source_repairs.effective_source(
            TASK, original, profile='procurement-date-and-section-extraction/v4')
        self.assertEqual(hashlib.sha256(historical.encode()).hexdigest(),
                         '5dbc6a6431a8dd4c4692e28fbe52051d7599a4038ab5aae347712e6ff4f4d561')
        current, receipt = source_repairs.effective_source(TASK, original)
        self.assertEqual(receipt['correction_id'], 'procurement-date-and-section-extraction/v6')
        funcs = lambda code: {n.name: ast.dump(n) for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
        previous, changed = funcs(historical), funcs(current)
        for name in ['grade', 'population', 'numeric_score', 'summary_key', 'direction']:
            self.assertEqual(previous[name], changed[name], name)
        self.scope = {}
        exec(current, self.scope)
        self.scope['_PS_ROOT'] = self.root

    def priority_table(self, label='高'):
        return {'sheet': '数量差异', 'kind': 'qty', 'header_row': 1,
                'rows': [{'row': 1, 'values': ['单号', '优先级']},
                         {'row': 2, 'values': ['A', label]}],
                'records': [{'id': 'A', 'row': 2}]}

    def test_custom_priority_text_does_not_invent_p1_membership(self):
        self.current_priority_scope()
        detail = self.priority_table()
        summary = {'sheet': '汇总', 'kind': 'summary', 'rows': [
            {'row': 1, 'values': ['项目', 'P1', 'P2', 'P3', '跟踪']},
            {'row': 2, 'values': ['数量差异', 0, 0, 0, 0]}]}
        result = self.scope['summary_diagnostics'](
            [detail, summary], self.records, self.metrics, self.numeric, self.truth)
        self.assertEqual(result['unrecognized_numeric_rows'], [])
        self.assertEqual(len(result['claims']), 4)
        self.assertTrue(all(c['expected'] == '0' and c['matches'] for c in result['claims']))
        self.assertEqual(detail['rows'][1]['values'][1], '高')
        detail['rows'][1]['values'][1] = 'P1'
        result = self.scope['summary_diagnostics'](
            [detail, summary], self.records, self.metrics, self.numeric, self.truth)
        self.assertEqual(result['claims'][0]['expected'], '1')
        self.assertFalse(result['claims'][0]['matches'])

    def test_custom_priority_keeps_unknown_numeric_claims_for_review(self):
        self.current_priority_scope()
        row = {'row': 3, 'values': ['未知总额', 666]}
        result = self.scope['summary_diagnostics'](
            [self.priority_table(), {'sheet': '汇总', 'kind': 'summary', 'rows': [row]}],
            self.records, self.metrics, self.numeric, self.truth)
        self.assertEqual(result['unrecognized_numeric_rows'], [{'sheet': '汇总', **row}])
        self.assertEqual(result['claims'], [])

    def test_custom_priority_does_not_resolve_duplicate_priority_columns(self):
        self.current_priority_scope()
        detail = self.priority_table()
        detail['rows'][0]['values'].append('复核优先级')
        detail['rows'][1]['values'].append('P1')
        with self.assertRaisesRegex(self.scope['EvaluationError'], 'Ambiguous priority columns'):
            self.scope['summary_diagnostics'](
                [detail], self.records, self.metrics, self.numeric, self.truth)


if __name__ == '__main__':
    unittest.main()
