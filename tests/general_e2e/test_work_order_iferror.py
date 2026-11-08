"""Supported IFERROR values follow Excel; evaluator gaps are never swallowed.

Definition: https://support.microsoft.com/en-us/excel/functions/iferror-function
"""
import ast
import hashlib
from pathlib import Path
import tempfile
import unittest

import openpyxl

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import effective_source

ROOT = Path(__file__).resolve().parents[2]
TASK = '02_Office_task_026_work_order_labor_reconciliation'


class WorkOrderIferrorTests(unittest.TestCase):
    def setUp(self):
        source = ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/tasks' / (TASK+'.md')
        _, sections, _ = _parse_task_source(source)
        self.original = _strip_codeblock(sections['Automated Checks'])
        self.current, self.receipt = effective_source(TASK, self.original)
        self.scope = {}
        exec(self.current, self.scope)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'formula-fixture.xlsx'
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = 'Values'
        values = {
            'A1': 0, 'B1': '#DIV/0!', 'C1': '=1/0',
            'D1': '=IFERROR(C1,9)', 'D2': '=IFERROR(B1,8)',
            'E1': '=IFERROR(A2,7)', 'E2': '=IFERROR(A1,7)',
            'E3': '=IFERROR(2,UNSUPPORTED(1))', 'E4': '=IFERROR(UNSUPPORTED(1),0)',
            'E5': '=IFERROR(1/0,IFERROR(2/0,"kept"))',
            'E6': '=IFERROR("text"+1,3)', 'E7': '=IFERROR(#N/A,"found")',
            'E8': '=IFERROR(1/0,#N/A)', 'E9': '=IFERROR(E8,"again")',
            'E10': '=IFERROR(E10,0)', 'E11': '=IFERROR(1)',
            'E12': '=IFERROR(A2+1,7)', 'E13': '=IFERROR(IF(A1=0,4,UNSUPPORTED(1)),0)',
        }
        for cell, value in values.items():
            sheet[cell] = value
        workbook.save(path)
        workbook.close()
        self.reader = self.scope['Reader'](path)
        self.addCleanup(self.reader.wb.close)
        self.addCleanup(self.reader.form.close)

    def value(self, cell):
        return self.reader.value('Values', cell)

    def test_success_zero_blank_and_lazy_fallback(self):
        self.assertEqual(self.value('E1'), '')
        self.assertEqual(self.value('E2'), 0)
        self.assertEqual(self.value('E3'), 2)
        self.assertEqual(self.value('E12'), 1)
        self.assertEqual(self.value('E13'), 4)

    def test_cached_and_uncached_errors_remain_errors_when_referenced_later(self):
        self.assertIsNone(self.value('B1'))
        self.assertIsNone(self.value('C1'))
        self.assertEqual(self.value('D1'), 9)
        self.assertEqual(self.value('D2'), 8)
        self.assertIsNone(self.value('E8'))
        self.assertEqual(self.value('E9'), 'again')

    def test_supported_excel_errors_and_nested_fallback(self):
        self.assertEqual(self.value('E5'), 'kept')
        self.assertEqual(self.value('E6'), 3)
        self.assertEqual(self.value('E7'), 'found')

    def test_unsupported_expression_and_cycles_are_not_hidden(self):
        with self.assertRaisesRegex(self.scope['EvaluationError'], 'UNSUPPORTED'):
            self.value('E4')
        self.assertEqual(self.reader._iferror_depth, 0)
        with self.assertRaisesRegex(self.scope['CandidateInvalid'], 'Circular'):
            self.value('E10')
        with self.assertRaisesRegex(self.scope['EvaluationError'], 'two arguments'):
            self.value('E11')
        with self.assertRaisesRegex(self.scope['EvaluationError'], 'external'):
            self.reader.formula('=IFERROR(\'[outside.xlsx]Elsewhere\'!A1,0)', 'Values')

    def test_exact_source_and_original_scoring_algorithm_stay_bound(self):
        self.assertEqual(self.receipt['correction_id'], 'work-order-lazy-iferror-reader/v1')
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(),
                         '0df6363a8bb5cc0f1f27fc30e6c62f02a84212e67cc43351eee5767ec6dc87c7')
        functions = lambda source: {n.name: ast.dump(n) for n in ast.parse(source).body
                                    if isinstance(n, ast.FunctionDef)}
        before, after = functions(self.original), functions(self.current)
        self.assertEqual(before, after)
        self.assertEqual(effective_source('other', self.original), (self.original, None))
        self.assertEqual(effective_source(TASK, self.original+'\n'), (self.original+'\n', None))


if __name__ == '__main__':
    unittest.main()
