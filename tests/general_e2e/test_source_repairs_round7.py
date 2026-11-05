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
from types import SimpleNamespace

import openpyxl
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import _PROFILES, effective_source

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
                      7:'=SUM(Detail!N:N)',8:'=IF(Detail!I:I="A",1,0)'}
            for r,text in formulas.items():s.cell(r,1,text)
            w.save(f);cells=scope['Cells'](f)
            for row,value in [(1,15),(2,2),(3,1048572),(4,1),(5,1048572),(6,15),(7,35)]:
                self.assertEqual(cells.cell('Summary',f'A{row}'),value)
            with self.assertRaises(scope['EvaluationError']):cells.cell('Summary','A8')

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
