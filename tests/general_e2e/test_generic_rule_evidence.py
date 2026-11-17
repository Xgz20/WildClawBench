"""Ordinary rule evidence custody; no Office/HTML capability or business oracle."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,unittest,zipfile
from tests.general_e2e.test_local_scoring_runtime import Fixture,RUNTIME,REPO_ROOT,LOCK_PATH,load_module

RULE='''
def grade(transcript, workspace_path):
    import json, os
    from pathlib import Path
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    (derived/'observations.json').write_text(json.dumps({'custody_only': True, 'business_success': False}))
    return {'fixture': 1., 'overall_score': 1.}
'''
RUBRIC='### Criterion 1: evidence (key: fixture, weight: 1.0)\n**Score 1.0**: inspectable.\n**Score 0.0**: absent.'

class GenericRuleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='generic-rule-evidence-');self.root=Path(self.temp.name)
        self.venv=self.root/'worker';subprocess.run([sys.executable,'-m','venv','--without-pip',str(self.venv)],check=True,capture_output=True)
        self.python=self.venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        lock=json.loads(LOCK_PATH.read_text());lock.update(python={'major':sys.version_info.major,'minor':sys.version_info.minor},dependencies=[])
        self.lock=self.root/'runtime-lock.json';self.lock.write_text(json.dumps(lock))
    def tearDown(self):self.temp.cleanup()
    def prepare(self,name='fixture',rule=RULE,hybrid=False):
        f=Fixture(self.root/name,rule=rule,grading_type='hybrid' if hybrid else 'automated',grading_weights={'automated':.75,'llm_judge':.25} if hybrid else {},llm_judge_rubric=RUBRIC if hybrid else '')
        p=RUNTIME.prepare_attempt(unit_root=f.unit_root,execution_record_path=f.execution_record,scoring_package=f.scoring_package,task_id=f.task_id,scoring_attempt_id=name,output_root=f.output_root,runtime_lock_path=self.lock,**({'judge_protocol':'codex-agent-judge-v1','judge_model':'fixture','judge_reasoning_effort':'high','judge_attempt_id':name} if hybrid else {}))
        return Path(p['attempt_root'])
    def execute(self,p):return RUNTIME.run_rules_attempt(attempt_root=p,runtime_python=self.python,timeout_seconds=20)
    def test_ordinary_rule_receipt_semantic_catalog_query_and_archive_custody(self):
        p=self.prepare(hybrid=True);result=self.execute(p)
        self.assertNotIn('office_runtime',result['audit']['worker']);self.assertNotIn('html_runtime',result['audit']['worker'])
        self.assertEqual(result['audit']['derived_artifacts'][0]['path'],'worker/derived/observations.json')
        self.assertEqual(result['audit']['derived_evidence']['schema_version'],'wildclawbench.rule-derived-evidence/v1')
        RUNTIME.prepare_semantics_attempt(attempt_root=p)
        catalog=json.loads((p/'semantic/evidence-catalog.json').read_text());paths={r['reference'].get('path') for r in catalog['evidence_index']['entries']}
        self.assertIn('worker/derived/observations.json',paths)
        entry=next(r for r in catalog['evidence_index']['entries'] if r['reference'].get('path')=='worker/derived/observations.json')
        query=RUNTIME.query_evidence_attempt(attempt_root=p,mode='file',evidence_id=entry['id'])
        self.assertIn('custody_only',json.dumps(query));self.assertTrue(RUNTIME.verify_attempt(p)['status']=='PASS')
        moved=self.root/'moved';shutil.copytree(p,moved,ignore=shutil.ignore_patterns('runtime'))
        self.assertEqual(RUNTIME.verify_attempt(moved,require_runtime=False)['status'],'PASS')
        artifact=moved/'worker/derived/observations.json';artifact.write_text('changed')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RULE_DERIVED_ARTIFACT_DRIFT'):RUNTIME.verify_attempt(moved,require_runtime=False)
    def test_unindexed_files_and_links_fail_instead_of_being_dropped(self):
        for kind in ['extra','link','directory-link']:
            with self.subTest(kind=kind):
                p=self.prepare(kind);self.execute(p);d=p/'worker/derived'
                if kind=='extra':(d/'unindexed.json').write_text('{}')
                elif kind=='link':(d/'link.json').symlink_to(p/'private/contract.json')
                else:(d/'linked-folder').symlink_to(p/'private',target_is_directory=True)
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RULE_DERIVED_'):RUNTIME.verify_attempt(p)
        for mode in ['directory-link']:
            source=RULE.replace("(derived/'observations.json').write_text(json.dumps({'custody_only': True, 'business_success': False}))", "(derived/'escaped').symlink_to(Path(workspace_path)/'gt',target_is_directory=True)")
            p=self.prepare('worker-link-'+mode,rule=source)
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RULE_DERIVED_'):self.execute(p)
            self.assertTrue((p/'worker/derived/escaped').is_symlink())
    def test_legacy_empty_audit_and_sealed_archive_zip_remain_supported(self):
        p=self.prepare('legacy',rule="def grade(transcript, workspace_path):\n return {'fixture':1.,'overall_score':1.}")
        self.execute(p);audit=json.loads((p/'rule-audit.json').read_text());audit.pop('derived_evidence',None);audit.pop('derived_artifacts',None);(p/'rule-audit.json').write_text(json.dumps(audit))
        self.assertEqual(RUNTIME.verify_attempt(p)['status'],'PASS')
        p=self.prepare('archive');self.execute(p);RUNTIME.prepare_semantics_attempt(attempt_root=p);RUNTIME.finalize_score_attempt(attempt_root=p)
        self.assertTrue(RUNTIME.verify_score_attempt(p,archived=True)['score_valid'])
        builder=load_module('generic_evidence_skill_builder',REPO_ROOT/'tools/e2e-build/build_skill_packages.py');dist=self.root/'dist'
        built=builder.build_skill_package(REPO_ROOT,dist,'score-general-e2e',source_revision='a'*40)
        with zipfile.ZipFile(dist/built['archive']) as z:z.extractall(self.root/'installed')
        moved=self.root/'zip-moved';shutil.copytree(p,moved,ignore=shutil.ignore_patterns('runtime'))
        script=self.root/'installed/score-general-e2e/scripts/score_general_e2e.py'
        output=subprocess.run([sys.executable,'-I',str(script),'verify-score','--attempt-root',str(moved),'--archived'],capture_output=True,text=True,cwd=self.root)
        self.assertEqual(output.returncode,0,output.stdout+output.stderr)

    def test_receipt_member_size_and_paths_are_checked(self):
        p=self.prepare('index');self.execute(p);path=p/'rule-audit.json';original=path.read_text()
        for kind in ['receipt','size','escape','duplicate']:
            with self.subTest(kind=kind):
                audit=json.loads(original)
                if kind=='receipt':audit['derived_evidence']['file_count']+=1
                elif kind=='size':audit['derived_artifacts'][0]['size']+=1
                elif kind=='escape':audit['derived_artifacts'][0]['path']='worker/derived/../../private/contract.json'
                else:audit['derived_artifacts'].append(dict(audit['derived_artifacts'][0]))
                path.write_text(json.dumps(audit))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RULE_DERIVED_'):RUNTIME.verify_attempt(p)
        path.write_text(original)

if __name__=='__main__':unittest.main()
