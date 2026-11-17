"""Synthetic accepted-completion/later-runtime-stop; no production grading."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from tests.general_e2e.test_general_scoring_orchestration import Fixture,SCORE_RUNTIME as SCORE,REPO_ROOT
from tests.general_e2e.test_external_quota_admission import encoded

def completed_then_interrupted(f,task):
    record=f.execution_records[task];cwd=f.unit_root/'execution/tasks'/task/'workspace';cwd.mkdir(parents=True)
    result=subprocess.run(['node',str(REPO_ROOT/'tests/general_e2e/fixtures/scoring-completed-sdk-interruption.mjs'),str(record),str(cwd)],capture_output=True,text=True,check=True)
    data=json.loads(result.stdout);execution=data['execution'];trace=record.parent/'trace';trace.mkdir()
    for name,value in data['files'].items():
        p=trace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
    (trace/'trace-index.json').write_bytes(encoded(data['index']))
    execution['evidence']['trace_index_path']=(trace/'trace-index.json').relative_to(f.unit_root).as_posix()
    execution['evidence']['transcript_path']=(trace/'transcript.jsonl').relative_to(f.unit_root).as_posix()
    record.write_bytes(encoded(execution));return execution

class CompletedSdkInterruptionAdmissionTests(unittest.TestCase):
    def test_prepares_all_original_grading_types_and_replays_both_terminals(self):
        for grading in ('automated','hybrid','llm_judge'):
            with self.subTest(grading=grading),tempfile.TemporaryDirectory() as directory:
                f=Fixture(Path(directory),task_ids=('completed-then-interrupted',),grading_type=grading)
                execution=completed_then_interrupted(f,f.task_ids[0]);record=f.execution_records[f.task_ids[0]];before=record.read_bytes()
                decision=SCORE.assess_execution(unit_root=f.unit_root,execution_record_path=record)
                self.assertEqual(decision['disposition'],'score_original_execution')
                result=f.initialize();root=Path(result['orchestration_root']);task=json.loads((root/'orchestration-state.json').read_bytes())['tasks'][0]
                self.assertIsNotNone(task['attempt_path'],json.dumps(task,ensure_ascii=False));attempt=root/task['attempt_path']
                receipt=json.loads((attempt/'private/evidence-admission.json').read_bytes())
                self.assertTrue(receipt['model_sdk_final_present']);self.assertFalse(receipt['client_display_of_sdk_final_verified'])
                self.assertFalse(receipt['numeric_decisions_assigned']);self.assertFalse(receipt['proof']['sdk_interruption_confirmed'])
                self.assertEqual(SCORE.verify_attempt(attempt,require_runtime=False)['status'],'PASS')
                self.assertEqual(record.read_bytes(),before);self.assertFalse(list(root.rglob('score.json')))
                SCORE._remove_tree(attempt)

    def test_original_numeric_rule_reads_the_retained_sdk_final_without_a_forced_zero(self):
        rule="""def grade(transcript, workspace_path):
    finals=[r.get('content') for r in transcript if r.get('type')=='assistant_message' and r.get('final') is True]
    value=0.75 if finals==['retained SDK final'] else 0.0
    return {'candidate_work':value,'overall_score':value}
"""
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(Path(directory),task_ids=('numeric-unchanged',),grading_type='automated',contract_overrides={'automated_checks':rule})
            completed_then_interrupted(f,f.task_ids[0]);result=f.initialize();root=Path(result['orchestration_root']);task=json.loads((root/'orchestration-state.json').read_bytes())['tasks'][0];attempt=root/task['attempt_path']
            rules=SCORE.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
            self.assertEqual(rules['rule_component']['score'],0.75)
            self.assertEqual(json.loads((attempt/'private/contract.json').read_bytes())['automated_checks'],rule)
            SCORE._remove_tree(attempt)
