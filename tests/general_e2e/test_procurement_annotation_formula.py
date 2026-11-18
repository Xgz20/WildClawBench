import ast
from copy import deepcopy
from decimal import Decimal
import hashlib,json
from pathlib import Path
import sys,tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import openpyxl

from tests.general_e2e.test_procurement_explicit_labels import ProcurementExplicitLabelsTests
from tests.general_e2e.test_local_scoring_runtime import RUNTIME
import native_calc_probe as CALC

P=RUNTIME.procurement_annotation_formula


class ProcurementAnnotationFormulaTests(unittest.TestCase):
    def setUp(self):
        old=ProcurementExplicitLabelsTests();old.setUp()
        self.source=old.source;self.contract=old.contract;self.manifest=old.manifest
        self.manifest['dataset']=dict(P.DATASET)
        self.manifest['runtime']['procurement_explicit_labels_profile']=RUNTIME.procurement_explicit_labels.marker(
            self.contract,RUNTIME.procurement_explicit_labels.CONTRACT)
        self.base,self.prior=RUNTIME._effective_rule_source(self.manifest,self.source)
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        config=self.root/'native-config.json';config.write_text('{}')
        self.lock={'python':sys.executable,'python_sha256':P.sha(sys.executable),
            'helper':str(Path(CALC.__file__)),'helper_sha256':P.sha(CALC.__file__),
            'java_source_sha256':P.sha(Path(CALC.__file__).with_name('native_calc')/'NativeCalcObserve.java'),
            'writer_configuration':str(config),'writer_configuration_sha256':P.sha(config),
            'javac_sha256':'a'*64,'validation_sha256':'b'*64}
        self.manifest['runtime']['procurement_annotation_formula_profile']=P.marker(
            self.contract,P.CONTRACT,P.DATASET,probe=self.lock)

    def tearDown(self):self.temp.cleanup()

    def scope(self):
        code,receipt=P.effective_source(self.manifest,self.source,self.base,self.prior)
        scope={};exec(code,scope);return scope,code,receipt

    def workbook(self,other_formula=False):
        p=self.root/'candidate.xlsx';w=openpyxl.Workbook();s=w.active;s.title='汇总'
        s.append(['项目','数值','核对说明']);s.append(['采购订单总数',2,'= input/采购订单.csv 数据行数'])
        s.append(['数量差额合计',1,'= SUM(数量差异!数量差额)'])
        if other_formula:s['B2']='=UNSUPPORTED_BUSINESS_VALUE()'
        s=w.create_sheet('数量差异');s.append(['采购订单号','采购数量','入库数量','数量差额']);s.append(['O1',1,2,1])
        w.save(p);w.close();return p

    def fake_probe(self,path,*,errors=True,fail=False):
        def run(argv,**kwargs):
            if fail:return SimpleNamespace(returncode=2,stdout='',stderr='synthetic native dependency failure')
            locations=[argv[i+1] for i,value in enumerate(argv) if value=='--cell']
            result={'status':'PASS','profile':CALC.PROFILE,'read_only':True,'macro_execution':'NEVER_EXECUTE',
                'external_link_updates':'NO_UPDATE','assets':{k:self.lock[k] for k in ['helper_sha256','java_source_sha256',
                    'writer_configuration_sha256','javac_sha256']},
                'source_sha256':P.sha(path),'source_unchanged':True,'saved':False,'residual_processes':False,
                'cells':[{'location':location,'error_code':525 if errors else 0,
                          'native_display':'#NAME?' if errors else '2','native_value':None if errors else 2}
                         for location in locations]}
            return SimpleNamespace(returncode=0,stdout=json.dumps(result),stderr='')
        return run

    def test_native_confirmed_annotation_errors_preserve_original_formula_and_workbook_bytes(self):
        scope,_,_=self.scope();path=self.workbook();before=path.read_bytes()
        with patch.object(scope['_paf_subprocess'],'run',side_effect=self.fake_probe(path)):
            tables,unresolved=scope['scan_workbook'](path)
        self.assertEqual(unresolved,[]);self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len(scope['_paf_native_annotations']),2)
        summary=next(t for t in tables if t['kind']=='summary')
        row=next(r for r in summary['rows'] if r['row']==2)
        self.assertEqual(row['values'][2],'= input/采购订单.csv 数据行数')
        self.assertFalse(scope['_paf_native_annotations'][0]['numeric_value_invented'])

    def test_native_good_unresolved_formula_is_not_silently_accepted_or_changed(self):
        scope,_,_=self.scope();path=self.workbook()
        with patch.object(scope['_paf_subprocess'],'run',side_effect=self.fake_probe(path,errors=False)):
            _,unresolved=scope['scan_workbook'](path)
        self.assertEqual(set(unresolved),{'汇总!C2','汇总!C3'})
        self.assertEqual(scope['_paf_native_annotations'],[])

    def test_unresolved_business_formula_and_native_dependency_failure_remain_evaluator_errors(self):
        scope,_,_=self.scope();path=self.workbook(other_formula=True)
        with patch.object(scope['_paf_subprocess'],'run',side_effect=self.fake_probe(path)):
            _,unresolved=scope['scan_workbook'](path)
        self.assertIn('汇总!B2',unresolved)
        with patch.object(scope['_paf_subprocess'],'run',side_effect=self.fake_probe(path,fail=True)):
            with self.assertRaisesRegex(scope['EvaluationError'],'observation failed'):scope['scan_workbook'](path)

    def test_quantity_total_uses_only_complete_submitted_records_and_retains_original_rows(self):
        scope,_,_=self.scope()
        tables=[{'kind':'summary','sheet':'汇总','rows':[{'row':1,'values':['项目','数值','核对说明']},
            {'row':3,'values':['数量差额合计',1,'= SUM(数量差异!数量差额)']}]}]
        before=deepcopy(tables)
        scope['_paf_previous_view']=lambda t,*args:(deepcopy(t),{},{},[])
        records={'qty':[{'id':'O1','values':{'dq':Decimal(1)}}]}
        converted,expected,_,_=scope['_pl_matrix_view'](tables,records,{}, {},{'qty':{'O1':{}}})
        self.assertEqual(expected['paf_quantity_delta_total'],1)
        self.assertEqual(tables,before);self.assertNotEqual(converted[0]['rows'][1]['values'],before[0]['rows'][1]['values'])
        _,expected,_,_=scope['_pl_matrix_view'](tables,records,{}, {},{'qty':{'O1':{},'O2':{}}})
        self.assertIsNone(expected['paf_quantity_delta_total'])
        ambiguous=deepcopy(tables);ambiguous[0]['rows'][1]['values'][2]='总计说明不明确'
        _,expected,_,_=scope['_pl_matrix_view'](ambiguous,records,{}, {},{'qty':{'O1':{}}})
        self.assertNotIn('paf_quantity_delta_total',expected)

    def test_original_grade_numeric_comparisons_and_aggregation_functions_remain_unchanged(self):
        _,code,receipt=self.scope()
        functions=lambda s:{n.name:ast.dump(n) for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
        old,new=functions(self.base),functions(code)
        for name in ['grade','summary_diagnostics','numeric_score','population','material']:
            self.assertEqual(old[name],new[name])
        self.assertFalse(receipt['rubric_and_weights_changed']);self.assertFalse(receipt['candidate_rewritten'])
        legacy=deepcopy(self.manifest);legacy['runtime'].pop('procurement_annotation_formula_profile')
        self.assertEqual(P.effective_source(legacy,self.source,self.base,self.prior),(self.base,self.prior))

    def test_exact_identity_base_and_helper_assets_are_required(self):
        self.assertIsNone(P.marker(self.contract,'0'*64,P.DATASET,probe=self.lock))
        self.assertIsNone(P.marker(self.contract,P.CONTRACT,{**P.DATASET,'digest':'0'*64},probe=self.lock))
        bad=dict(self.lock,helper_sha256='0'*64)
        with self.assertRaises(ValueError):P.marker(self.contract,P.CONTRACT,P.DATASET,probe=bad)
        with self.assertRaises(ValueError):P.effective_source(self.manifest,self.source,self.base+'\n',self.prior)

    def test_native_probe_rejects_external_formula_before_native_loading(self):
        path=self.workbook();CALC.check_local_workbook(path)
        w=openpyxl.load_workbook(path);w['汇总']['D1']='=WEBSERVICE("https://example.com")';w.save(path);w.close()
        with self.assertRaisesRegex(ValueError,'EXTERNAL_FORMULA'):CALC.check_local_workbook(path)


if __name__=='__main__':unittest.main()
