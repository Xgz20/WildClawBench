"""v3 source/CLI/E2E parity and original-input regressions."""
from pathlib import Path
from copy import deepcopy
import ast,hashlib,json,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from eval_general_e2e.datasets.bundle import (compile_dataset,GENERAL70_V2_DEFINITION,
    GENERAL70_V3_DEFINITION,dataset_manifest_path,load_manifest_lock)
from src.utils.task_parser import parse_task_md
from src.utils.dataset_selection import dataset_task_paths
from src.utils import declared_rule_review as REVIEW,grading
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

class General70V3SourceSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.old_members=compile_dataset(REPO_ROOT,definition=GENERAL70_V2_DEFINITION)
        cls.new,cls.members=compile_dataset(REPO_ROOT,definition=GENERAL70_V3_DEFINITION)
        cls.contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in cls.members if m.path.endswith('/private-scoring/contract.json')}
    def test_all_seventy_cli_rules_are_the_exact_frozen_e2e_source(self):
        manifest,grouped=dataset_task_paths(REPO_ROOT,'general-custom70-v3')
        self.assertEqual(manifest,self.new)
        self.assertEqual(sum(map(len,grouped.values())),70)
        for paths in grouped.values():
            for path in paths:
                task=parse_task_md(path)
                self.assertEqual(task['automated_checks'],self.contracts[task['task_id']]['automated_checks'])
    def test_v2_cli_uses_archived_bytes_and_original_lock(self):
        manifest,grouped=dataset_task_paths(REPO_ROOT,'general-custom70-v2')
        self.assertEqual(manifest,load_manifest_lock(dataset_manifest_path('general-custom70-v2')))
        old={json.loads(m.data)['task_id']:json.loads(m.data) for m in self.old_members if m.path.endswith('/private-scoring/contract.json')}
        for paths in grouped.values():
            for path in paths:
                task=parse_task_md(path)
                self.assertEqual(task['automated_checks'],old[task['task_id']]['automated_checks'])
    def test_frozen_revisions_do_not_follow_later_git_source_commits(self):
        with patch('eval_general_e2e.datasets.bundle._derive_source_revision',side_effect=AssertionError('must use the explicit source revision')):
            for definition in [GENERAL70_V2_DEFINITION,GENERAL70_V3_DEFINITION]:
                manifest,_=compile_dataset(REPO_ROOT,definition=definition)
                self.assertEqual(manifest,load_manifest_lock(dataset_manifest_path(definition.dataset_id)))
    def test_exact_v3_generated_glob_admissions_preserve_all_old_catalogs(self):
        registered=RUNTIME.generated_evidence_globs.registry('general-custom70-v3')
        self.assertEqual(len(registered),4)
        by_id={t['task_id']:t for t in self.new['tasks']}
        for row in registered:
            tid=row['task_id'];manifest={'identity':{'task_id':tid},
                'digests':{'contract_sha256':by_id[tid]['digests']['scoring_contract_sha256']},
                'dataset':{'id':self.new['dataset_id'],'digest':self.new['dataset_digest']}}
            self.assertIsNotNone(RUNTIME.generated_evidence_globs.descriptor(manifest,self.contracts[tid]))
            manifest['dataset']['digest']='0'*64
            self.assertIsNone(RUNTIME.generated_evidence_globs.descriptor(manifest,self.contracts[tid]))
        self.assertEqual(len(RUNTIME.generated_evidence_globs.registry('general-custom70-v2')),4)
    def test_only_eight_rule_implementations_change_and_all_public_obligations_are_identical(self):
        before={json.loads(m.data)['task_id']:json.loads(m.data) for m in self.old_members if m.path.endswith('/private-scoring/contract.json')}
        changed=[]
        for row in self.new['tasks']:
            tid=row['task_id'];a,b=before[tid],self.contracts[tid]
            self.assertEqual({k:v for k,v in a.items() if k!='automated_checks'},
                             {k:v for k,v in b.items() if k!='automated_checks'},tid)
            if a['automated_checks']!=b['automated_checks']:changed.append(tid)
        self.assertEqual(len(changed),8)
        self.assertEqual(self.new['statistics'],self.old['statistics'])
    def test_native_review_admission_uses_source_and_contract_not_harness(self):
        contract=self.contracts[REVIEW.TASK]
        row=next(t for t in self.new['tasks'] if t['task_id']==REVIEW.TASK)
        sha=row['digests']['scoring_contract_sha256']
        self.assertEqual(REVIEW.profile_for(REVIEW.TASK,contract['automated_checks']),REVIEW.PROFILE)
        self.assertEqual(RUNTIME._new_native_rule_review_profile(contract,sha,{'protocol':'codex-agent-judge-v1'}),REVIEW.PROFILE)
        self.assertIsNone(RUNTIME._new_native_rule_review_profile(contract,'0'*64,{'protocol':'codex-agent-judge-v1'}))
        manifest={'identity':{'task_id':REVIEW.TASK},'digests':{'contract_sha256':sha},
            'runtime':{'rule_review_profile':REVIEW.PROFILE}}
        self.assertEqual(RUNTIME._effective_rule_source(manifest,contract['automated_checks']),
                         (contract['automated_checks'],None))
    def test_materialized_work_order_still_distinguishes_available_from_allocated(self):
        tid=next(t for t in self.contracts if '_026_work_order' in t)
        scope={};exec(compile(self.contracts[tid]['automated_checks'],'<v3-work-order>','exec'),scope)
        mapping=scope['_ge2e_work_order_mapping'](['可分摊生产工时','分摊工时'],True,{0:'actual',1:'actual'})
        self.assertEqual(mapping,{0:'available',1:'actual'})
    def test_materialized_procurement_keeps_identifiers_and_numeric_comparisons(self):
        tid=next(t for t in self.contracts if '_015_procurement' in t)
        scope={};exec(compile(self.contracts[tid]['automated_checks'],'<v3-procurement>','exec'),scope)
        self.assertEqual(scope['matched_header']('入库单号/订单号','orphan'),'receipt')
        self.assertIsNone(scope['matched_header']('入库单号/订单号','qty'))
        old=next(json.loads(m.data)['automated_checks'] for m in self.old_members
            if m.path.endswith('/private-scoring/contract.json') and json.loads(m.data)['task_id']==tid)
        grade=lambda source:ast.dump(next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='grade'))
        self.assertEqual(grade(old),grade(self.contracts[tid]['automated_checks']))
    def test_procurement_mixed_single_money_summary_retains_all_original_claims(self):
        tid=next(t for t in self.contracts if '_015_procurement' in t)
        scope={};exec(compile(self.contracts[tid]['automated_checks'],'<v3-mixed-summary>','exec'),scope)
        records={k:[] for k in ['qty','amount','missing','orphan']}
        table={'sheet':'汇总','kind':'summary','rows':[
            {'row':1,'values':['类别','笔数','金额口径','金额合计(元)','金额差额净额(元)','金额差额绝对值(元)']},
            {'row':2,'values':['数量差异',15,'数量差额',None,0,298]},
            {'row':3,'values':['金额差异',25,'金额差额',None,-1349.13,16388.85]}]}
        converted,*_=scope['_pl_matrix_view']([table],records,{'orders_amount':100,'receipts_amount':80},
            {'categories':{'amount':{'direction':-1}}},records,scope['norm'],scope['summary_key'],scope['number'])
        self.assertEqual(converted[0]['rows'],table['rows'])

class DeclaredCLIReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=REPO_ROOT/'tasks/general/work/02_Office'/f'{REVIEW.TASK}.md'
        source=parse_task_md(path)['automated_checks']
        names={'_rr_normalize','_rr_decide','_warranty_reason_matches'}
        nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
        cls.source=('import hashlib as _rr_hashlib\nimport json as _rr_json\n'+ast.unparse(ast.Module(body=nodes,type_ignores=[]))+
            '\nRULE_REVIEW_PROFILE='+repr(REVIEW.PROFILE)+'''\ndef grade(transcript,workspace_path):
    passed=_warranty_reason_matches(('SYNTHETIC','供应商甲'),{'reason':'待核查','_location':'sheet!row2'}, {'decision':'review'}, [])
    return {'unchanged_amount':0.5,'reason_category':float(passed)}
''')
    def run_workflow(self,decision=True,mutate=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);workspace=root/'workspace';workspace.mkdir();(workspace/'candidate.txt').write_text('original')
            copied={};real_run=subprocess.run;calls=[]
            def docker(argv,**kwargs):
                if argv[:2]==['docker','cp']:
                    if Path(argv[2]).is_file():copied[argv[3].split(':',1)[-1]]=Path(argv[2]).read_text()
                    return subprocess.CompletedProcess(argv,0,'','')
                self.assertEqual(argv[0:2],['docker','exec'])
                code=copied['/tmp/_grade_runner.py']
                prelude="import types,sys\nm=types.ModuleType('_transcript_loader');m.load_transcript=lambda _:[];sys.modules['_transcript_loader']=m\n"
                return real_run([sys.executable,'-X','utf8','-c',prelude+code],capture_output=True,text=True)
            def judge(task,code,path,**kwargs):
                request=json.loads(next((root/'audit/rule-review').glob('*/request.json')).read_text())
                calls.append(request)
                rows=[{'context_id':key,'status':'unresolved' if decision is None else 'judged','passed':decision,
                    'reason':'测试候选待核查类别与原行一致。','evidence_locations':['sheet!row2']} for key in request['contexts']]
                if mutate:(workspace/'candidate.txt').write_text('changed')
                return {'candidate_text':json.dumps({'decisions':rows}), 'response':{'finish_reason':'stop'}},''
            with patch.object(grading,'TMP_WORKSPACE',str(workspace)),patch.object(grading.subprocess,'run',side_effect=docker):
                result,error=REVIEW.run(REVIEW.TASK,self.source,'',None,'/trace.jsonl',output_dir=root/'audit',
                    grade=grading._exec_container_grade,judge=judge,model='synthetic-judge',max_tokens=8192)
            discovery=json.loads(next((root/'audit/rule-review').glob('*/discovery.json')).read_text())
            self.assertNotIn('unchanged_amount',discovery['result'])
            self.assertFalse(discovery['provisional_scores_published'])
            return result,error,calls
    def test_independent_boolean_replays_original_rules_without_provisional_publication(self):
        for decision,expected in [(True,1.),(False,0.)]:
            result,error,calls=self.run_workflow(decision)
            self.assertEqual(error,'');self.assertEqual(result,{'unchanged_amount':.5,'reason_category':expected})
            self.assertEqual(len(calls),1)
    def test_unknown_and_non_boolean_decisions_never_become_zero(self):
        for decision in [None,0,1]:
            result,error,_=self.run_workflow(decision)
            self.assertIsNone(result);self.assertRegex(error,'UNRESOLVED|BOOLEAN_REQUIRED')
    def test_changed_candidate_is_rejected_between_discovery_and_apply(self):
        result,error,_=self.run_workflow(True,mutate=True)
        self.assertIsNone(result);self.assertIn('RULE_REVIEW_INPUT_DRIFT',error)
