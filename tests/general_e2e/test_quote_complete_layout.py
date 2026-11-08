from copy import deepcopy
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
import openpyxl

from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
import sterilization_quote_complete_layout as P

class QuoteCompleteLayoutTests(unittest.TestCase):
    def setUp(self):
        _,sections,_=_parse_task_source(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{P.TASK}.md')
        self.source=_strip_codeblock(sections['Automated Checks'])
        self.contract={'task_id':P.TASK,'automated_checks':self.source}
        self.manifest={'identity':{'task_id':P.TASK},'dataset':P.DATASET,'digests':{'contract_sha256':P.CONTRACT},
                       'runtime':{'sterilization_quote_layout_profile':P.marker(self.contract,P.CONTRACT,P.DATASET)}}

    def test_precise_fields_and_domain_boundaries_preserve_original_formulas(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(),P.SOURCE)
        fixed,receipt=RUNTIME._effective_rule_source(self.manifest,self.source)
        self.assertEqual(receipt['correction_id'],P.PROFILE)
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])
        old={};new={};exec(self.source,old);exec(fixed,new)
        self.assertEqual(new['role']('Total (USD)'),old['role']('Total (USD)'))
        self.assertEqual(new['role']('Quote validity'),'validity')
        self.assertEqual(new['role']('Estimated total delivery'),'elapsed')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'synthetic.xlsx';w=openpyxl.Workbook();sheet=w.active;sheet.title='Transport Comparison'
            for col,label in [('B','Air'),('C','Sea'),('D','Road')]:
                sheet[col+'4']=label;sheet[col+'13']='14 days';sheet[col+'20']='4 - 5.5 weeks'
                sheet[col+'23']=10;sheet[col+'24']=2;sheet[col+'25']='='+col+'23+'+col+'24'
                sheet[col+'30']=label;sheet[col+'32']=999
            sheet['A13']='Quote validity';sheet['A20']='Estimated total delivery';sheet['A25']='Total (USD)';sheet['A32']='Total (USD)'
            w.save(path)
            before=path.read_bytes()
            old_book=old['Book'](path);new_book=new['Book'](path)
            try:
                original=old_book.extract()[1];options=new_book.extract()[1]
                for mode in ['air','sea','road']:
                    self.assertNotIn('grand',original[mode][0])
                    self.assertEqual(options[mode][0]['grand']['value'],12)
                    self.assertEqual(options[mode][0]['grand']['row'],25)
                    self.assertEqual(options[mode][0]['validity']['row'],13)
                    self.assertEqual(options[mode][0]['elapsed']['row'],20)
                    self.assertEqual(options[mode][1]['grand']['value'],999)
            finally:
                for book in [old_book,new_book]:book.w.close();book.cache.close()
            self.assertEqual(path.read_bytes(),before)

    def test_unknown_source_dataset_and_base_remain_closed_and_legacy_unchanged(self):
        self.assertIsNone(P.marker(self.contract,'0'*64,P.DATASET))
        self.assertIsNone(P.marker(self.contract,P.CONTRACT,{**P.DATASET,'digest':'0'*64}))
        legacy=deepcopy(self.manifest);legacy['runtime']={}
        self.assertEqual(RUNTIME._effective_rule_source(legacy,self.source),(self.source,None))
        with self.assertRaises(RUNTIME.ScoringRuntimeError):
            RUNTIME._effective_rule_source(self.manifest,self.source+'\n')

    def test_original_native_blocker_is_bound_to_cells_formulas_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);candidate=root/'candidate-original';candidate.mkdir()
            path=candidate/'synthetic.xlsx';w=openpyxl.Workbook();sheet=w.active;sheet.title='Transport Comparison'
            for cell,value in {'A13':'Quote validity','A20':'Estimated total delivery','A25':'Total (USD)'}.items():sheet[cell]=value
            for col in ['B','C','D']:sheet[col+'25']='='+col+'23+'+col+'24'
            w.save(path);sha=hashlib.sha256(path.read_bytes()).hexdigest()
            for p in P.blocker_files(root):p.write_text('{}')
            (root/'worker').mkdir()
            worker={'ok':True,'raw_result':{'diagnostics':{'extracted':{mode:{'grand_total':None,'validity_days':None,'order_to_arrival_days':None} for mode in ['air','sea','road']}}}}
            (root/'worker/result.json').write_text(json.dumps(worker))
            m=deepcopy(self.manifest);m['identity']['scoring_attempt_id']='synthetic-001';m['paths']={'candidate_original':'candidate-original'}
            b={'schema_version':'judge-local-evaluation-blocker/v1','task_id':P.TASK,'scoring_attempt_id':'synthetic-001',
               'formal_score_published':False,'verify_score_passed':False,
               'extraction_conflicts':[{'criterion':k,'replacement_score':None} for k in ['automated.scenario_totals','automated.validity_by_mode','automated.elapsed_time']],
               'evidence':{'candidate_sha256':sha},'preservation':{k:False for k in ['candidate_modified','rule_component_modified','rule_rerun','skill_modified','harness_executed','new_task_or_attempt_created','semantic_response_imported','finalize_executed']}}
            self.assertTrue(P.validate_blocker(root,m,self.contract,b))
            altered=deepcopy(b);altered['preservation']['rule_rerun']=True
            with self.assertRaisesRegex(ValueError,'ACTION_INVALID'):P.validate_blocker(root,m,self.contract,altered)
            altered=deepcopy(b);altered['extraction_conflicts'][0]['replacement_score']=1
            with self.assertRaisesRegex(ValueError,'BLOCKER_INVALID'):P.validate_blocker(root,m,self.contract,altered)
            worker['raw_result']['diagnostics']['extracted']['air']['grand_total']=12
            (root/'worker/result.json').write_text(json.dumps(worker))
            with self.assertRaisesRegex(ValueError,'ORIGINAL_FIELDS_NOT_MISSING'):P.validate_blocker(root,m,self.contract,b)

if __name__=='__main__':unittest.main()
