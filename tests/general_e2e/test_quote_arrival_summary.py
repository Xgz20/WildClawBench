import ast
from copy import deepcopy
import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import openpyxl
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

P=RUNTIME.quote_arrival_summary

class QuoteArrivalSummaryTests(unittest.TestCase):
    def setUp(self):
        path=REPO_ROOT/'tasks/general_e2e/02_Office'/(P.TASK+'.md')
        self.source=_strip_codeblock(_parse_task_source(path)[1]['Automated Checks'])
        self.contract={'task_id':P.TASK,'automated_checks':self.source}
        self.m={'identity':{'task_id':P.TASK},'dataset':P.DATASET,'digests':{'contract_sha256':P.CONTRACT},
                'runtime':{'sterilization_quote_layout_profile':RUNTIME.sterilization_quote_layout.marker(self.contract,P.CONTRACT,P.DATASET)}}
        self.base,self.prior=RUNTIME._effective_rule_source(self.m,self.source)
        self.assertEqual(hashlib.sha256(self.base.encode()).hexdigest(),P.BASE)
        self.m['runtime'][P.RUNTIME_KEY]=P.marker(self.contract,P.CONTRACT,P.DATASET)

    def scope(self):
        code,receipt=RUNTIME._effective_rule_source(self.m,self.source);scope={};exec(code,scope)
        return scope,code,receipt

    def workbook(self,path,*,mode='sea',formula=True,hidden_header=False,hidden_summary=False,duplicate=False):
        w=openpyxl.Workbook();s=w.active;s.title='Synthetic'
        s.append(['Quantity','Unit price','Description']);s.append([3,4,'Synthetic product'])
        s['A3']='Total price EXW';s['B3']=12
        s['A4']='Freight cost (recommended: '+mode+')';s['B4']=2
        s['A5']='Estimated total CIP (goods + freight)';s['B5']='=B3+B4' if formula else 14
        s['A8']='Transport mode';s['B8']='Freight cost (USD)';s['C8']='Estimated arrival time';s['D8']='Rate validity'
        for row,label,days in [(9,'Air freight','24–26'),(10,'Sea freight','46–51'),(11,'Road freight','36–42')]:
            s.cell(row,1,label);s.cell(row,2,2);s.cell(row,3,days+' days (production 3 weeks + transit 3–5 days)');s.cell(row,4,'14 days')
        if hidden_header:s.row_dimensions[8].hidden=True
        if hidden_summary:s.row_dimensions[5].hidden=True
        if duplicate:s['A6']=s['A5'].value;s['B6']='=B3+B4'
        w.save(path);w.close()

    def test_explicit_heading_and_single_mode_summary_preserve_missing_other_totals(self):
        scope,_,receipt=self.scope()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.xlsx';self.workbook(path);before=path.read_bytes();book=scope['Book'](path)
            try:
                _,options,_=book.extract()
                self.assertEqual([options[k][0]['elapsed']['cell'] for k in ['air','sea','road']],['C9','C10','C11'])
                self.assertEqual(options['sea'][0]['grand']['cell'],'B5');self.assertEqual(options['sea'][0]['grand']['value'],14)
                self.assertIsNone(options['air'][0].get('grand'));self.assertIsNone(options['road'][0].get('grand'))
            finally:book.w.close();book.cache.close()
            self.assertEqual(path.read_bytes(),before)
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])

    def test_no_mode_or_formula_or_visibility_is_not_synthesized(self):
        scope,_,_=self.scope()
        with tempfile.TemporaryDirectory() as folder:
            for number,kwargs in enumerate([{'mode':'unknown'},{'formula':False},{'hidden_summary':True}]):
                path=Path(folder)/(str(number)+'.xlsx');self.workbook(path,**kwargs);book=scope['Book'](path)
                try:self.assertTrue(all(o[0].get('grand') is None for o in book.extract()[1].values()))
                finally:book.w.close();book.cache.close()
            path=Path(folder)/'hidden.xlsx';self.workbook(path,hidden_header=True);book=scope['Book'](path)
            try:self.assertTrue(all(o[0].get('elapsed') is None for o in book.extract()[1].values()))
            finally:book.w.close();book.cache.close()

    def test_ambiguous_summary_is_not_selected_by_its_value(self):
        scope,_,_=self.scope()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'duplicate.xlsx';self.workbook(path,duplicate=True);book=scope['Book'](path)
            try:
                with self.assertRaisesRegex(scope['EvaluationError'],'Ambiguous explicitly mode-bound'):book.extract()
            finally:book.w.close();book.cache.close()

    def test_original_numeric_functions_caps_and_old_profiles_are_unchanged(self):
        _,code,receipt=self.scope();nodes=lambda source:{n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        old,new=nodes(self.base),nodes(code)
        for key in ['Book','grade','duration','assess_elapsed','material_time_shortening','numeric','num','field_duration','close']:
            self.assertEqual(old[key],new[key])
        old_m=deepcopy(self.m);old_m['runtime'].pop(P.RUNTIME_KEY)
        self.assertEqual(RUNTIME._effective_rule_source(old_m,self.source),(self.base,self.prior))
        self.assertIsNone(P.marker(self.contract,'0'*64,P.DATASET));self.assertIsNone(P.marker(self.contract,P.CONTRACT,{**P.DATASET,'digest':'0'*64}))
        with self.assertRaises(ValueError):P.effective_source(self.m,self.source,self.base+'\n',self.prior)
        self.assertFalse(receipt['rubric_and_weights_changed'])

    def fixture(self,folder):
        root=Path(folder);candidate=root/'candidate-original/results';candidate.mkdir(parents=True)
        path=candidate/'synthetic.xlsx';self.workbook(path)
        m=deepcopy(self.m);m['runtime'].pop(P.RUNTIME_KEY);m['identity'].update(scoring_attempt_id='synthetic-001',execution_attempt_id='execution-001');m['paths']={'candidate_original':'candidate-original'}
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        write=lambda name,value:(root/name).write_text(json.dumps(value,ensure_ascii=False))
        (root/'worker').mkdir();(root/'grader-evidence/files/evaluator_evidence/task024').mkdir(parents=True)
        write('worker/request.json',{'automated_checks':self.base});write('rule-component.json',{})
        write('rule-audit.json',{'status':'completed','identity':m['identity'],'worker':{'return_code':0,'request_sha256':sha(root/'worker/request.json'),'process_tree_cleanup':{'remaining':False}}})
        extracted={mode:{'order_to_arrival_days':None,'elapsed_assessment':{'classification':'missing_or_unreadable'},'row':row} for mode,row in [('air',9),('sea',10),('road',11)]}
        write('worker/result.json',{'ok':True,'raw_result':{'diagnostics':{'extracted':extracted}}})
        write('grader-evidence/files/evaluator_evidence/task024/overview.json',{'extracted_options':extracted})
        write('semantic-response-draft-not-imported.json',{'not_imported':True});(root/'judge-readonly-workbook-check.py').write_text('# readonly inspection\n')
        issue={'status':'evaluation_infrastructure_issue','task_id':P.TASK,'scoring_attempt_id':'synthetic-001','criterion_key':'automated.elapsed_time','origin':'evaluator','official_score_created':False,'verify_inputs':'PASS','verify_score':'not_run_no_official_score','extractor_entry':P.BASE,'evidence_checked':['candidate SHA '+sha(path)],'preservation':{k:False for k in ['candidate_original_modified','frozen_skill_modified','rules_rerun','semantic_response_imported','harness_executed']}}
        write('scoring-infrastructure-review.json',issue)
        rt=SimpleNamespace(_read_json=lambda p:json.loads(Path(p).read_text()),_sha256_file=sha)
        return root,m,rt,{'thread':{'status':'COMPLETED'},'score':None},write,issue

    def test_retirement_requires_original_completed_native_omission_and_no_published_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root,m,rt,task,write,issue=self.fixture(folder)
            result=P.validate_blocker(rt,root,m,self.contract,task);self.assertFalse(result['numeric_score_assigned'])
            altered=deepcopy(issue);altered['preservation']['rules_rerun']=True;write('scoring-infrastructure-review.json',altered)
            with self.assertRaisesRegex(ValueError,'NATIVE_ISSUE_INVALID'):P.validate_blocker(rt,root,m,self.contract,task)
            write('scoring-infrastructure-review.json',issue);(root/'score.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'IDENTITY_INVALID'):P.validate_blocker(rt,root,m,self.contract,task)

    def test_orchestration_copy_is_identical_and_importable(self):
        score=REPO_ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/quote_arrival_summary.py'
        orchestration=REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/quote_arrival_summary.py'
        self.assertEqual(score.read_bytes(),orchestration.read_bytes())

    def test_v1_exact_replay_and_v2_explicit_total_delivery_alias(self):
        old=deepcopy(self.m);old['runtime'][P.RUNTIME_KEY]=P.marker(self.contract,P.CONTRACT,P.DATASET,profile=P.PROFILE_V1)
        code,receipt=RUNTIME._effective_rule_source(old,self.source)
        self.assertEqual(hashlib.sha256(code.encode()).hexdigest(),P.V1_EFFECTIVE)
        self.assertEqual(receipt['correction_id'],P.PROFILE_V1)
        before={};exec(code,before);after,_,_=self.scope()
        self.assertIsNone(before['role']('Est. delivery incl. lead time'))
        self.assertEqual(after['role']('Est. delivery incl. lead time'),'elapsed')
        self.assertIsNone(after['role']('Est. delivery'))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.xlsx';self.workbook(path)
            w=openpyxl.load_workbook(path);w.active['C8']='Est. delivery incl. lead time';w.save(path);w.close()
            sha=hashlib.sha256(path.read_bytes()).hexdigest();b=after['Book'](path)
            try:self.assertEqual([b.extract()[1][k][0]['elapsed']['cell'] for k in ['air','sea','road']],['C9','C10','C11'])
            finally:b.w.close();b.cache.close()
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)

    def test_native_v1_total_heading_issue_requires_exact_old_source_and_no_score(self):
        with tempfile.TemporaryDirectory() as folder:
            root,m,rt,task,write,_=self.fixture(folder)
            m['runtime'][P.RUNTIME_KEY]=P.marker(self.contract,P.CONTRACT,P.DATASET,profile=P.PROFILE_V1)
            path=root/'candidate-original/results/synthetic.xlsx';w=openpyxl.Workbook();s=w.active;s.title='Quotation'
            s['A23']='Est. delivery equals lead time + transit';s['E24']='Est. delivery incl. lead time'
            for row,days in [(25,'24–26'),(26,'46–51'),(27,'36–42')]:s.cell(row,5,'~'+days+' days')
            w.save(path);w.close()
            old=self.base+'\n'+P.BRIDGE;write('worker/request.json',{'automated_checks':old})
            audit=rt._read_json(root/'rule-audit.json');audit['worker']['request_sha256']=rt._sha256_file(root/'worker/request.json');write('rule-audit.json',audit)
            worker=rt._read_json(root/'worker/result.json');worker['raw_result']['elapsed_time']=0
            for row,mode in [(25,'air'),(26,'sea'),(27,'road')]:worker['raw_result']['diagnostics']['extracted'][mode]['row']=row
            write('worker/result.json',worker);write('grader-evidence/files/evaluator_evidence/task024/overview.json',{'extracted_options':worker['raw_result']['diagnostics']['extracted']})
            issue={'schema_version':'general-e2e-evaluator-extraction-issue/v1','identity':{k:m['identity'][k] for k in ['task_id','scoring_attempt_id','execution_attempt_id']},
                'status':'evaluation_error_requires_extractor_repair','total_score':None,
                **{k:False for k in ['candidate_changed','rules_rerun','semantic_response_imported','score_finalized','verify_score_passed']},
                'decision_requests':[{'criterion_key':'automated.elapsed_time','origin':'evaluator','evidence_checked':[P.V1_EFFECTIVE]}]}
            write('evaluator-extraction-issue.json',issue)
            result=P.validate_blocker(rt,root,m,self.contract,task);self.assertFalse(result['numeric_score_assigned'])
            issue['rules_rerun']=True;write('evaluator-extraction-issue.json',issue)
            with self.assertRaises(ValueError):P.validate_blocker(rt,root,m,self.contract,task)

if __name__=='__main__':unittest.main()
