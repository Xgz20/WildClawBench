import copy,unittest
import importlib.util,pathlib
_SCRIPT=pathlib.Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/compose_rescore_selection.py'
_SPEC=importlib.util.spec_from_file_location('rescore_selection_for_test',_SCRIPT)
_API=importlib.util.module_from_spec(_SPEC);_SPEC.loader.exec_module(_API)
plan_selection=_API.plan_selection

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.source={'scope':{'batch_id':'b','unit_id':'u'},'dataset':{'id':'d','digest':'f'},'task_ids':['a','b'],'tasks':[{'task_id':k,'execution_attempt_id':'exec-'+k,'candidate_sha256':'cand-'+k,'execution_status':'completed','scoring_attempt_id':'old-'+k,'score_status':'valid'} for k in ['a','b']]}
        self.source['tasks'][1]['score_status']='evaluation_error'
        self.replacement=copy.deepcopy(self.source);self.replacement['tasks']=[copy.deepcopy(self.source['tasks'][1])];self.replacement['task_ids']=['b'];self.replacement['tasks'][0].update(scoring_attempt_id='new-b',score_status='valid')
    def test_full_scope_and_order_preserved(self):
        rows=plan_selection(self.source,self.replacement,['b']);self.assertEqual([x['task_id'] for x in rows],['a','b']);self.assertEqual(rows[0],self.source['tasks'][0]);self.assertEqual(self.source['tasks'][1]['score_status'],'evaluation_error')
    def test_explicit_selection_required(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,[])
    def test_duplicate_selection_rejected(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b','b'])
    def test_unselected_replacement_rejected(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['a'])
    def test_changed_dataset_rejected(self):
        self.replacement['dataset']['digest']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_changed_execution_rejected(self):
        self.replacement['tasks'][0]['execution_attempt_id']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_changed_candidate_rejected(self):
        self.replacement['tasks'][0]['candidate_sha256']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_attempt_reuse_rejected(self):
        self.replacement['tasks'][0]['scoring_attempt_id']='old-b'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_null_not_changed_to_zero(self):
        self.replacement['tasks'][0]['score_status']='evaluation_error';self.assertEqual(plan_selection(self.source,self.replacement,['b'])[1]['score_status'],'evaluation_error')

if __name__=='__main__':unittest.main()

import json,tempfile,sys
from types import SimpleNamespace
sys.path.insert(0,str(_SCRIPT.parent))
from verify_judge_context import verify_context

class NativeContextCorrectionTests(unittest.TestCase):
    def scenario(self,change=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=pathlib.Path(temp.name).resolve();src=base/'source';rep=base/'replacement'
        for r in (src,rep):r.mkdir();(r/'execution-records').mkdir()
        scope={'batch_id':'b','unit_id':'u'};dataset={'id':'d','digest':'f'};judge={'model':'gpt-fixture','reasoning_effort':'high'};sources={k:k+'-sha' for k in ['unit_manifest_sha256','scoring_package_sha256','report_config_sha256']}
        old={'task_id':'b','phase':'THREAD_FAILED','score':None,'native_context_rejection':{'actual_effort':'medium'},'thread':{'thread_id':'old-thread','status':'COMPLETED'},'attempt_path':'attempts/old-b','scoring_attempt_id':'old-b'}
        new={'task_id':'b','phase':'SCORE_RECORDED','thread':{'thread_id':'new-thread','status':'COMPLETED'},'attempt_path':'attempts/new-b','scoring_attempt_id':'new-b','prompt_path':'prompts/b.md'}
        ss={'submission':True,'judge':judge,'sources':sources,'score_skill':{},'tasks':[old]};rs={'submission':True,'kind':'initial','judge':judge,'sources':sources,'tasks':[new]}
        original=src/old['attempt_path'];adopted=rep/new['attempt_path'];original.mkdir(parents=True);adopted.mkdir(parents=True)
        for directory in (original,adopted):(directory/'attempt-manifest.json').write_text(json.dumps({k:{'same':'frozen'} for k in ['candidate','contract','dataset','execution','task']}))
        (adopted/'score.json').write_text('{"fixed":"score"}');(src/'execution-records/a.json').write_text('{}');(src/'execution-records/b.json').write_text('{}')
        a={'task_id':'a','execution_attempt_id':'exec-a','candidate_sha256':'cand-a','execution_status':'completed','scoring_attempt_id':None,'score_status':'unscored','score_path':None}
        b={'task_id':'b','execution_attempt_id':'exec-b','candidate_sha256':'cand-b','execution_status':'completed','scoring_attempt_id':None,'score_status':'unscored','score_path':None}
        selected=dict(b,scoring_attempt_id='new-b',score_status='valid',score_path='attempts/new-b/score.json',score_sha256=_API.digest(adopted/'score.json'))
        source={'scope':scope,'dataset':dataset,'task_ids':['a','b'],'tasks':[a,b]};replacement={'scope':scope,'dataset':dataset,'task_ids':['b'],'tasks':[selected]}
        (src/'submission.json').write_text(json.dumps(source));(rep/'submission.json').write_text(json.dumps(replacement));(rep/'prompts').mkdir();(rep/new['prompt_path']).write_text('frozen prompt')
        cwd=str(adopted.resolve());sdk=base/'native.jsonl';rows=[{'type':'session_meta','payload':{'id':'new-thread','cwd':cwd,'runtime_workspace_roots':[cwd]}},{'type':'turn_context','payload':{'model':'gpt-fixture','effort':'high','cwd':cwd}},{'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'frozen prompt'}]}},{'type':'event_msg','payload':{'type':'task_started','turn_id':'t'}},{'type':'event_msg','payload':{'type':'task_complete','turn_id':'t'}}];sdk.write_text(''.join(json.dumps(x)+'\n' for x in rows));proof=verify_context(sdk,thread_id='new-thread',cwd=cwd,model='gpt-fixture',effort='high',prompt='frozen prompt');proof_path=base/'proof.json';proof_path.write_text(json.dumps(proof))
        if change=='valid-old':old['score']={'sha256':'valid'}
        elif change=='no-rejection':old.pop('native_context_rejection')
        elif change=='wrong-native':rows[1]['payload']['effort']='medium';sdk.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        for r,s in [(src,ss),(rep,rs)]:(r/'orchestration-state.json').write_text(json.dumps(s))
        frozen=SimpleNamespace(_verify_state=lambda r:ss if r==src else rs,_run_score_command=lambda *a,**k:{'score_valid':True},_validate_contract=lambda *a,**k:None,SUBMISSION_SCHEMA='schema')
        args=SimpleNamespace(source=src,replacement=rep,task_id=['b'],output_root=base/'selected',allow_native_context_correction=True,native_context_proof=proof_path)
        return args,frozen
    def test_explicit_unadmitted_correction_keeps_unscored_rows_and_originals(self):
        args,frozen=self.scenario();before=(args.source/'submission.json').read_bytes();result=_API.compose(args,frozen=frozen);d=json.loads((args.output_root/'submission.json').read_text());self.assertEqual(d['task_ids'],['a','b']);self.assertIsNone(d['tasks'][0]['score_path']);self.assertEqual(d['tasks'][1]['score_status'],'valid');self.assertEqual((args.source/'submission.json').read_bytes(),before);self.assertFalse((args.output_root/'orchestration-state.json').exists());self.assertEqual(result['task_count'],2)
    def test_valid_old_score_missing_rejection_and_wrong_actual_judge_fail(self):
        for kind in ['valid-old','no-rejection','wrong-native']:
            with self.subTest(kind=kind):
                args,frozen=self.scenario(kind)
                with self.assertRaises(ValueError):_API.compose(args,frozen=frozen)
