import hashlib,importlib.util,json,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
FILE=ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/orchestrate_general_e2e.py'
spec=importlib.util.spec_from_file_location('general_browser_preflight_test',FILE)
api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)

class BrowserPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.attempt=pathlib.Path(self.tmp.name)
        (self.attempt/'candidate-original').mkdir();(self.attempt/'candidate-original/page.html').write_text('<h1>frozen candidate</h1>',encoding='utf-8')
        self.script=self.attempt/'observation.py';self.script.write_text('# synthetic test implementation\n',encoding='utf-8')
        self.validator={'path':str(self.script),'sha256':hashlib.sha256(self.script.read_bytes()).hexdigest()}
        self.state={'prompt_protocol':api.PROMPT_PROTOCOL,'score_skill':{'browser_validator':self.validator,'runtime_lock_sha256':'a'*64}}
        self.task={'scoring_attempt_id':'new-attempt'}
        self.python={'executable':sys.executable,'executable_sha256':'b'*64,'version':[3,11,14],'utf8_mode':True}
    def tearDown(self):self.tmp.cleanup()
    def fake_probe(self,argv,**kwargs):
        self.assertIn('--probe',argv);self.assertNotIn('--html',argv)
        output=pathlib.Path(argv[argv.index('--output-dir')+1]);output.mkdir(parents=True)
        (output/'observations.json').write_text('{}',encoding='utf-8')
        return types.SimpleNamespace(returncode=0,stdout=json.dumps({'status':'PASS','candidate_used':False}),stderr='')
    def test_legacy_prompt_does_not_rewrite_its_environment_contract(self):
        self.assertTrue(api.needs_browser_preflight(self.attempt,self.state))
        self.assertFalse(api.needs_browser_preflight(self.attempt,{**self.state,'prompt_protocol':'general-e2e-codex-scoring-prompt/v6'}))
    def test_missing_runtime_blocks_before_judge_creation(self):
        with self.assertRaisesRegex(api.OrchestrationError,'JUDGE_BROWSER_RUNTIME_REQUIRED'):
            api.prepare_browser_environment(self.attempt,self.state,self.task,None,None)
        self.assertFalse((self.attempt/'judge-environment.json').exists())
    def test_public_preflight_freezes_environment_without_touching_candidate(self):
        before=(self.attempt/'candidate-original/page.html').read_bytes()
        with patch.object(api,'_score_python_lock',return_value=self.python),patch.object(api,'_run_score_command',return_value={'status':'PASS'}) as dependency,patch.object(api.subprocess,'run',side_effect=self.fake_probe):
            ref=api.prepare_browser_environment(self.attempt,self.state,self.task,pathlib.Path(sys.executable),None)
        self.assertEqual(dependency.call_args.args[1][0],'probe-runtime')
        self.assertEqual(ref['path'],'judge-environment.json')
        self.assertEqual((self.attempt/'candidate-original/page.html').read_bytes(),before)
        profile=json.loads((self.attempt/ref['path']).read_text());self.assertFalse(profile['candidate_modified']);self.assertFalse(profile['os_network_isolation_claimed'])
    def test_cached_preflight_cannot_hide_modified_observations(self):
        with patch.object(api,'_score_python_lock',return_value=self.python),patch.object(api,'_run_score_command',return_value={'status':'PASS'}),patch.object(api.subprocess,'run',side_effect=self.fake_probe):
            api.prepare_browser_environment(self.attempt,self.state,self.task,pathlib.Path(sys.executable),None)
            artifact=next((self.attempt/'judge-browser-preflight').rglob('observations.json'));artifact.write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(api.OrchestrationError,'ARTIFACT_DRIFT'):
                api.prepare_browser_environment(self.attempt,self.state,self.task,pathlib.Path(sys.executable),None)

if __name__=='__main__':unittest.main()
