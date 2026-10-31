from copy import deepcopy
from pathlib import Path
import base64
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture,REPO_ROOT
from tests.general_e2e.test_public_office_profiles import with_cwm
from tests.general_e2e import test_general_scoring_orchestration as orchtests
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock

SNAPSHOT=RUNTIME.declared_public_snapshots


class DeclaredPublicSnapshotTests(unittest.TestCase):
    def test_exact_profiles_keep_original_score_math_and_reject_source_or_dataset_drift(self):
        for row in SNAPSHOT.registry():
            task=next((REPO_ROOT/'tasks/general_e2e').rglob(row['task_id']+'.md'));_,sections,_=_parse_task_source(task)
            source=_strip_codeblock(sections['Automated Checks']);contract={'task_id':row['task_id'],'automated_checks':source}
            marker=SNAPSHOT.marker(contract,row['contract_sha256'],row['dataset']);self.assertIsNotNone(marker)
            m={'identity':{'task_id':row['task_id']},'dataset':row['dataset'],'digests':{'contract_sha256':row['contract_sha256']},'runtime':{'declared_public_snapshot_profile':marker}}
            fixed,receipt=RUNTIME._effective_rule_source(m,source);compile(fixed,'<exact-public-snapshot>','exec')
            self.assertTrue(fixed.endswith(source.replace(
                '_digest(path)!=expected: changed.append(rel)',
                '(_digest(path)!=expected and not _ge2e_declared_public_snapshot_matches(path,rel,expected,root)): changed.append(rel)'
            ).replace('hashlib.sha256(p.read_bytes()).hexdigest()!=expected:',
                '(hashlib.sha256(p.read_bytes()).hexdigest()!=expected and not _ge2e_declared_public_snapshot_matches(p,rel,expected,root)):')))
            self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])
            self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))
            bad=deepcopy(m);bad['dataset']['digest']='0'*64
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,source)

    def test_original_text_and_strict_office_variance_preserve_bytes_in_isolated_worker(self):
        profile=SNAPSHOT.registry()[0]
        text=next(r for r in profile['files'] if r['kind']=='text-newlines');office=next(r for r in profile['files'] if r['kind']=='office-cwm-only')
        raw=(REPO_ROOT/'workspace/general_e2e/02_Office/task_018_targeted_repair_communication_pack/exec'/text['path']).read_bytes()
        self.assertTrue(SNAPSHOT.matches_bytes(text,raw));self.assertTrue(SNAPSHOT.matches_bytes(text,raw.replace(b'\n',b'\r\n')))
        self.assertFalse(SNAPSHOT.matches_bytes(text,raw+b'changed'))
        content=with_cwm(base64.b64decode(office['base64']))
        helper=Path(SNAPSHOT.office_input_compat.__file__).read_text(encoding='utf-8')
        source=helper+'\n_GE2E_SNAPSHOT_PROFILE='+repr(profile)+'\n'+SNAPSHOT.MATCHER+'\n'
        source+='def grade(transcript,workspace_path):\n    root=_ge2e_Path(workspace_path)\n    accepted=_ge2e_declared_public_snapshot_matches(root/'+repr(office['path'])+','+repr(office['path'])+','+repr(office['declared_sha256'])+',root)\n    return {"probe":float(accepted),"overall_score":float(accepted)}\n'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            try:
                attempt=Fixture(root,rule=source,candidate_files={office['path']:content}).prepare(protect_runtime_office_inputs=sys.platform=='darwin')
                result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                self.assertEqual(result['rule_component']['score'],1.)
                self.assertEqual((attempt/'runtime/workspace'/office['path']).read_bytes(),content)
                records=json.loads((attempt/'runtime/workspace'/profile['evidence_directory']/'00_public_snapshot_variance.json').read_text())
                self.assertTrue(records[0]['proof']['business_members_byte_identical']);self.assertTrue(records[0]['not_agent_action_evidence'])
                RUNTIME.verify_attempt(attempt)
            finally:RUNTIME._remove_tree(root)

    def test_completed_no_judge_baseline_failure_is_retained_and_evidence_locks_replay(self):
        orch=orchtests.ORCHESTRATOR;module=orch.framework_failure_retirement.declared_public_snapshots
        rule="def grade(transcript,workspace_path):\n return {'probe':0.,'overall_score':0.,'diagnostics':{'changed_inputs':['synthetic.txt']}}"
        adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics']}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            try:
                fixture=orchtests.Fixture(root,task_ids=('task-snapshot',),grading_type='hybrid',contract_overrides={'automated_checks':rule,'rule_result_adapter':adapter})
                orchestration=Path(fixture.initialize()['orchestration_root'])
                with patch.object(orch,'_run_score_command',side_effect=orchtests.GeneralScoringOrchestrationTests()._direct_local_score_command):
                    orch.run_rule_score_task(orchestration,task_id='task-snapshot',runtime_python=Path(sys.executable))
                    with patch.object(module,'marker',return_value={'synthetic':True}),patch.object(module,'original_failure',return_value=True):
                        view=orch.framework_failure_retirement.record(orch,orchestration,task_id='task-snapshot',reason='保留合成公开输入基线适配失败，未派发裁判，不改旧规则组件。')
                        self.assertEqual(view['unscored_count'],1);self.assertEqual(orch.status(orchestration)['unscored_count'],1)
                        orch.build_submission(orchestration)
            finally:RUNTIME._remove_tree(root)


if __name__=='__main__':unittest.main()
