import ast,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from src.utils.task_parser import parse_task_md as _parse_task_md
from eval_general_e2e.datasets.source_history import frozen_v2_task_path

def parse_task_md(path):
    # These regressions exercise the immutable v2 correction profiles.
    return _parse_task_md(frozen_v2_task_path(path))

sys.path.insert(0,str(REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts'))
import communication_evidence_failure as FAILURE
B=RUNTIME.work_order_evidence_budget

class CommunicationEvidenceBudgetTests(unittest.TestCase):
    def test_weekly_and_consolidation_profiles_only_change_total_resource_guard(self):
        for task,(sha,source_sha,_,limit) in B.EXTRA.items():
            source=parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{task}.md')['automated_checks']
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),source_sha)
            marker=B.marker({'task_id':task,'automated_checks':source},sha)
            m={'identity':{'task_id':task},'digests':{'contract_sha256':sha},'runtime':{'work_order_evidence_budget_profile':marker}}
            fixed,receipt=B.effective_source(m,source,source,None)
            expected=source.replace("    total=sum(len(p.read_text(encoding='utf-8')) for p in evidence.iterdir())\n    if total>"+str(limit)+':',"    total=sum(p.stat().st_size for p in evidence.iterdir())\n    if total>16777216:")
            self.assertEqual(fixed,expected);self.assertFalse(receipt['candidate_rewritten'])
    def test_prd_budget_has_exact_identity_and_does_not_modify_other_functions(self):
        source=parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{B.PRD_TASK}.md')['automated_checks']
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),B.PRD_SOURCE)
        marker=B.marker({'task_id':B.PRD_TASK,'automated_checks':source},B.PRD_CONTRACT)
        m={'identity':{'task_id':B.PRD_TASK},'digests':{'contract_sha256':B.PRD_CONTRACT},'runtime':{'work_order_evidence_budget_profile':marker}}
        fixed,receipt=B.effective_source(m,source,source,None)
        self.assertIn("sum(len(v.encode('utf-8')) for v in serialized)",fixed)
        self.assertIn('if total>16777216:',fixed);self.assertFalse(receipt['candidate_rewritten'])
        for node in ast.parse(source).body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='grade':
                other=next(n for n in ast.parse(fixed).body if isinstance(n,type(node)) and n.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(other))
        error={'ok':False,'result':None,'error':{'type':'RuntimeError','message':'EVALUATOR_EVIDENCE_BUDGET: 85080 characters require larger collection budget; do not truncate or score a partial plan'}}
        contract={'task_id':B.PRD_TASK,'automated_checks':source};audit={'status':'failed'}
        self.assertTrue(FAILURE.prd_failure(m,contract,audit,error))
        error['error']['message']='unrelated failure';self.assertFalse(FAILURE.prd_failure(m,contract,audit,error))
    def test_only_total_resource_guard_changes_and_original_chunker_stays_exact(self):
        source=parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{B.PACK_TASK}.md')['automated_checks']
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),B.PACK_SOURCE)
        marker=B.marker({'task_id':B.PACK_TASK,'automated_checks':source},B.PACK_CONTRACT)
        m={'identity':{'task_id':B.PACK_TASK},'digests':{'contract_sha256':B.PACK_CONTRACT},'runtime':{'work_order_evidence_budget_profile':marker}}
        fixed,receipt=B.effective_source(m,source,source,None)
        self.assertEqual(receipt['correction_id'],B.PACK_PROFILE);self.assertFalse(receipt['candidate_rewritten'])
        before,after=ast.parse(source),ast.parse(fixed)
        for node in before.body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='grade':
                other=next(n for n in after.body if isinstance(n,type(node)) and n.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(other))
        self.assertIn('if size>16777216:',fixed);self.assertIn('if len(text)>18000:',fixed)
        self.assertIsNone(B.marker({'task_id':B.PACK_TASK,'automated_checks':source+'\n'},B.PACK_CONTRACT))
    def fixture(self,root):
        source='synthetic source'
        m={'digests':{'contract_sha256':FAILURE.CONTRACT},'runtime':{'workspace_argument':'runtime/workspace'}}
        contract={'task_id':FAILURE.TASK,'automated_checks':source};audit={'status':'failed'}
        worker={'ok':False,'result':None,'error':{'type':'EvidenceError','message':FAILURE.ERROR}}
        folder=root/'runtime/workspace/evaluator_evidence_018';folder.mkdir(parents=True)
        for i in range(6):
            name='00_manifest.json' if i==0 else f'10_candidate_001_{i:03d}.json'
            (folder/name).write_text(json.dumps({'truncated':False,'text':'x'*14000}))
        return m,contract,audit,worker
    def test_retains_every_old_file_and_rejects_changed_or_truncated_evidence(self):
        with tempfile.TemporaryDirectory() as d,patch.object(FAILURE,'SOURCE',hashlib.sha256(b'synthetic source').hexdigest()):
            root=Path(d).resolve();m,c,a,w=self.fixture(root)
            rt=SimpleNamespace(_sha256_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),_read_json=lambda p:json.loads(p.read_text()),
                _write_new_json=lambda p,v:p.write_text(json.dumps(v)))
            originals=FAILURE.files(root,m,c,a,w);before={p.name:p.read_bytes() for p in originals}
            binding=FAILURE.preserve(rt,root,m,c,a,w);FAILURE.verify(rt,root,m,c,a,w,binding)
            self.assertEqual(before,{p.name:p.read_bytes() for p in originals})
            copied=root/FAILURE.PRESERVED/'10_candidate_001_001.json';copied.write_text(json.dumps({'truncated':True}))
            with self.assertRaises(ValueError):FAILURE.verify(rt,root,m,c,a,w,binding)
            wrong=dict(w,error={'type':'RuntimeError','message':'unrelated'})
            self.assertIsNone(FAILURE.files(root,m,c,a,wrong))
