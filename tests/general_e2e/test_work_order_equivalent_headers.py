import ast
from copy import deepcopy
from pathlib import Path
import hashlib,json,tempfile,unittest
from types import SimpleNamespace
import openpyxl
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

P=RUNTIME.work_order_equivalent_headers

class WorkOrderEquivalentHeaderTests(unittest.TestCase):
    def setUp(self):
        path=REPO_ROOT/'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/tasks'/(P.TASK+'.md')
        self.source=_strip_codeblock(_parse_task_source(path)[1]['Automated Checks'])
        self.contract={'task_id':P.TASK,'automated_checks':self.source}
        self.m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},'dataset':P.DATASET,
                'runtime':{'shared_rule_source_repair':RUNTIME.shared_source_repairs.marker(self.contract)}}
        self.base,self.prior=RUNTIME._effective_rule_source(self.m,self.source)
        self.m['runtime']['work_order_equivalent_header_profile']=P.marker(self.contract,P.CONTRACT,P.DATASET)

    def scope(self):
        code,receipt=P.effective_source(self.m,self.source,self.base,self.prior)
        scope={};exec(code,scope);return scope,code,receipt

    def workbook(self,path,*,duplicate=False):
        w=openpyxl.Workbook();s=w.active;s.title='工单核对准表'
        s.append(['工单号','日期','产线','可分摊生产工时','分摊生产工时','排期偏差异常','缺陷率异常','核对状态','问题/备注'])
        s.append(['WO-0921-01-01','2026-09-21','D01',100,23.04,'是','否','正常','保留原说明'])
        s.append(['WO-0921-01-02','2026-09-21','D01',100,0,'否','是','待确认','零基数仍填0'])
        if duplicate:s['J1']='分摊工时';s['J2']=99;s['J3']=0
        s=w.create_sheet('产线日汇总');s.append(['日期','产线','出勤工时','非生产工时','加班占比异常','分摊状态','问题/备注'])
        s.append(['2026-09-21','D01',120,20,'是','可分摊','当日标准工作量合计为零，不平均摊入工单'])
        w.save(path);w.close()

    def test_explicit_values_flags_and_real_zero_are_read_without_changing_original(self):
        scope,_,_=self.scope()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.xlsx';self.workbook(path);before=path.read_bytes()
            orders,days,texts,_=scope['extract'](path)
            self.assertEqual([r['actual'] for r in orders],[23.04,0])
            self.assertEqual([r['available'] for r in orders],[100,100])
            self.assertEqual(orders[0]['flags'],'排期偏差异常')
            self.assertIn('缺陷率异常',orders[1]['flags']);self.assertIn('待确认',orders[1]['flags'])
            self.assertEqual(orders[0]['notes'],'保留原说明')
            self.assertEqual(path.read_bytes(),before)
            literals=[json.loads(t['text']) for t in texts if t['text'].startswith('{') and 'candidate_literal_status' in t['text']]
            self.assertIn('可分摊',[r['value'] for r in literals]);self.assertIn('正常',[r['value'] for r in literals])
            self.assertFalse(any('可分摊' in str(r.get('flags','')) for r in days))

    def test_conflicting_actual_columns_are_not_selected_by_value_or_score(self):
        scope,_,_=self.scope()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.xlsx';self.workbook(path,duplicate=True)
            with self.assertRaisesRegex(scope['EvaluationError'],'Ambiguous duplicate field actual'):scope['extract'](path)

    def test_numeric_functions_weights_thresholds_and_original_marker_absence_stay_identical(self):
        _,code,receipt=self.scope()
        functions=lambda c:{n.name:ast.dump(n) for n in ast.parse(c).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        old,new=functions(self.base),functions(code)
        for name in ['grade','Reader','marked','flags_expected','merge_records','close','mean','number']:
            self.assertEqual(old[name],new[name])
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['rubric_and_weights_changed'])
        oldm=deepcopy(self.m);oldm['runtime'].pop('work_order_equivalent_header_profile')
        self.assertEqual(P.effective_source(oldm,self.source,self.base,self.prior),(self.base,self.prior))
        self.assertIsNone(P.marker(self.contract,'0'*64,P.DATASET))
        self.assertIsNone(P.marker(self.contract,P.CONTRACT,{**P.DATASET,'digest':'0'*64}))
        with self.assertRaises(ValueError):P.effective_source(self.m,self.source,self.base+'\n',self.prior)

    def fixture(self,folder):
        root=Path(folder);base=root/'candidate-original/workspace/results';base.mkdir(parents=True)
        path=base/'synthetic.xlsx';w=openpyxl.Workbook();s=w.active;s.title='工单核对准表'
        for cell,value in {'O1':'分摊生产工时','O44':1.5,'Q1':'排期偏差异常','Q44':'是','W1':'问题/备注'}.items():s[cell]=value
        w.save(path);w.close()
        write=lambda name,value:(root/name).write_text(json.dumps(value,ensure_ascii=False))
        (root/'worker').mkdir();(root/'grader-evidence/files').mkdir(parents=True)
        m=deepcopy(self.m);m['runtime'].pop('work_order_equivalent_header_profile');m['identity'].update(scoring_attempt_id='synthetic-001',execution_attempt_id='execution-001')
        m['paths']={'candidate_original':'candidate-original/workspace'}
        write('worker/request.json',{'automated_checks':self.base});write('worker/result.json',{'ok':True})
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        write('rule-audit.json',{'status':'completed','identity':m['identity'],'worker':{'return_code':0,
              'request_sha256':sha(root/'worker/request.json'),'process_tree_cleanup':{'remaining':False}}})
        write('rule-component.json',{})
        write('scoring-evaluation-issue.json',{'schema_version':'general-e2e-judge-evaluation-issue/v1',
            'status':'NEEDS_ATTENTION','identity':m['identity'],'origin':'evaluator',
            'score_published':False,'rule_rerun':False,'candidate_modified':False})
        exported={'wo':'WO-0922-03-01','candidate':{'actual':None}}
        observed={'role':'judge_readonly_observation_not_score','candidate_sha256':sha(path),
                  'candidate_cells':{'工单核对准表!O1':'分摊生产工时','工单核对准表!O44':1.5,
                    '工单核对准表!Q1':'排期偏差异常','工单核对准表!Q44':'是','工单核对准表!W1':'问题/备注'},
                  'exported_case':exported}
        write('judge-readonly-observations.json',observed);write('grader-evidence/files/critical_1.json',[exported])
        rt=SimpleNamespace(_read_json=lambda p:json.loads(Path(p).read_text()),_sha256_file=sha)
        task={'thread':{'status':'COMPLETED'},'score':None}
        return root,m,rt,task,write

    def test_original_completed_failure_is_bound_to_actual_cells_and_frozen_critical_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root,m,rt,task,_=self.fixture(folder)
            proof=P.validate_blocker(rt,root,m,self.contract,task)
            self.assertTrue(proof['old_actual_missing']);self.assertFalse(proof['numeric_score_assigned'])

    def test_failure_rejects_active_score_source_drift_and_changed_cell_or_critical_snapshot(self):
        for field in ['active','score','source','cell','snapshot']:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
                root,m,rt,task,write=self.fixture(folder)
                if field=='active':task['thread']['status']='RUNNING'
                elif field=='score':write('score.json',{})
                elif field=='source':write('worker/request.json',{'automated_checks':self.base+'\n'})
                elif field=='cell':
                    v=rt._read_json(root/'judge-readonly-observations.json');v['candidate_cells']['工单核对准表!O44']=99;write('judge-readonly-observations.json',v)
                else:write('grader-evidence/files/critical_1.json',[])
                with self.assertRaises(ValueError):P.validate_blocker(rt,root,m,self.contract,task)


if __name__=='__main__':unittest.main()
