import ast,hashlib,json
from pathlib import Path
import tempfile,unittest
import openpyxl
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from src.utils.task_parser import parse_task_md
import procurement_orphan_id_header as P

class ProcurementOrphanHeaderTests(unittest.TestCase):
    def source(self):return parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{P.TASK}.md')['automated_checks']
    def corrected(self):
        source=self.source();m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},
            'runtime':{'procurement_summary_label_profile':P.marker({'task_id':P.TASK,'automated_checks':source},P.CONTRACT)}}
        fixed,receipt=RUNTIME._effective_rule_source(m,source);return source,fixed,receipt
    def test_only_header_matching_changes_and_exact_source_is_required(self):
        source,fixed,receipt=self.corrected();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),P.SOURCE)
        manifest=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v2.json').read_text())
        row=next(t for t in manifest['tasks'] if t['task_id']==P.TASK);self.assertEqual(row['digests']['scoring_contract_sha256'],P.CONTRACT)
        a,b=ast.parse(source),ast.parse(fixed)
        left=[ast.dump(n) for n in a.body if not isinstance(n,ast.FunctionDef) or n.name!='matched_header']
        right=[ast.dump(n) for n in b.body if not isinstance(n,ast.FunctionDef) or n.name!='matched_header']
        self.assertEqual(left,right);self.assertFalse(receipt['numeric_claims_invented'])
        self.assertIsNone(P.marker({'task_id':P.TASK,'automated_checks':source+'\n'},P.CONTRACT))
    def test_combined_column_retains_original_identifiers_and_other_kinds_stay_strict(self):
        source,fixed,_=self.corrected();old,new={},{};exec(compile(source,'<original>','exec'),old);exec(compile(fixed,'<fixed>','exec'),new)
        self.assertIsNone(old['matched_header']('入库单号/订单号','orphan'))
        self.assertEqual(new['matched_header']('入库单号/订单号','orphan'),'receipt')
        self.assertIsNone(new['matched_header']('入库单号/订单号','qty'))
        self.assertIsNone(new['matched_header']('发票号/订单号','orphan'))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'candidate.xlsx';w=openpyxl.Workbook();s=w.active;s.title='无对应订单入库'
            s.append(['入库单号/订单号','入库数量','入库金额(元)']);s.append(['PO-2099-9999',2,100]);w.save(path);w.close()
            with self.assertRaises(old['EvaluationError']):old['scan_workbook'](path)
            tables,_=new['scan_workbook'](path);self.assertEqual(tables[0]['records'][0]['id'],'PO-2099-9999')
            self.assertEqual(tables[0]['records'][0]['values']['ra'],100)
