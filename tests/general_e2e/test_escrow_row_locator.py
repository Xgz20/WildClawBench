from pathlib import Path
import ast
import unittest
from eval_general_e2e.datasets.source_history import dataset_task_path
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

ROOT = Path(__file__).resolve().parents[2]
TASK = '03_Data_Analysis_task_010_contract_escrow_refund_reconciliation'


def codes():
    path = next((ROOT / 'tasks/general/work').rglob(TASK + '.md'))
    index = ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json'
    old = dataset_task_path(ROOT, path.relative_to(ROOT).as_posix(), index.relative_to(ROOT).as_posix())
    return [_strip_codeblock(_parse_task_source(p)[1]['Automated Checks']) for p in [old, path]]


class EscrowRowLocatorTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = {}, {}
        a, b = codes()
        exec(a, self.old)
        exec(b, self.new)

    def test_equivalent_chinese_positive_row_preserves_file_sheet_and_number(self):
        value = '内部收款与核销.xlsx|分配_TG01_合同|第100行'
        with self.assertRaises(ValueError): self.old['locations'](value)
        expected = self.old['locations'](value.replace('第100行', '行100'))
        self.assertEqual(self.new['locations'](value), expected)
        self.assertEqual(expected, {('内部收款与核销.xlsx', '分配_TG01_合同', 100)})

    def test_original_rows_cells_ranges_and_index_references_keep_original_results(self):
        for value in ['a.xlsx|Sheet|R12', 'a.xlsx|Sheet|行12', 'a.xlsx!Sheet!$B$12:$B$14',
                      'a.xlsx|Sheet|12', 'a.xlsx|Sheet|第12行;a.xlsx|Sheet|第13行']:
            canonical = value.replace('第12行', '行12').replace('第13行', '行13')
            self.assertEqual(self.new['locations'](value), self.old['locations'](canonical))

    def test_unknown_or_nonpositive_chinese_rows_are_not_approximated(self):
        for value in ['第0行', '第-1行', '第1.5行', '第100行备注', '第一百行']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.new['locations']('a.xlsx|Sheet|' + value)

    def test_unknown_file_and_sheet_are_retained_for_original_existence_checks(self):
        self.assertEqual(self.new['locations']('wrong.xlsx|wrongSheet|第7行'), {('wrong.xlsx', 'wrongSheet', 7)})

    def test_all_other_rule_functions_and_grading_weights_are_unchanged(self):
        a, b = [ast.parse(s) for s in codes()]
        functions = lambda module: {n.name: ast.dump(n) for n in module.body if isinstance(n, ast.FunctionDef) and n.name != 'locations'}
        self.assertEqual(functions(a), functions(b))
        self.assertEqual(self.old['WEIGHTS'], self.new['WEIGHTS'])


if __name__ == '__main__':
    unittest.main()
