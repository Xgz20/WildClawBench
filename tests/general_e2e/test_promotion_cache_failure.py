import hashlib,json,shutil,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import openpyxl
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR

P=ORCHESTRATOR.framework_failure_retirement.source_failures.promotion_cache_failure
class PromotionCacheFailureTests(unittest.TestCase):
    def test_exact_uncached_formula_failure_and_non_cache_errors_are_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'worker').mkdir()
            for folder in ['candidate/results','runtime/results']:(root/folder).mkdir(parents=True)
            candidate=root/'candidate/results/促销毛利分析.xlsx';w=openpyxl.Workbook();s=w.active;s.title='分组指标';s['E2']='=1+1';w.save(candidate);w.close()
            shutil.copyfile(candidate,root/'runtime/results/促销毛利分析.xlsx')
            source='def grade(transcript,workspace_path):return {}';digest=hashlib.sha256(source.encode()).hexdigest()
            def write(name,value):(root/name).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            rt=SimpleNamespace(_read_json=lambda p:json.loads(p.read_text()),_sha256_file=sha)
            write('worker/request.json',{'automated_checks':source})
            result={'ok':False,'result':None,'error':{'type':'GradingIndeterminate','message':P.PREFIX+'分组指标!E2'},'worker':{'pid':123}}
            write('worker/result.json',result)
            identity={'task_id':P.TASK};audit={'identity':identity,'status':'failed','runtime_workspace':{'drifted':False},
                'worker':{'return_code':1,'timed_out':False,'request_sha256':sha(root/'worker/request.json'),
                'process_tree_cleanup':{'remaining':False},'worker_pid':123}}
            write('rule-audit.json',audit)
            m={'identity':identity,'dataset':P.DATASET,'digests':{'contract_sha256':P.CONTRACT},
               'paths':{'candidate_original':'candidate'},'runtime':{'workspace_argument':'runtime'}}
            c={'task_id':P.TASK,'automated_checks':source};task={'phase':'RULES_NEEDS_ATTENTION'}
            with patch.object(P,'SOURCE',digest):
                self.assertEqual(P.evidence(rt,root,m,c,task),result)
                for change in [{'thread':{}},{'score':{}}]:
                    with self.subTest(change=change),self.assertRaises(ValueError):P.evidence(rt,root,m,c,{**task,**change})
                result['error']['type']='RuntimeError';write('worker/result.json',result)
                with self.assertRaises(ValueError):P.evidence(rt,root,m,c,task)
                result['error']['type']='GradingIndeterminate';result['error']['message']=P.PREFIX+'分组指标!E3';write('worker/result.json',result)
                with self.assertRaises(ValueError):P.evidence(rt,root,m,c,task)

if __name__=='__main__':unittest.main()
