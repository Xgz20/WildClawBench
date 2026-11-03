import ast,hashlib,json,tempfile,unittest
from pathlib import Path
import openpyxl
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from src.utils.task_parser import parse_task_md
P=RUNTIME.work_order_table_roles
class WorkOrderTableRoleTests(unittest.TestCase):
    def fixed(self):
        source=parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{P.TASK}.md')['automated_checks']
        marker=P.marker({'task_id':P.TASK,'automated_checks':source},P.CONTRACT)
        m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},'runtime':{'work_order_table_role_profile':marker}}
        fixed,receipt=RUNTIME._effective_rule_source(m,source);return source,fixed,receipt
    def test_original_grading_and_calculations_stay_exact(self):
        source,fixed,r=self.fixed();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),P.SOURCE)
        catalog=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v2.json').read_text())
        self.assertEqual(next(t for t in catalog['tasks'] if t['task_id']==P.TASK)['digests']['scoring_contract_sha256'],P.CONTRACT)
        transported=source.replace("    days+= [r for r in orders if any(k in r for k in ('labor','available','nonprod'))]",'    days+= []')
        before,after=ast.parse(transported),ast.parse(fixed)
        for node in before.body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='extract':
                other=next(n for n in after.body if isinstance(n,type(node)) and n.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(other))
        self.assertFalse(r['numeric_decisions_assigned']);self.assertFalse(r['candidate_rewritten'])
    def test_available_and_allocated_columns_are_distinct_without_value_selection(self):
        source,fixed,_=self.fixed();old,new={},{};exec(compile(source,'<old>','exec'),old);exec(compile(fixed,'<new>','exec'),new)
        for available,actual in [(120,30),(10,200)]:
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'candidate.xlsx';w=openpyxl.Workbook();s=w.active;s.title='工单明细'
                s.append(['工单号','日期','产线','可分摊生产工时','分摊工时','出勤总人时','检验数合计','缺陷数合计'])
                s.append(['WO-0921-01-01','2026-09-21','D01',available,actual,130,100,2]);w.save(path);w.close()
                with self.assertRaises(old['EvaluationError']):old['extract'](path)
                orders,_,_,_=new['extract'](path);self.assertEqual(orders[0]['actual'],actual);self.assertEqual(orders[0]['available'],available)
                self.assertEqual(orders[0]['units'],100);self.assertEqual(orders[0]['defects'],2)
        mapping={0:'wo',1:'actual'}
        self.assertEqual(new['_ge2e_work_order_mapping'](['工单号','可分摊生产工时'],True,mapping),mapping)
        self.assertEqual(new['_ge2e_work_order_mapping'](['日期','可分摊生产工时'],False,mapping),mapping)
        projected=new['_ge2e_order_day_projection']({'date':'2026-09-21','dept':'D01','labor':100,'available':90,'wo':'WO-0921-01-01','actual':30,'flags':'质量超限','_loc':'source'},[],[])
        self.assertNotIn('wo',projected);self.assertNotIn('actual',projected);self.assertNotIn('flags',projected)
        self.assertTrue(new['_ge2e_work_order_event_table'](['日期','产线','事件ID','人数','非生产人时']))
        self.assertFalse(new['_ge2e_work_order_event_table'](['日期','产线','出勤总人时','可分摊生产工时']))
