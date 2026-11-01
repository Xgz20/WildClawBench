from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts'
sys.path.insert(0,str(ROOT))
SPEC=importlib.util.spec_from_file_location('valid_rescore_composer_test',ROOT/'compose_full_scope_selection.py')
COMPOSE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(COMPOSE)


class ValidRescoreSourceTests(unittest.TestCase):
    def fixture(self):
        old={'score_status':'valid','score_sha256':'old-score','scoring_attempt_id':'old',
             'candidate_sha256':'candidate','execution_attempt_id':'exec'}
        digests={key:key+'-sha' for key in ('candidate_artifact_sha256','candidate_original_sha256','contract_sha256',
            'execution_record_sha256','private_gt_workspace_sha256','private_scoring_tree_sha256','task_sha256','transcript_sha256')}
        original={'sha256':'old-manifest','document':{'digests':digests}}
        adopted={'digests':deepcopy(digests),'lineage':{'kind':'rescore','source_score_sha256':'old-score',
            'source_scoring_attempt_id':'old','source_candidate_sha256':'candidate','source_attempt_manifest_sha256':'old-manifest'}}
        score={'execution':{'attempt_id':'exec'},'identity':{'attempt_id':'new'}}
        return old,original,adopted,score

    def test_exact_current_selected_source_is_required_without_any_score_ranking(self):
        old,original,new,score=self.fixture()
        for value in (0,.2,1):
            score['result']={'total_score':value}
            COMPOSE.validate_valid_rescore(old,original,new,score)

    def test_source_score_manifest_and_candidate_mismatches_fail(self):
        for key in ('source_score_sha256','source_scoring_attempt_id','source_candidate_sha256','source_attempt_manifest_sha256'):
            old,original,new,score=self.fixture();new['lineage'][key]='different'
            with self.subTest(key=key),self.assertRaises(ValueError):COMPOSE.validate_valid_rescore(old,original,new,score)

    def test_all_eight_input_digests_are_checked(self):
        old,original,new,score=self.fixture()
        for key in original['document']['digests']:
            changed=deepcopy(new);changed['digests'][key]='changed'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'FROZEN_INPUT_CHANGED'):
                COMPOSE.validate_valid_rescore(old,original,changed,score)

    def test_optional_transcript_absence_is_preserved_but_attempt_reuse_is_rejected(self):
        old,original,new,score=self.fixture()
        original['document']['digests']['transcript_sha256']=None;new['digests']['transcript_sha256']=None
        COMPOSE.validate_valid_rescore(old,original,new,score)
        score['identity']['attempt_id']='old'
        with self.assertRaises(ValueError):COMPOSE.validate_valid_rescore(old,original,new,score)

    def test_owner_requires_locked_submission_admitted_score_and_native_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            owner=Path(directory).resolve()/'owner';root=owner/'attempts/unit/task/new';root.mkdir(parents=True)
            (owner/'orchestration-state.json').write_text('{}')
            task={'attempt_path':'attempts/unit/task/new','phase':'SCORE_RECORDED','score':{'sha256':'new-score'},
                  'source':{'score_sha256':'old-score','scoring_attempt_id':'old'},'thread':{'status':'COMPLETED'}}
            state={'kind':'rescore','submission':{'sha256':'locked'},'tasks':[task],'judge':{'protocol':'codex-agent-judge-v1'}}
            frozen=SimpleNamespace(_verify_state=lambda p:state)
            old={'score_sha256':'old-score','scoring_attempt_id':'old'}
            self.assertEqual(COMPOSE.locked_rescore_owner(root,old,'new-score',frozen=frozen),owner)
            task['thread']['status']='RUNNING'
            with self.assertRaises(ValueError):COMPOSE.locked_rescore_owner(root,old,'new-score',frozen=frozen)
            task['thread']=None
            self.assertEqual(COMPOSE.locked_rescore_owner(root,old,'new-score',frozen=frozen,native_required=False),owner)
            state['submission']=None
            with self.assertRaises(ValueError):COMPOSE.locked_rescore_owner(root,old,'new-score',frozen=frozen,native_required=False)


if __name__=='__main__':unittest.main()
