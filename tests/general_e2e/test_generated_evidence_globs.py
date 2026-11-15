from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT,Fixture
from tests.general_e2e import test_general_scoring_orchestration as orchestration_tests

GLOBS=RUNTIME.generated_evidence_globs
ORCHESTRATOR=orchestration_tests.ORCHESTRATOR
PATTERN='evaluator_evidence/source_*.txt'
DECLARATIONS={'required':[{'path':'evaluator_evidence/index.json','role':'grader_generated_evidence'},
                         {'path':PATTERN,'role':'frozen_source_pages'}]}
RULE='''from pathlib import Path
def grade(transcript,workspace_path):
    folder=Path(workspace_path)/'evaluator_evidence';folder.mkdir()
    for number in range(1,4):(folder/f'source_{number:02}.txt').write_text('完整合成源文 '+str(number),encoding='utf-8')
    (folder/'index.json').write_text('{"synthetic":true}',encoding='utf-8')
    return {'accuracy':1.,'overall_score':1.}
'''


def synthetic_policy(manifest,contract):
    if not any(e.get('path')==PATTERN for e in (contract.get('judge_evidence') or {}).get('required',[])):return None
    return {'task_id':manifest['identity']['task_id'],'contract_sha256':manifest['digests']['contract_sha256'],
        'source_sha256':hashlib.sha256(contract['automated_checks'].encode()).hexdigest(),'patterns':[PATTERN]}


class GeneratedEvidenceGlobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    def tearDown(self):
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def test_both_standalone_skills_have_identical_exact_contract_catalog_and_helper(self):
        skills=REPO_ROOT/'tools/report/skills/general-e2e'
        for file in ['scripts/generated_evidence_globs.py','data/reviewed-generated-file-globs-v1.json','data/reviewed-generated-file-globs-v2.json']:
            self.assertEqual((skills/'score-general-e2e'/file).read_bytes(),(skills/'orchestrate-general-e2e'/file).read_bytes())
        dataset=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom116-v1.json').read_text())
        self.assertEqual(len(GLOBS.registry()),4)
        for row in GLOBS.registry():
            task=next(t for t in dataset['tasks'] if t['task_id']==row['task_id'])
            self.assertEqual(task['digests']['scoring_contract_sha256'],row['contract_sha256'])
        self.assertIsNone(GLOBS.policy({'identity':{'task_id':'other'}},{'automated_checks':None}))

    def test_revised70_globs_bind_new_contracts_without_changing_old_catalog_or_rules(self):
        from src.utils.task_parser import parse_task_md
        dataset=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v2.json').read_text())
        previous={r['task_id']:r for r in GLOBS.registry()}
        rows=GLOBS.registry('general-custom70-v2');self.assertEqual(len(rows),4)
        for row in rows:
            task=next(t for t in dataset['tasks'] if t['task_id']==row['task_id'])
            self.assertEqual(row['contract_sha256'],task['digests']['scoring_contract_sha256'])
            self.assertEqual(row['dataset'],{'id':dataset['dataset_id'],'digest':dataset['dataset_digest']})
            self.assertEqual(row['patterns'],previous[row['task_id']]['patterns'])
            self.assertEqual(row['source_sha256'],previous[row['task_id']]['source_sha256'])
            parsed=parse_task_md(REPO_ROOT/task['source']['task_path'])
            contract={'task_id':row['task_id'],'automated_checks':parsed['automated_checks'],'judge_evidence':parsed['judge_evidence']}
            manifest={'identity':{'task_id':row['task_id']},'digests':{'contract_sha256':row['contract_sha256']},'dataset':row['dataset']}
            self.assertEqual(GLOBS.policy(manifest,contract),row)
            self.assertEqual(GLOBS.descriptor(manifest,contract)['catalog_sha256'],GLOBS.CATALOG_V2_SHA)
            contract['automated_checks']+='\n# drift'
            self.assertIsNone(GLOBS.policy(manifest,contract))

    def test_v6_catalog_binds_all_four_unchanged_contracts_and_rejects_dataset_drift(self):
        dataset=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v6.json').read_text())
        previous={r['task_id']:r for r in GLOBS.registry('general-custom70-v5')}
        rows=GLOBS.registry('general-custom70-v6')
        self.assertEqual(len(rows),4)
        from src.utils.task_parser import parse_task_md
        for row in rows:
            task=next(t for t in dataset['tasks'] if t['task_id']==row['task_id'])
            self.assertEqual(row['contract_sha256'],task['digests']['scoring_contract_sha256'])
            self.assertEqual(row['source_sha256'],previous[row['task_id']]['source_sha256'])
            parsed=parse_task_md(REPO_ROOT/task['source']['task_path'])
            contract={'task_id':row['task_id'],'automated_checks':parsed['automated_checks'],'judge_evidence':parsed['judge_evidence']}
            manifest={'identity':{'task_id':row['task_id']},'digests':{'contract_sha256':row['contract_sha256']},'dataset':row['dataset']}
            self.assertEqual(GLOBS.policy(manifest,contract),row)
            manifest['dataset']={**row['dataset'],'digest':'0'*64}
            self.assertIsNone(GLOBS.policy(manifest,contract))
        skills=REPO_ROOT/'tools/report/skills/general-e2e'
        for name in ['scripts/generated_evidence_globs.py','data/reviewed-generated-file-globs-v6.json']:
            self.assertEqual((skills/'score-general-e2e'/name).read_bytes(),(skills/'orchestrate-general-e2e'/name).read_bytes())

    def test_managed_producer_collects_every_match_and_archived_score_stays_verifiable(self):
        fixture=Fixture(self.root/'fixture',rule=RULE,contract_overrides={'judge_evidence':DECLARATIONS})
        with patch.object(GLOBS,'policy',side_effect=synthetic_policy):
            attempt=fixture.prepare()
            RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
            proof=RUNTIME.verify_attempt(attempt)
            self.assertEqual(proof['generated_evidence_glob_reader']['patterns'],[PATTERN])
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
            snapshot=json.loads((attempt/'grader-evidence/manifest.json').read_text())
            self.assertEqual({Path(f['path']).name for f in snapshot['files']},
                {'index.json','source_01.txt','source_02.txt','source_03.txt'})
            RUNTIME.finalize_score_attempt(attempt_root=attempt)
            RUNTIME._remove_tree(attempt/'runtime')
            self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_zero_matches_do_not_create_placeholder_or_accept_incomplete_evidence(self):
        no_sources=RULE.replace('range(1,4)','range(1,1)')
        fixture=Fixture(self.root/'fixture',rule=no_sources,contract_overrides={'judge_evidence':DECLARATIONS})
        with patch.object(GLOBS,'policy',side_effect=synthetic_policy):
            attempt=fixture.prepare()
            RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'JUDGE_EVIDENCE_MISSING'):
                RUNTIME.verify_attempt(attempt)
            self.assertFalse((attempt/'grader-evidence').exists())

    def test_existing_candidate_match_is_a_collision_before_worker_runs(self):
        fixture=Fixture(self.root/'fixture',rule=RULE,contract_overrides={'judge_evidence':DECLARATIONS},
            candidate_files={'evaluator_evidence/source_01.txt':b'candidate supplied'})
        with patch.object(GLOBS,'policy',side_effect=synthetic_policy):
            attempt=fixture.prepare()
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'TARGET_COLLISION'):
                RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
            self.assertFalse((attempt/'worker').exists())

    def test_parent_link_matching_link_and_directory_are_rejected_and_exact_paths_stay_literal(self):
        workspace=self.root/'workspace';workspace.mkdir();outside=self.root/'outside';outside.mkdir()
        manifest={'identity':{'task_id':'fixture'},'digests':{'contract_sha256':'a'*64}}
        contract={'automated_checks':RULE,'judge_evidence':DECLARATIONS}
        with patch.object(GLOBS,'policy',side_effect=synthetic_policy):
            (workspace/'evaluator_evidence').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):GLOBS.targets(workspace,PATTERN,manifest,contract)
            (workspace/'evaluator_evidence').unlink();(workspace/'evaluator_evidence').mkdir()
            path=workspace/'evaluator_evidence/source_01.txt';path.symlink_to(outside/'secret.txt')
            with self.assertRaises(ValueError):GLOBS.targets(workspace,PATTERN,manifest,contract)
            path.unlink();path.mkdir()
            with self.assertRaises(ValueError):GLOBS.targets(workspace,PATTERN,manifest,contract)
        self.assertEqual(GLOBS.targets(workspace,'literal.txt',{},{}),[workspace/'literal.txt'])
        self.assertEqual(GLOBS.targets(workspace,PATTERN,{},{}),[workspace/PATTERN])

    def test_old_valid_worker_is_retired_with_readonly_proof_and_not_reexecuted_or_scored(self):
        fixture=orchestration_tests.Fixture(self.root/'orchestration',task_ids=('task-glob',),grading_type='hybrid',
            contract_overrides={'automated_checks':RULE,'judge_evidence':DECLARATIONS})
        view=fixture.initialize();root=Path(view['orchestration_root'])
        reader=self.root/'new-reader';shutil.copytree(orchestration_tests.SCORE_SKILL,reader)
        direct=orchestration_tests.GeneralScoringOrchestrationTests()._direct_local_score_command
        def command(lock,args,**kwargs):
            path=Path(args[args.index('--attempt-root')+1])
            if args[0]=='verify' and lock['path']==str(orchestration_tests.SCORE_SKILL) and (path/'rule-component.json').exists():
                raise ORCHESTRATOR.OrchestrationError('SCORE_SKILL_COMMAND_FAILED',json.dumps({'error':{'code':'JUDGE_EVIDENCE_MISSING','detail':PATTERN},'status':'FAIL'}))
            return direct(lock,args,**kwargs)
        with patch.object(GLOBS,'policy',side_effect=synthetic_policy),patch.object(ORCHESTRATOR,'_run_score_command',side_effect=command):
            with self.assertRaises(ORCHESTRATOR.OrchestrationError):
                ORCHESTRATOR.run_rule_score_task(root,task_id='task-glob',runtime_python=Path(sys.executable))
            state=json.loads((root/'orchestration-state.json').read_text());attempt=root/state['tasks'][0]['attempt_path']
            before={f.relative_to(attempt).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in attempt.rglob('*') if f.is_file()}
            retained=ORCHESTRATOR.record_unscored_evidence_glob_error(root,task_id='task-glob',verifier_score_skill_dir=reader,
                reason='保留真实规则结果和原始证据，新的读取器仅修复已声明文件通配符，另建修复评分。')
            self.assertEqual(retained['tasks'][0]['phase'],'UNSCORED')
            self.assertEqual(before,{f.relative_to(attempt).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in attempt.rglob('*') if f.is_file()})
            self.assertFalse((attempt/'score.json').exists());self.assertFalse((attempt/'semantic').exists())
            self.assertEqual(ORCHESTRATOR.status(root)['unscored_count'],1)
            built=ORCHESTRATOR.build_submission(root)
            self.assertEqual(json.loads(Path(built['submission_path']).read_text())['tasks'][0]['score_status'],'unscored')
            receipt=next((root/'evidence-glob-repair').glob('*.json'))
            receipt.write_bytes(receipt.read_bytes()+b'changed')
            with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError,'EVIDENCE_GLOB_REPAIR_RECEIPT_INVALID'):
                ORCHESTRATOR.status(root)


if __name__=='__main__':unittest.main()
