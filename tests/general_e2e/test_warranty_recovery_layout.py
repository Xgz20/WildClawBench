from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import tempfile
import unittest

import openpyxl

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

LAYOUT = RUNTIME.warranty_recovery_layout


class WarrantyRecoveryLayoutTests(unittest.TestCase):
    def source(self):
        _, sections, _ = _parse_task_source(next((REPO_ROOT / 'tasks/general_e2e').rglob(LAYOUT.TASK + '.md')))
        return _strip_codeblock(sections['Automated Checks'])

    def corrected(self):
        source = self.source()
        marker = LAYOUT.marker({'task_id': LAYOUT.TASK, 'automated_checks': source}, LAYOUT.CONTRACT_SHA, LAYOUT.DATASET)
        self.assertIsNotNone(marker)
        manifest = {'identity': {'task_id': LAYOUT.TASK}, 'digests': {'contract_sha256': LAYOUT.CONTRACT_SHA},
                    'dataset': LAYOUT.DATASET, 'runtime': {'warranty_recovery_layout_profile': marker}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, source)
        return source, fixed, receipt, manifest

    def test_exact_frozen_profile_and_unchanged_business_grading(self):
        source, fixed, receipt, manifest = self.corrected()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), LAYOUT.SOURCE_SHA)
        before, after = ast.parse(source), ast.parse(fixed)
        for name in ('grade', 'number', 'close', 'pair', 'reason_class'):
            left = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == name)
            right = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertEqual(ast.dump(left), ast.dump(right))
        self.assertFalse(receipt['candidate_rewritten'])
        self.assertFalse(receipt['numeric_decisions_assigned'])
        self.assertEqual(RUNTIME._effective_rule_source({}, source), (source, None))
        bad = deepcopy(manifest)
        bad['dataset']['digest'] = '0' * 64
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'WARRANTY_LAYOUT_PROFILE_MISMATCH'):
            RUNTIME._effective_rule_source(bad, source)

    def test_real_equivalent_headers_and_allocated_cost_precedence(self):
        source, fixed, _, _ = self.corrected()
        old, new = {}, {}
        exec(compile(source, '<original-warranty-rule>', 'exec'), old)
        exec(compile(fixed, '<repaired-warranty-rule>', 'exec'), new)
        for header, key in [('本次金额(元)', 'current'), ('政策责任比例', 'ratio'),
                            ('已追偿', 'already'), ('分摊及合同依据说明', 'note')]:
            self.assertIsNone(old['header_key'](header))
            self.assertEqual(new['header_key'](header), key)
        for header in ('金额', '责任', '预计本次金额', '本次金额(美元)', '申报供应商'):
            self.assertEqual(new['header_key'](header), old['header_key'](header))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'candidate.xlsx'
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = '可追偿明细'
            sheet.append(['索赔单号', '供应商', '维修成本(元)', '分摊维修成本(元)', '政策责任比例', '本次金额(元)'])
            sheet.append(['SYNTHETIC', '测试供应商', 1000, 400, .5, 200])
            workbook.save(path)
            workbook.close()
            original, _ = old['read_tables'](path)
            actual, _ = new['read_tables'](path)
            self.assertEqual(original['detail'], [])
            self.assertEqual(actual['detail'][0]['cost'], 400)
            self.assertEqual(actual['detail'][0]['current'], 200)
            self.assertEqual(actual['detail'][0]['ratio'], .5)


if __name__ == '__main__':
    unittest.main()
