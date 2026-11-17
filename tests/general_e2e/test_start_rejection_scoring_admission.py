"""Synthetic accepted-no-turn transport; no production task, GT or Judge."""
import json
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest
from tests.general_e2e.test_general_scoring_orchestration import Fixture,SCORE_RUNTIME as SCORE,REPO_ROOT,sha256_bytes
from tests.general_e2e.test_external_quota_admission import encoded


def start_rejection(f,task,*,fenced=False,tamper='none'):
    record=f.execution_records[task]
    workspace=f.unit_root/'execution/tasks'/task/'workspace';workspace.mkdir(parents=True)
    result=subprocess.run(['node',str(REPO_ROOT/'tests/general_e2e/fixtures/scoring-start-rejection.mjs'),
        str(record),str(workspace),str(fenced).lower(),tamper],capture_output=True,text=True,check=True)
    fixture=json.loads(result.stdout);execution,state=fixture['execution'],fixture['state']
    prompt=workspace.parent/'PROMPT.md';prompt.write_text(fixture['prompt'])
    state['prompt']['path']=str(prompt)
    state_path=record.parent/'execution/automation-state.json';state_path.parent.mkdir()
    state_path.write_bytes(encoded(state));record.write_bytes(encoded(execution))
    proof=f.unit_root/execution['evidence']['native_start_rejection']['path'];proof.parent.mkdir(parents=True)
    proof.write_text(fixture['proof'])
    for name,value in fixture['files'].items():proof.with_name(name).write_text(value)
    paths=[state_path,proof,*[proof.with_name(name) for name in fixture['files']]]
    manifest={'identity':execution['identity'],'artifacts':[{'path':p.relative_to(f.unit_root).as_posix(),
        'sha256':sha256_bytes(p.read_bytes()),'size':p.stat().st_size} for p in paths]}
    record.with_name('evidence-manifest.json').write_bytes(encoded(manifest))
    return execution


class StartRejectionScoringTests(unittest.TestCase):
    def test_accepted_no_model_failure_prepares_and_reverifies_without_assigning_a_score(self):
        for fenced,grading in itertools.product((False,True),('automated','hybrid','llm_judge')):
            with self.subTest(fenced=fenced,grading=grading),tempfile.TemporaryDirectory() as directory:
                f=Fixture(Path(directory),task_ids=('unregistered-start-rejection',),grading_type=grading)
                execution=start_rejection(f,f.task_ids[0],fenced=fenced)
                record=f.execution_records[f.task_ids[0]];before=record.read_bytes()
                assessment=SCORE.assess_execution(unit_root=f.unit_root,execution_record_path=record)
                self.assertEqual(assessment['disposition'],'score_original_execution')
                result=f.initialize();root=Path(result['orchestration_root'])
                task=json.loads((root/'orchestration-state.json').read_bytes())['tasks'][0]
                self.assertIsNotNone(task['attempt_path'],json.dumps(task,ensure_ascii=False))
                attempt=root/task['attempt_path']
                manifest=json.loads((attempt/'attempt-manifest.json').read_bytes())
                self.assertEqual(manifest['evidence_admission'],SCORE.execution_accountability.FAILED_ADMISSION)
                receipt=json.loads((attempt/'private/evidence-admission.json').read_bytes())
                self.assertTrue(receipt['native_message_accepted']);self.assertFalse(receipt['native_model_turn_started'])
                self.assertFalse(receipt['numeric_decisions_assigned'])
                self.assertEqual(SCORE.verify_attempt(attempt)['status'],'PASS')
                self.assertEqual(SCORE.verify_attempt(attempt,require_runtime=False)['status'],'PASS')
                self.assertEqual(record.read_bytes(),before)
                self.assertEqual(json.loads((attempt/'private/execution-record.json').read_bytes()),execution)
                self.assertFalse(list(root.rglob('score.json')))
                SCORE._remove_tree(attempt)

    def test_self_consistently_rehashed_late_turn_or_unknown_source_never_admits(self):
        for tamper in ('late-turn','unknown-source'):
            with self.subTest(tamper=tamper),tempfile.TemporaryDirectory() as directory:
                f=Fixture(Path(directory),task_ids=('reject-unsafe-evidence',))
                start_rejection(f,f.task_ids[0],fenced=True,tamper=tamper)
                result=SCORE.assess_execution(unit_root=f.unit_root,execution_record_path=f.execution_records[f.task_ids[0]])
                self.assertEqual(result['disposition'],'needs_user_decision')
                self.assertFalse(result['score_assigned'])
                initialized=f.initialize();root=Path(initialized['orchestration_root'])
                task=json.loads((root/'orchestration-state.json').read_bytes())['tasks'][0]
                self.assertIsNone(task['attempt_path'])
                self.assertEqual(task['execution_review']['disposition'],'needs_user_decision')
                self.assertFalse(list(f.unit_root.rglob('score.json')))

    def test_formal_manifest_and_native_proof_binding_cannot_be_bypassed(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(Path(directory),task_ids=('source-drift',))
            execution=start_rejection(f,f.task_ids[0],fenced=True)
            proof=f.unit_root/execution['evidence']['native_start_rejection']['path']
            proof.write_bytes(proof.read_bytes()+b' ')
            result=SCORE.assess_execution(unit_root=f.unit_root,execution_record_path=f.execution_records[f.task_ids[0]])
            self.assertEqual(result['disposition'],'needs_user_decision')
