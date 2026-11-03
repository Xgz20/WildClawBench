import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from tests.general_e2e.test_source_office_metadata import office
path=REPO_ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/runtime_office_guard.py'
spec=importlib.util.spec_from_file_location('runtime_guard_test',path);M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
class RuntimeOfficeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.original=self.root/'candidate-original/workspace';self.runtime=self.root/'runtime/workspace'
        for folder in (self.original,self.runtime):folder.mkdir(parents=True);(folder/'output.docx').write_bytes(office())
        (self.runtime/'evaluator.txt').write_text('original rule evidence')
        _,source=RUNTIME._inventory_tree(self.original);_,self.expected=RUNTIME._inventory_tree(self.runtime)
        self.manifest={'schema_version':RUNTIME.ATTEMPT_SCHEMA,'identity':{'task_id':'synthetic'},'digests':{'candidate_original_sha256':source},'paths':{'candidate_original':'candidate-original/workspace','runtime_workspace':'runtime/workspace'}}
        self.audit={'status':'completed','identity':self.manifest['identity'],'runtime_workspace':{'final_sha256':self.expected}}
        for name,data in [('attempt-manifest.json',self.manifest),('rule-audit.json',self.audit),('rule-component.json',{'original':True}),('score.json',{'original_valid_score':True})]:
            (self.root/name).write_text(json.dumps(data))
        self.output=self.root/'infrastructure-evidence/runtime-office-recoveries/one'
    def tearDown(self):
        if hasattr(os,'chflags'):
            for p in self.root.rglob('*'):
                if p.is_file() and not p.is_symlink():os.chflags(p,0)
        self.tmp.cleanup()
    def test_exact_postrule_digest_recovered_with_all_original_scores_and_variants_retained(self):
        before=(self.root/'score.json').read_bytes();variant=office(marker=True);(self.runtime/'output.docx').write_bytes(variant)
        result=M.recover(RUNTIME,self.root,self.output)
        self.assertEqual(result['status'],'PASS');self.assertEqual(RUNTIME._inventory_tree(self.runtime)[1],self.expected)
        self.assertEqual((self.root/'score.json').read_bytes(),before)
        self.assertEqual((self.output/'000-variant.bin').read_bytes(),variant)
        guarded=M.guard(RUNTIME,self.root,self.root/'infrastructure-evidence/guard.json');self.assertEqual(len(guarded['files']),1)
        if hasattr(os,'chflags'):self.assertTrue((self.runtime/'output.docx').stat().st_flags & 2)
    def test_unrelated_or_business_drift_never_recovered(self):
        (self.runtime/'output.docx').write_bytes(office(marker=True));(self.runtime/'evaluator.txt').write_text('different evidence')
        with self.assertRaisesRegex(ValueError,'EXACT_FINAL_TREE'):M.recover(RUNTIME,self.root,self.output)
        self.assertFalse(self.output.exists())
        (self.runtime/'evaluator.txt').write_text('original rule evidence');(self.runtime/'output.docx').write_bytes(office(marker=True,business='changed'))
        with self.assertRaises(ValueError):M.recover(RUNTIME,self.root,self.output)
        self.assertFalse(self.output.exists())
