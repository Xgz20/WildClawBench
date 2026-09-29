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

if __name__=='__main__':unittest.main()
