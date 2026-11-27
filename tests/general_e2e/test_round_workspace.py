from pathlib import Path
import contextlib, hashlib, importlib.util, json, os, shutil, sys, tempfile, unittest, zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'tools/report/skills/general-e2e/run-general-e2e/scripts'
sys.path.insert(0,str(SCRIPTS))
import round_workspace as ROUND
import archive_round as ARCHIVE
from tests.general_e2e.test_local_scoring_runtime import Fixture, RUNTIME
from tests.general_e2e import test_general_release_prepare as PREPARE_TESTS

class TraceHandoffTests(unittest.TestCase):
    def test_copy_file_supports_shutil_copytree_string_destinations(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';target=root/'target'
            source.mkdir();(source/'trace.jsonl').write_text('{"event":"bound"}\n')
            trace_handoff = importlib.util.module_from_spec(
                importlib.util.spec_from_file_location(
                    'trace_handoff_copytree',
                    ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/trace_handoff.py',
                )
            )
            spec=trace_handoff.__spec__;assert spec and spec.loader
            spec.loader.exec_module(trace_handoff)
            shutil.copytree(source,target,copy_function=trace_handoff.copy_file)
            self.assertEqual((target/'trace.jsonl').read_text(),'{"event":"bound"}\n')

    def test_private_raw_trace_survives_source_removal_and_is_queryable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fixture(Path(d),grading_type='llm_judge',llm_judge_rubric='### Evidence (key: evidence, weight: 1.0)\nScore 1.0: correct\nScore 0.0: incorrect')
            ex=json.loads(f.execution_record.read_text());p=f.unit_root/'evidence'
            (p/'native.jsonl').write_text('{"type":"function_call","name":"read","call_id":"native-call"}\n')
            artifact=lambda name:{'path':name,'size':(p/name).stat().st_size,'sha256':hashlib.sha256((p/name).read_bytes()).hexdigest()}
            index={'identity':ex['identity'],'transcript':artifact('transcript.jsonl'),'raw_trace':[artifact('native.jsonl')]}
            (p/'trace-index.json').write_text(json.dumps(index));ex['evidence']['trace_index_path']='evidence/trace-index.json';f.execution_record.write_text(json.dumps(ex))
            attempt=f.prepare();m=json.loads((attempt/'attempt-manifest.json').read_text());self.assertIsNotNone(m['trace_bundle'])
            self.assertEqual((attempt/'trace/native.jsonl').read_bytes(),(p/'native.jsonl').read_bytes())
            shutil.rmtree(f.unit_root);RUNTIME.verify_attempt(attempt)
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
            rows=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode='catalog',evidence_type='raw_trace')['items'];self.assertEqual(len(rows),1)
            page=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode='file',evidence_id=rows[0]['id'])
            self.assertIn('native-call',json.dumps(page))
            shutil.rmtree(attempt/'runtime')
            RUNTIME.verify_attempt(attempt,require_runtime=False)
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME.verify_attempt(attempt)
            (attempt/'trace/native.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError,'TRACE_HANDOFF_ARTIFACT_DRIFT'):RUNTIME.verify_attempt(attempt,require_runtime=False)

    def test_strict_trace_gate_and_raw_source_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fixture(Path(d));ex=json.loads(f.execution_record.read_text());out=Path(d)/'copy';out.mkdir()
            with self.assertRaisesRegex(ValueError,'SCORING_TRACE_BUNDLE_REQUIRED'):
                RUNTIME.trace_handoff.freeze(f.unit_root,ex,out,required=True)
            p=f.unit_root/'evidence';(p/'native.jsonl').write_text('{}\n')
            index={'identity':ex['identity'],'transcript':{'path':'transcript.jsonl','size':1,'sha256':'0'*64},'raw_trace':[{'path':'native.jsonl','size':3,'sha256':'0'*64}]}
            (p/'trace-index.json').write_text(json.dumps(index));ex['evidence']['trace_index_path']='evidence/trace-index.json'
            with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):RUNTIME.trace_handoff.freeze(f.unit_root,ex,out,required=True)

class RoundLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):PREPARE_TESTS.GeneralReleasePrepareTests.setUpClass()
    @classmethod
    def tearDownClass(cls):PREPARE_TESTS.GeneralReleasePrepareTests.tearDownClass()

    def test_default_control_cwd_preserves_received_files_and_extracts_stable_units(self):
        with tempfile.TemporaryDirectory() as d:
            project=Path(d);(project/'received.zip').write_bytes(b'notes');(project/'README.md').write_text('user notes')
            old=Path.cwd()
            try:
                os.chdir(project)
                with contextlib.redirect_stdout(__import__('io').StringIO()):
                    result=ROUND.main(['init','--batch-root',str(PREPARE_TESTS.GeneralReleasePrepareTests.batch_root),'--prepare-skill',str(ROOT/'tools/report/skills/general-e2e/prepare-general-e2e-workspaces')])
            finally:os.chdir(old)
            self.assertEqual(result['round_root'],str(project.resolve()))
            self.assertTrue((project/'AstronStudio/execution/tasks').is_dir());self.assertTrue((project/'WorkBuddy/score/tasks').is_dir())
            self.assertFalse(list((project/'AstronStudio').rglob('private-scoring')))
            self.assertEqual((project/'README.md').read_text(),'user notes')
            with self.assertRaisesRegex(ValueError,'ALREADY_INITIALIZED'):ROUND.init_round(project,PREPARE_TESTS.GeneralReleasePrepareTests.batch_root,ROOT/'tools/report/skills/general-e2e/prepare-general-e2e-workspaces')

    def test_single_execution_zip_needs_no_early_private_scoring_package(self):
        with tempfile.TemporaryDirectory() as d:
            batch=PREPARE_TESTS.GeneralReleasePrepareTests.batch_root;archive=next(batch.rglob('*astronstudio-macos__execution.zip'))
            result=ROUND.install_unit(Path(d)/'explicit-root',archive,ROOT/'tools/report/skills/general-e2e/prepare-general-e2e-workspaces')
            root=Path(result['round_root']);self.assertTrue((root/'AstronStudio/manifest.json').exists())
            self.assertFalse((root/'.general-e2e/packages/AstronStudio/scoring.zip').exists())
            self.assertFalse(result['private_scoring_installed'])

    def test_zip_traversal_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);z=root/'bad.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('../escape','bad')
            with self.assertRaises(ValueError):ROUND.extract_zip(z,root/'out')
            self.assertFalse((root/'out').exists())

class ExternalScoringPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'round';self.root.mkdir()
        self.unit=self.root/'AstronStudio';self.unit.mkdir()
        self.scoring=self.base/'external-scoring.zip';self.scoring.write_bytes(b'frozen private ZIP')
        self.config=self.base/'report-config.json';self.config.write_text('{}',encoding='utf-8')
        ROUND.write(self.root/'.general-e2e/round.json',{'kind':'live','units':[
            {'harness':'astronstudio','directory':'AstronStudio','unit_id':'unit'}]})

    def prepare(self,**kw):
        import types
        def fake_init(command,**unused):
            self.last_init_command=command
            output=Path(command[command.index('--output-root')+1])/command[command.index('--orchestration-id')+1]
            ROUND.write(output/'orchestration-state.json',{'tasks':[]})
            return types.SimpleNamespace(returncode=0,stdout='{}',stderr='')
        with patch.object(ROUND.subprocess,'run',side_effect=fake_init):
            # Keep the test portable; cp -c is not involved in the storage policy.
            with patch.object(ROUND,'copy',side_effect=lambda src,dst:(Path(dst).parent.mkdir(parents=True,exist_ok=True),shutil.copyfile(src,dst))):
                return ROUND.prepare_score(self.root,'AstronStudio',ROOT/'tools/report/skills/general-e2e',
                    'score-fixture',report_config=self.config,**kw)

    def test_explicit_external_mode_binds_sha_and_never_caches_private_zip(self):
        original=self.scoring.read_bytes()
        result=self.prepare(scoring_package=self.scoring,keep_scoring_external=True)
        unit=ROUND.load(self.root/'.general-e2e/round.json')['units'][0]
        self.assertEqual(result['scoring_package_storage'],'external')
        self.assertEqual(unit['scoring_external'],{'path':str(self.scoring.resolve()),'sha256':ROUND.sha(self.scoring)})
        self.assertNotIn('scoring_package',unit)
        self.assertFalse(list(self.root.rglob('*.zip')))
        self.assertEqual(self.scoring.read_bytes(),original)
        self.prepare(keep_scoring_external=True)
        with self.assertRaisesRegex(ValueError,'STORAGE_MODE_DRIFT'):self.prepare(scoring_package=self.scoring)
        self.scoring.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'PACKAGE_DRIFT'):self.prepare(keep_scoring_external=True)

    def test_runtime_office_guard_is_explicit_and_preserves_external_storage(self):
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True,protect_runtime_office_inputs=True)
        self.assertIn('--protect-runtime-office-inputs',self.last_init_command)
        self.assertFalse(list(self.root.rglob('*.zip')))

    def test_explicit_execution_record_selection_is_forwarded(self):
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True,execution_records=['task=/frozen/recapture.json'])
        self.assertEqual(self.last_init_command[self.last_init_command.index('--execution-record')+1],'task=/frozen/recapture.json')

    def test_exact_sdk_final_authority_is_explicit_and_keeps_scoring_external(self):
        authority=self.base/'sdk-authority.json';authority.write_text('{"tasks":[]}',encoding='utf-8')
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True,sdk_final_authorization=authority)
        self.assertEqual(self.last_init_command[self.last_init_command.index('--sdk-final-authorization')+1],str(authority.resolve()))
        self.assertFalse(list(self.root.rglob('*.zip')))

    def test_score_slots_default_to_three_in_the_orchestrator_command(self):
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True)
        self.assertEqual(self.last_init_command[self.last_init_command.index('--score-slots')+1],'3')

    def test_four_score_slots_reach_orchestrator_without_caching_private_zip(self):
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True,score_slots=4)
        self.assertEqual(self.last_init_command[self.last_init_command.index('--score-slots')+1],'4')
        unit=ROUND.load(self.root/'.general-e2e/round.json')['units'][0]
        self.assertEqual(unit['scoring_external'],{'path':str(self.scoring.resolve()),'sha256':ROUND.sha(self.scoring)})
        self.assertNotIn('scoring_package',unit)
        self.assertFalse(list(self.root.rglob('*.zip')))

    def test_score_slots_accept_supported_range_endpoints(self):
        for slots in (1,8):
            with self.subTest(slots=slots):
                self.prepare(scoring_package=self.scoring,keep_scoring_external=True,score_slots=slots)
                self.assertEqual(self.last_init_command[self.last_init_command.index('--score-slots')+1],str(slots))

    def test_invalid_score_slots_fail_before_reading_state_or_creating_orchestration(self):
        for slots in (0,9,-1,True,4.0,'4',None):
            with self.subTest(slots=slots),patch.object(ROUND,'load') as read,patch.object(ROUND.subprocess,'run') as dispatch:
                with self.assertRaisesRegex(ValueError,'ROUND_SCORE_SLOTS_UNSUPPORTED'):
                    ROUND.prepare_score(self.root,'AstronStudio',ROOT/'tools/report/skills/general-e2e','fixture',score_slots=slots)
                read.assert_not_called()
                dispatch.assert_not_called()

    def test_both_prepare_score_clis_forward_explicit_and_default_slots(self):
        import run_general_e2e as run
        entrypoints=[(run.main,[]),(ROUND.main,['--skill-root',str(ROOT/'tools/report/skills/general-e2e')])]
        for entrypoint,extra in entrypoints:
            for supplied,expected in (([],3),(['--score-slots','4'],4)):
                with self.subTest(entrypoint=entrypoint.__module__,slots=expected):
                    args=['prepare-score','--harness','AstronStudio','--orchestration-id','fixture',*extra,*supplied]
                    with patch.object(ROUND,'prepare_score',return_value={'status':'MOCKED'}) as handoff:
                        with contextlib.redirect_stdout(__import__('io').StringIO()):entrypoint(args)
                    self.assertEqual(handoff.call_args.kwargs['score_slots'],expected)

    def test_both_prepare_score_clis_reject_invalid_slots_without_handoff(self):
        import run_general_e2e as run
        entrypoints=[(run.main,[]),(ROUND.main,['--skill-root',str(ROOT/'tools/report/skills/general-e2e')])]
        for entrypoint,extra in entrypoints:
            for value in ('0','9','four'):
                with self.subTest(entrypoint=entrypoint.__module__,value=value):
                    args=['prepare-score','--harness','AstronStudio','--orchestration-id','fixture',*extra,'--score-slots',value]
                    with patch.object(ROUND,'prepare_score') as handoff,contextlib.redirect_stderr(__import__('io').StringIO()):
                        with self.assertRaises(SystemExit):entrypoint(args)
                    handoff.assert_not_called()

    def test_runtime_office_guard_defaults_off_in_both_entrypoints(self):
        self.prepare(scoring_package=self.scoring,keep_scoring_external=True)
        self.assertNotIn('--protect-runtime-office-inputs',self.last_init_command)
        import run_general_e2e as run
        args=['prepare-score','--harness','AstronStudio','--orchestration-id','fixture']
        self.assertFalse(run.build_parser().parse_args(args).protect_runtime_office_inputs)
        self.assertTrue(run.build_parser().parse_args(args+['--protect-runtime-office-inputs']).protect_runtime_office_inputs)

    def test_default_mode_retains_existing_cache_behavior(self):
        result=self.prepare(scoring_package=self.scoring)
        self.assertEqual(result['scoring_package_storage'],'round-cache')
        self.assertEqual((self.root/'.general-e2e/packages/AstronStudio/scoring.zip').read_bytes(),self.scoring.read_bytes())
        with self.assertRaisesRegex(ValueError,'ALREADY_INTERNAL'):
            self.prepare(scoring_package=self.scoring,keep_scoring_external=True)

    def test_external_mode_rejects_missing_internal_and_symlinked_internal_paths_before_init(self):
        with self.assertRaisesRegex(ValueError,'EXTERNAL_SCORING_PACKAGE_REQUIRED'):self.prepare(keep_scoring_external=True)
        internal=self.root/'private.zip';internal.write_bytes(b'private')
        alias=self.base/'alias.zip';alias.symlink_to(internal)
        for source in (internal,alias):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError,'NOT_EXTERNAL'):
                    self.prepare(scoring_package=source,keep_scoring_external=True)
        self.assertFalse((self.unit/'score').exists())

if __name__=='__main__':unittest.main()
