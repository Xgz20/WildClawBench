import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import openpyxl
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

P=RUNTIME.promotion_formula_values
class PromotionFormulaValuesTests(unittest.TestCase):
    def source(self):
        data=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v6.json').read_text())
        task=next(t for t in data['tasks'] if t['task_id']==P.TASK)
        _,sections,_=_parse_task_source(REPO_ROOT/task['source']['task_path'])
        return _strip_codeblock(sections['Automated Checks'])
    def probe(self,root):
        scripts=Path(P.__file__).parent;configuration=root/'configuration.json';configuration.write_text('{}')
        return {'python':sys.executable,'python_sha256':P.sha(sys.executable),
            'helper':str(scripts/'native_calc_values_file.py'),'helper_sha256':P.sha(scripts/'native_calc_values_file.py'),
            'assets':{'helper_sha256':P.sha(scripts/'native_calc_values.py'),
                'java_source_sha256':P.sha(scripts/'native_calc/NativeCalcValues.java'),
                'writer_configuration_sha256':P.sha(configuration),'javac_sha256':'a'*64},
            'writer_configuration':str(configuration),'pointer_sha256':'b'*64,'validation_sha256':'c'*64}
    def test_precise_marker_legacy_behavior_and_source_drift(self):
        source=self.source();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),P.SOURCE)
        with tempfile.TemporaryDirectory() as td:
            probe=self.probe(Path(td));contract={'task_id':P.TASK,'automated_checks':source}
            marker=P.marker(contract,P.CONTRACT,P.DATASET,probe=probe)
            m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},'dataset':P.DATASET,
                'runtime':{'promotion_formula_value_profile':marker}}
            fixed,receipt=P.effective_source(m,source,source,None)
            self.assertTrue(fixed.startswith(source));self.assertFalse(receipt['candidate_rewritten'])
            self.assertFalse(receipt['numeric_decisions_assigned'])
            self.assertEqual(P.effective_source({'runtime':{}},source,'legacy',{'old':True}),('legacy',{'old':True}))
            with self.assertRaises(ValueError):P.effective_source(m,source,source+'\n',None)
            self.assertIsNone(P.marker(contract,'0'*64,P.DATASET,probe=probe))
    def test_memory_view_preserves_zero_empty_error_literal_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'results').mkdir();path=root/'results/促销毛利分析.xlsx'
            w=openpyxl.Workbook();s=w.active;s.title='分组指标'
            s['A1']='literal';s['E2']='=1+1';s['F2']='=IF(1=1,"",7)';s['G2']='=1/0';s['H2']='=0';s['I2']=17
            w.save(path);w.close();before=P.sha(path);probe=self.probe(root)
            scope={};exec(self.source(),scope);scope['_PFV_NATIVE_PROBE']=probe;exec(P.BRIDGE,scope)
            rows=[['分组指标!E2','number',2.0,0],['分组指标!F2','string','',0],
                  ['分组指标!G2','error','Err:532',532],['分组指标!H2','number',0.0,0]]
            def fake_run(argv,**kwargs):
                output=Path(argv[argv.index('--output-root')+1]);output.mkdir()
                requested=json.loads(Path(argv[argv.index('--locations-json')+1]).read_text())
                self.assertEqual(set(requested),{r[0] for r in rows})
                page=output/'values-0001.json';page.write_text(json.dumps({'profile':'readonly-native-calc-bulk-values/v2','rows':rows}))
                observed={'status':'PASS','profile':'readonly-native-calc-bulk-values/v2','assets':probe['assets'],
                    'source_sha256':before,'read_only':True,'saved':False,'source_unchanged':True,
                    'disposable_copy_unchanged':True,'calculated_all':True,'residual_processes':False,
                    'macro_execution':'NEVER_EXECUTE','external_link_updates':'NO_UPDATE','cell_count':4,
                    'pages':[{'path':page.name,'sha256':P.sha(page),'size':page.stat().st_size,'cell_count':4}]}
                for name in ['requested-locations.txt','native-values.jsonl','native.properties','compile.stdout','compile.stderr','server.stdout','server.stderr','java.stdout','java.stderr']:
                    (output/name).write_text(json.dumps(rows) if name=='native-values.jsonl' else '')
                (output/'observation.json').write_text(json.dumps(observed));return SimpleNamespace(returncode=0,stdout=json.dumps(observed),stderr='')
            with patch.object(scope['_pfv_subprocess'],'run',side_effect=fake_run):values=scope['load_workbook'](path,data_only=True,read_only=False)
            self.assertEqual(values['分组指标']['E2'].value,2)
            self.assertEqual(values['分组指标']['F2'].value,'')
            self.assertEqual(values['分组指标']['G2'].value,'Err:532')
            self.assertEqual(values['分组指标']['H2'].value,0)
            self.assertEqual(values['分组指标']['I2'].value,17);values.close()
            self.assertEqual(P.sha(path),before)
            original=openpyxl.load_workbook(path,data_only=False);self.assertEqual(original['分组指标']['G2'].value,'=1/0');original.close()
            view=json.loads((root/'评分证据/原生公式求值/内存视图说明.json').read_text())
            self.assertFalse(view['candidate_workbook_saved']);self.assertFalse(view['existing_cached_values_replaced'])
            self.assertEqual(view['all_native_error_cells'],[['分组指标!G2',532,'Err:532']])

if __name__=='__main__':unittest.main()
