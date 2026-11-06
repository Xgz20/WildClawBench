from pathlib import Path
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import ast
import hashlib
import json
import operator
import re
import tempfile
import unittest
import importlib.util
import csv
from types import SimpleNamespace

import openpyxl
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import _PROFILES, effective_source
from src.wildclawbench_grading_core.rules import _validate_grade_function

ROOT=Path(__file__).resolve().parents[2]

def sources(tid):
    current=next((ROOT/'tasks/general_e2e').rglob(tid+'.md'))
    index=ROOT/'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json'
    row=json.loads(index.read_text())['files'][current.relative_to(ROOT).as_posix()]
    old=index.parent/row['snapshot']
    _,a,_=_parse_task_source(old);_,b,_=_parse_task_source(current)
    return a,b,_strip_codeblock(a['Automated Checks']),_strip_codeblock(b['Automated Checks'])

class Round7SourceRepairTests(unittest.TestCase):
    def test_native_repairs_are_opted_in_and_historical_manifests_keep_old_source(self):
        path=ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/shared_source_repairs.py'
        spec=importlib.util.spec_from_file_location('round7_bridge',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for row in _PROFILES.values():
            _,_,old,new=sources(row['task_id'])
            contract={'task_id':row['task_id'],'automated_checks':old}
            manifest={'identity':{'task_id':row['task_id']},'runtime':{}}
            self.assertEqual(module.effective_source(manifest,old,old,None),(old,None))
            manifest['runtime']['shared_rule_source_repair']=module.marker(contract)
            self.assertEqual(module.effective_source(manifest,old,old,None)[0],new)
            manifest['runtime']['shared_rule_source_repair']['source_sha256']='tampered'
            with self.assertRaises(ValueError):module.effective_source(manifest,old,old,None)

    def test_failure_retirement_requires_exact_unscored_source_and_original_error(self):
        path=ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/registered_rule_source_failures.py'
        spec=importlib.util.spec_from_file_location('round7_failure',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        read=lambda p:json.loads(p.read_text())
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        rt=SimpleNamespace(_read_json=read,_sha256_file=sha)
        for tid,row in module.ROWS.items():
            _,_,old,_=sources(tid)
            with tempfile.TemporaryDirectory() as tmp:
                attempt=Path(tmp);worker=attempt/row[3];worker.mkdir(parents=True)
                request={'automated_checks':old}
                if row[3]!='worker':request['rule_review']={'schema_version':'wildclawbench.general-e2e-rule-review-worker/v1','profile':'warranty-recovery-reason-semantic-review/v1','mode':'discover','decisions':{}}
                (worker/'request.json').write_text(json.dumps(request))
                result={'ok':False,'error':{'type':row[4],'message':row[5]},'worker':{'pid':123}}
                (worker/'result.json').write_text(json.dumps(result))
                manifest={'identity':{'task_id':tid},'dataset':{'id':'general-custom70-v4'},'digests':{'contract_sha256':row[0]}}
                contract={'task_id':tid,'automated_checks':old};task={'thread':None,'score':None}
                if row[3]=='worker':
                    audit={'identity':manifest['identity'],'status':'failed','worker':{'request_sha256':sha(worker/'request.json'),'process_tree_cleanup':{'remaining':False}}}
                    (attempt/'rule-audit.json').write_text(json.dumps(audit))
                self.assertEqual(module.evidence(rt,attempt,manifest,contract,task),result)
                task['thread']={'status':'RUNNING'}
                with self.assertRaises(ValueError):module.evidence(rt,attempt,manifest,contract,task)
                task['thread']=None;result['error']['message']='unknown'
                (worker/'result.json').write_text(json.dumps(result))
                with self.assertRaises(ValueError):module.evidence(rt,attempt,manifest,contract,task)

    def test_preworker_failure_cannot_claim_an_exited_worker_or_hide_changed_runtime(self):
        path=ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/registered_rule_source_failures.py'
        spec=importlib.util.spec_from_file_location('round7_preworker',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        tid='02_Office_task_015_procurement_reconciliation';row=module.ROWS[tid]
        _,_,old,_=sources(tid)
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Path(tmp);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            rt=SimpleNamespace(_read_json=lambda p:json.loads(p.read_text()),_sha256_file=sha)
            effective='34cd4dae061555354dea38a62146b4f1b833423837d2898ac30720470e02f3df'
            profile={'profile':'procurement-date-and-section-extraction/v2','current_source_sha256':effective}
            manifest={'identity':{'task_id':tid},'dataset':{'id':'general-custom70-v4'},'digests':{'contract_sha256':row[0]},'runtime':{'shared_rule_source_repair':profile}}
            (attempt/'rule-source-correction.json').write_text(json.dumps({'effective_source_sha256':effective}))
            audit={'identity':manifest['identity'],'status':'failed','worker':None,'runtime_workspace':{'drifted':False},
                'error':{'code':'RULE_ENTRYPOINT_INVALID','message':'automated_checks must define exactly one synchronous grade() function'},
                'source_correction':{'path':'rule-source-correction.json','sha256':sha(attempt/'rule-source-correction.json')}}
            (attempt/'rule-audit.json').write_text(json.dumps(audit))
            contract={'task_id':tid,'automated_checks':old};task={'score':None,'thread':None}
            self.assertEqual(module.evidence(rt,attempt,manifest,contract,task),{'worker_never_started':True})
            (attempt/'worker').mkdir()
            with self.assertRaises(ValueError):module.evidence(rt,attempt,manifest,contract,task)
            (attempt/'worker').rmdir();audit['runtime_workspace']['drifted']=True
            (attempt/'rule-audit.json').write_text(json.dumps(audit))
            with self.assertRaises(ValueError):module.evidence(rt,attempt,manifest,contract,task)

    def test_only_exact_sources_change_and_task_meaning_stays_frozen(self):
        for digest,profile in _PROFILES.items():
            a,b,old,new=sources(profile['task_id'])
            self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),digest)
            self.assertEqual(effective_source(profile['task_id'],old)[0],new)
            for section in ['Prompt','Expected Behavior','Grading Criteria','LLM Judge Rubric']:
                self.assertEqual(a[section],b[section],section)
            self.assertEqual(effective_source('other',old),(old,None))
            self.assertEqual(effective_source(profile['task_id'],old+'\n'),(old+'\n',None))
            ast.parse(new)
            _validate_grade_function(new)

    def test_whole_column_aggregates_preserve_implicit_blank_rows_and_bounded_results(self):
        tid='02_Office_task_010_warranty_recovery_allocation'
        _,_,_,code=sources(tid)
        names={'_WarrantyWholeColumnRange','Cells','CandidateError','EvaluationError'}
        nodes=[n for n in ast.parse(code).body if isinstance(n,ast.ClassDef) and n.name in names]
        scope=dict(openpyxl=openpyxl,Tokenizer=Tokenizer,range_boundaries=range_boundaries,
                   ast=ast,re=re,operator=operator,Decimal=Decimal,ROUND_HALF_UP=ROUND_HALF_UP)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<trusted-excel-evaluator>','exec'),scope)
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'test.xlsx';w=openpyxl.Workbook();d=w.active;d.title='Detail'
            for r,v,amount in [(1,'vendor','amount'),(2,'A',10),(3,'B',20),(4,'A',5)]:d.cell(r,9,v);d.cell(r,14,amount)
            other=w.create_sheet('Other');other['J1']='flag';other['J2']='ok';other['J3']='ok'
            s=w.create_sheet('Summary')
            formulas={1:"=SUMIF(Detail!$I:$I,\"A\",Detail!$N:$N)",2:'=COUNTIF(Detail!I:I,"A")',
                      3:'=COUNTIF(Detail!I:I,"")',4:'=COUNTIFS(Detail!I:I,"A",Other!J:J,"ok")',
                      5:'=COUNTIFS(Detail!I:I,"",Other!J:J,"")',6:'=SUMIF(Detail!I1:I4,"A",Detail!N1:N4)',
                      7:'=SUM(Detail!N:N)',8:'=IF(Detail!I:I="A",1,0)',9:'=COUNTA(Detail!I:I)',
                      10:'=COUNTA(0,FALSE,"")',11:'=COUNTA(IF(TRUE,"",""))'}
            for r,text in formulas.items():s.cell(r,1,text)
            w.save(f);cells=scope['Cells'](f)
            for row,value in [(1,15),(2,2),(3,1048572),(4,1),(5,1048572),(6,15),(7,35),(9,4),(10,3),(11,1)]:
                self.assertEqual(cells.cell('Summary',f'A{row}'),value)
            with self.assertRaises(scope['EvaluationError']):cells.cell('Summary','A8')

    def test_warranty_totals_and_explicit_summary_roles_do_not_become_phantom_claims(self):
        _,_,_,code=sources('02_Office_task_010_warranty_recovery_allocation')
        scope={};exec(code,scope)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'warranty.xlsx';wb=openpyxl.Workbook();ws=wb.active;ws.title='可追偿明细'
            for row in [ ['序号','索赔编号','供应商','维修成本','分摊维修成本','本次金额','已追偿'],
                         [1,'WR-1','供应商甲',100,50,10,5],
                         ['合计（1 行）',None,None,None,50,10,5],
                         ['缺少编号',None,'供应商甲',20,20,10,0] ]:ws.append(row)
            review=wb.create_sheet('不可追偿或待核查')
            review.append(['索赔编号','供应商','缺口与原因','维修成本','参考分摊成本','计入暴露维修成本','已追偿','本次金额','待核查金额'])
            review.append(['WR-2','供应商甲','已覆盖',100,50,50,40,0,0])
            summary=wb.create_sheet('供应商汇总')
            summary.append(['供应商','涉及索赔数','维修成本暴露','已追偿（已入账）','本次可追偿金额'])
            summary.append(['供应商甲',2,100,45,10]);wb.save(path)
            tables,_=scope['read_tables'](path)
            self.assertEqual(len(tables['detail']),2)
            self.assertEqual(tables['detail'][1]['supplier'],'供应商甲')
            self.assertIsNone(tables['detail'][1]['claim'])
            self.assertEqual(tables['review'][0]['cost'],50)
            self.assertEqual(tables['summary'][0]['already'],45)

    def test_prior_source_repair_profiles_reproduce_their_original_sha(self):
        from src.wildclawbench_grading_core.source_repairs import _history
        for digest,profiles in _history().items():
            for profile,row in profiles.items():
                _,_,old,_=sources(row['task_id'])
                source,receipt=effective_source(row['task_id'],old,profile=profile)
                self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),row['current_source_sha256'])
                self.assertEqual(receipt['correction_id'],profile)
                self.assertEqual(receipt['reason'],row['reason'])

    def test_procurement_section_headers_keep_priority_counts_and_status_subsets_separate(self):
        _,_,_,code=sources('02_Office_task_015_procurement_reconciliation')
        scope={};exec(code,scope)
        records={
            'qty':[{'id':'A','row':2,'values':{'oq':10,'rq':9,'oa':100,'ra':90,'dq':-1,'da':-10}}],
            'amount':[{'id':'A','row':2,'values':{'oq':10,'rq':9,'oa':100,'ra':90,'dq':-1,'da':-10}}],
            'missing':[{'id':'B','row':2,'values':{'oq':20,'oa':200}}, {'id':'C','row':3,'values':{'oq':30,'oa':300}}],
            'orphan':[{'id':'D-01','row':2,'values':{'rq':5,'ra':50}}]}
        tables=[]
        for kind,items in records.items():
            table={'sheet':kind,'kind':kind,'header_row':1,'records':items,
                   'rows':[{'row':1,'values':['业务编号','优先级']}]}
            for row in items:table['rows'].append({'row':row['row'],'values':[row['id'],'P2' if row['id']=='B' else '跟踪' if row['id']=='C' else 'P1']})
            tables.append(table)
        raw=[['项目','笔数','订单金额（元）','入库金额（元）','金额差额（元）','数量（订单）','数量（入库）','说明'],
             ['采购订单（全部状态）',3,600,'—','—',60,'—','全量'],
             ['入库记录（全部）',2,'—',140,'—','—',14,'全量'],
             ['已匹配（一单一入库）',1,100,90,-10,10,9,'入库减订单'],
             ['工作表','P1','P2','P3','跟踪','合计','优先级判定规则'],
             ['数量差异',1,0,0,0,1,'金额规则'],['金额差异',1,0,0,0,1,'金额规则'],
             ['未入库订单',0,1,0,1,2,'状态规则'],['无对应订单入库',1,0,0,0,1,'金额规则'],
             ['去重后 P1 合计',2,0,0,0,2,'两个不同业务对象'],
             ['项目','笔数','订单金额（元）','入库金额（元）','差额（元）','数量','占订单总额','说明'],
             ['未入库订单',2,500,'—',-500,50,500/600,'完整类别'],
             ['其中：状态“已完成”',1,200,'—',-200,20,200/600,'子集'],
             ['其中：状态“待确认”',1,300,'—',-300,30,300/600,'子集'],
             ['无对应订单入库',1,'—',50,50,5,50/600,'完整类别']]
        summary={'sheet':'汇总','kind':'summary','rows':[{'row':i+1,'values':r} for i,r in enumerate(raw)]}
        tables.append(summary)
        metrics={k:Decimal(str(v)) for k,v in {'orders':3,'receipts':2,'orders_amount':600,'receipts_amount':140}.items()}
        truth={k:{r['id']:None for r in rows} for k,rows in records.items()}
        numeric={'categories':{k:{'direction':1} for k in ['qty','amount']}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'input').mkdir()
            for name,fields,rows in [
                ('采购订单.csv',['ORDER_ID','ORDER_QTY','TOTAL_AMOUNT','STATUS'],[['A',10,100,'已完成'],['B',20,200,'已完成'],['C',30,300,'待确认']]),
                ('入库记录.csv',['RECEIPT_NO','RECV_QTY','RECV_AMOUNT'],[['A-01',9,90],['D-01',5,50]])]:
                with (root/'input'/name).open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(fields);writer.writerows(rows)
            scope['_PS_ROOT']=root
            result=scope['summary_diagnostics'](tables,records,metrics,numeric,truth)
            self.assertEqual(result['unrecognized_numeric_rows'],[])
            self.assertTrue(all(c['matches'] is True for c in result['claims']))
            self.assertEqual(next(c for c in result['claims'] if c['value_location']=='汇总!F6')['key'],'qty')
            self.assertNotEqual(next(c for c in result['claims'] if c['value_location']=='汇总!B6')['key'],'qty')
            raw[5][1]=0
            result=scope['summary_diagnostics'](tables,records,metrics,numeric,truth)
            self.assertTrue(any(c['matches'] is False and c['value_location']=='汇总!B6' for c in result['claims']))
            summary['rows'].append({'row':99,'values':['未知数字口径',123]})
            result=scope['summary_diagnostics'](tables,records,metrics,numeric,truth)
            self.assertEqual(result['unrecognized_numeric_rows'][-1]['row'],99)

    def test_repaired_non_equivalent_pdf_is_candidate_failure_not_unknown_version(self):
        tid='01_Information_Search_Organization_task_001_acl2024_long_context_qa'
        _,_,_,code=sources(tid)
        grade=ast.parse(code).body[0]
        selected=next(n for n in ast.walk(grade) if isinstance(n,ast.If)
                      and isinstance(n.test,ast.Name) and n.test.id=='matched'
                      and 'non_equivalent_repaired_pdf' in ast.unparse(n))
        fn=ast.FunctionDef(name='classify',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg=x) for x in ['matched','identified','repaired']],kwonlyargs=[],kw_defaults=[],defaults=[]),
            body=ast.parse("record={'requires_pdf_repair':repaired};pdf_pass=set();pending_versions=[];relative='candidate.pdf'").body+[selected]+ast.parse('return record,pdf_pass,pending_versions').body,decorator_list=[])
        scope={};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<original-pdf-branch>','exec'),scope)
        record,_,pending=scope['classify'](None,['paper'],True)
        self.assertEqual(record['status'],'non_equivalent_repaired_pdf');self.assertEqual(pending,[])
        record,_,pending=scope['classify'](None,['paper'],False)
        self.assertEqual(record['status'],'pending_version_review');self.assertEqual(pending,['candidate.pdf'])
        record,passed,pending=scope['classify']('paper',['paper'],True)
        self.assertEqual(passed,{'paper'});self.assertEqual(pending,[])

    def test_procurement_date_size_estimate_matches_existing_final_encoder(self):
        tid='02_Office_task_015_procurement_reconciliation'
        _,_,old,new=sources(tid)
        old_line=next(x for x in old.splitlines() if 'chunks[min(range(2)' in x)
        new_line=next(x for x in new.splitlines() if 'chunks[min(range(2)' in x)
        item={'date':datetime(2026,5,1,12,30),'amount':12.5}
        with self.assertRaises(TypeError):exec(compile(old_line.strip(),'<old-evidence-sizing>','exec'),{'chunks':[[item],[]],'item':item,'json':json})
        chunks=[[item],[]];exec(compile(new_line.strip(),'<fixed-evidence-sizing>','exec'),{'chunks':chunks,'item':item,'json':json})
        self.assertEqual(chunks,[[item],[item]])
