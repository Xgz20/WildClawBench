from copy import deepcopy
from pathlib import Path
import ast,hashlib,json,subprocess,sys,tempfile,unittest
import openpyxl
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from src.utils.task_parser import parse_task_md as _parse_task_md
from eval_general_e2e.datasets.source_history import frozen_v2_task_path

def parse_task_md(path):
    # These regressions exercise the immutable v2 correction profiles.
    return _parse_task_md(frozen_v2_task_path(path))


sys.path.insert(0,str(REPO_ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts'))
import warranty_recovery_review as REVIEW

class WarrantyReasonReviewTests(unittest.TestCase):
    def source_and_manifest(self):
        source=parse_task_md(REPO_ROOT/'tasks/general/work/02_Office'/f'{REVIEW.TASK}.md')['automated_checks']
        manifest={'identity':{'task_id':REVIEW.TASK},'digests':{'contract_sha256':REVIEW.CONTRACT},'dataset':REVIEW.DATASET,
            'judge':{'protocol':'codex-agent-judge-v1'},'runtime':{'rule_review_profile':REVIEW.PROFILE,
            'warranty_recovery_layout_profile':REVIEW.marker({'task_id':REVIEW.TASK,'automated_checks':source},REVIEW.CONTRACT,REVIEW.DATASET)}}
        return source,manifest
    def corrected(self):
        source,m=self.source_and_manifest();fixed,receipt=RUNTIME._effective_rule_source(m,source)
        return source,fixed,receipt,m
    def test_new_profile_exact_bindings_and_original_arithmetic(self):
        source,fixed,receipt,m=self.corrected()
        catalog=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v2.json').read_text())
        row=next(t for t in catalog['tasks'] if t['task_id']==REVIEW.TASK)
        self.assertEqual(row['digests']['scoring_contract_sha256'],REVIEW.CONTRACT)
        self.assertEqual(catalog['dataset_digest'],REVIEW.DATASET['digest'])
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),REVIEW.SOURCE)
        before,after=ast.parse(source),ast.parse(fixed)
        for name in ['number','close','pair','reason_class','band','safe_path']:
            a=next(n for n in before.body if isinstance(n,ast.FunctionDef) and n.name==name)
            b=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))
        self.assertFalse(receipt['numeric_decisions_assigned']);self.assertFalse(receipt['candidate_rewritten'])
        self.assertFalse(receipt['discovery_provisional_scores_publishable'])
        for field in ['contract','dataset','judge']:
            bad=deepcopy(m)
            if field=='contract':bad['digests']['contract_sha256']='0'*64
            elif field=='dataset':bad['dataset']['digest']='0'*64
            else:bad['judge']['protocol']='api-judge-v1'
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,source)
        self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))
        contract={'task_id':REVIEW.TASK,'automated_checks':source}
        self.assertEqual(RUNTIME._new_native_rule_review_profile(contract,REVIEW.CONTRACT,{'protocol':'codex-agent-judge-v1'}),REVIEW.PROFILE)
        self.assertIsNone(RUNTIME._new_native_rule_review_profile(contract,REVIEW.CONTRACT,{'protocol':'api-judge-v1'}))
        self.assertIsNone(RUNTIME._new_native_rule_review_profile(contract,'0'*64,{'protocol':'codex-agent-judge-v1'}))
    def test_equivalent_columns_raw_evidence_and_explicit_non_initiation(self):
        _,fixed,_,_=self.corrected();scope={};exec(compile(fixed,'<synthetic-warranty>','exec'),scope)
        for label,key in [('追偿供应商','supplier'),('实际分摊比例','share'),('CAP上限(元)','cap'),('原因说明','reason'),('处理动作','action'),('已追偿汇总(元)','already')]:
            self.assertEqual(scope['header_key'](label),key)
        self.assertIsNone(scope['header_key']('申报/涉及供应商'))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'candidate.xlsx';w=openpyxl.Workbook();s=w.active;s.title='可追偿明细'
            s.append(['索赔编号','追偿供应商','本次金额(元)','处理动作','未映射完整说明'])
            s.append(['A','供应商甲',100,'发起追偿','真实原文 A'])
            s.append(['B','供应商乙',0,'不再发起（明确原因说明）','真实原文 B'])
            s.append(['C','供应商丙',0,None,'零金额未声明，不得当合格不发起'])
            s.append(['D','供应商丁',100,'不再发起','矛盾正金额不得移为不发起'])
            w.save(path);w.close();tables,found=scope['read_tables'](path)
            self.assertEqual([r['claim'] for r in tables['detail']],['A','C','D'])
            self.assertEqual([r['claim'] for r in tables['review']],['B'])
            self.assertIn('review',found);self.assertEqual(tables['review'][0]['_raw_values'][-1],'真实原文 B')
            self.assertEqual(found['_context'][0]['values'][-1],'未映射完整说明')
    def worker(self,mode,decisions=None):
        _,fixed,_,_=self.corrected()
        fixed+='''
def grade(transcript,workspace_path):
    passed=_warranty_reason_matches(('SYNTHETIC','供应商甲'),{'reason':'原候选原因','_location':'synthetic!row2'}, {'decision':'review'}, [])
    return {'unchanged_amount':0.5,'reason_category':float(passed)}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);workspace=root/'workspace';workspace.mkdir()
            request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'automated_checks':fixed,'workspace_path':str(workspace),'transcript':[],
                'rule_review':RUNTIME.rule_review.worker_configuration(mode,decisions,profile=REVIEW.PROFILE)}
            (root/'request.json').write_text(json.dumps(request),encoding='utf-8')
            r=subprocess.run([sys.executable,'-I',str(REPO_ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/rule_worker.py'),
                '--request',str(root/'request.json'),'--result',str(root/'result.json')],capture_output=True)
            return r.returncode,json.loads((root/'result.json').read_text())
    def test_managed_discovery_publishes_no_score_and_only_native_boolean_applies(self):
        code,discovered=self.worker('discover');self.assertEqual(code,0);self.assertEqual(discovered['result'],{})
        self.assertNotIn('raw_result',discovered);contexts=discovered['rule_review']['contexts'];self.assertEqual(len(contexts),1)
        key,item=next(iter(contexts.items()));self.assertEqual(item['kind'],'warranty-non-initiation-reason-category')
        for value,expected in [(True,1.),(False,0.)]:
            code,result=self.worker('apply',{key:value});self.assertEqual(code,0)
            self.assertEqual(result['result'],{'unchanged_amount':.5,'reason_category':expected})
        for decisions in [{},{key:1},{'other':True}]:
            code,result=self.worker('apply',decisions);self.assertNotEqual(code,0);self.assertFalse(result['ok'])
