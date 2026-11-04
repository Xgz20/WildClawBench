from copy import deepcopy
from pathlib import Path
import json,shutil,tempfile,unittest
from unittest.mock import patch
from eval_general_e2e.datasets.bundle import (compile_dataset,DEFAULT_DEFINITION,GENERAL116_DEFINITION,
    GENERAL70_V2_DEFINITION,GENERAL70_V3_DEFINITION,INFO004_STABLE_DEFINITION,dataset_manifest_path,load_manifest_lock)
from src.utils.task_parser import parse_task_md
from src.wildclawbench_grading_core.criterion_states import validate_semantic_response,finalize_cli_score
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

TASK='01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'
PATH=REPO_ROOT/'tasks/general_e2e/01_Information_Search_Organization'/f'{TASK}.md'

class Info004StableCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.task=parse_task_md(PATH);cls.workspace=Path(cls.task['workspace_path'])
    def copy(self,root):
        shutil.copytree(self.workspace/'exec',root,dirs_exist_ok=True)
        shutil.copytree(self.workspace/'gt',root/'gt')
        ns={};exec(compile(self.task['automated_checks'],'<stable-case-only>','exec'),ns)
        return ns['grade']
    def trace(self,answer):return [{'type':'task_started'},{'role':'assistant','channel':'final','content':answer},
        {'type':'task_complete','last_agent_message':answer}]
    def test_local_packet_is_complete_without_network_or_full_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade=self.copy(root)
            with patch('urllib.request.urlopen',side_effect=AssertionError('no network needed')):
                result=grade(self.trace('依据M1#p1、R1#p1和R2#p1分析。'),str(root))
            self.assertEqual(result['overall_score'],1.)
            self.assertTrue(result['diagnostics']['public_packet_complete'])
            self.assertEqual(result['diagnostics']['material_count'],7)
            index=json.loads((root/'evaluator_evidence/reference_sources.json').read_text())
            self.assertEqual(index['known_unresolved_claims'],[])
            self.assertEqual(index['scoring_research_units'],[1,2])
    def test_traditional_title_is_accepted_and_real_empty_delivery_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade=self.copy(root)
            self.assertEqual(grade(self.trace('《文化偏至論》所给片段可用。'),str(root))['overall_score'],1.)
            self.assertEqual(grade(self.trace(''),str(root))['overall_score'],0.)
    def test_missing_tampered_and_symlink_materials_are_not_zero_scores(self):
        for action in ['missing','changed','symlink']:
            with self.subTest(action=action),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);grade=self.copy(root);path=root/'materials/R2.json'
                if action=='missing':path.unlink()
                elif action=='changed':path.write_text('changed')
                else:
                    data=path.read_bytes();path.unlink();target=root/'same.json';target.write_bytes(data);path.symlink_to(target)
                with self.assertRaisesRegex(ValueError,'EVALUATOR_SETUP_INVALID'):
                    grade(self.trace('R2#p1'),str(root))
    def test_reference_drift_and_wrong_completion_receipt_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade=self.copy(root);(root/'gt/reference_answer.md').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):grade(self.trace('M1#p1'),str(root))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade=self.copy(root)
            with self.assertRaisesRegex(ValueError,'mismatch'):
                grade([{'role':'assistant','content':'M1#p1正文'},{'type':'task_complete','last_agent_message':'different'}],str(root))
    def test_public_body_is_not_erased_by_a_trailing_completion_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grade=self.copy(root)
            trace=[{'type':'task_started'},{'role':'assistant','content':'完整比较M1#p1和R1#p1。'},
                {'role':'assistant','content':'已完成。'},{'type':'task_complete','last_agent_message':'已完成。'}]
            self.assertEqual(grade(trace,str(root))['overall_score'],1.)
            self.assertIn('完整比较',(root/'evaluator_evidence/candidate_answer.md').read_text())
    def test_old_datasets_and_original_workspace_remain_byte_identical(self):
        for definition in [DEFAULT_DEFINITION,GENERAL116_DEFINITION,GENERAL70_V2_DEFINITION,GENERAL70_V3_DEFINITION]:
            actual,_=compile_dataset(REPO_ROOT,definition=definition)
            self.assertEqual(actual,load_manifest_lock(dataset_manifest_path(definition.dataset_id)))
        original=self.workspace.with_name(self.workspace.name.removesuffix('_stable_v1'))
        self.assertFalse((original/'exec/materials').exists())
        self.assertEqual(len(json.loads((original/'gt/reference_sources.json').read_text())['sources']),5)
    def test_release_scope_is_one_case_and_existing_protocol_is_unchanged(self):
        manifest,members=compile_dataset(REPO_ROOT,definition=INFO004_STABLE_DEFINITION)
        self.assertEqual(manifest['task_count'],1)
        self.assertEqual([r['task_id'] for r in manifest['tasks']],[TASK])
        contract=next(json.loads(m.data) for m in members if m.path.endswith('/private-scoring/contract.json'))
        self.assertEqual(contract['automated_checks'],self.task['automated_checks'])
        self.assertEqual(contract['semantic_weight_scale'],98.)
        self.assertNotIn('claim_review_units',contract['judge_evidence'])
        self.assertEqual(sum(c['weight'] for c in self.task['rubric_criteria']),98.)
        self.assertEqual(len(self.task['rubric_criteria']),22)
    def test_two_research_units_reuse_cli_and_native_validation_without_new_fields(self):
        criteria=[{'key':'known','weight':94.,'allowed_scores':[0.,1.]},
            {'key':'scholar_claim_binding','weight':4.,'allowed_scores':[0.,.5,1.]}]
        for statuses,value in [(['supported','supported'],1.),(['supported','contradicted'],.5),
                               (['contradicted','contradicted'],0.),(['supported','evaluator_reference_unavailable'],None)]:
            state='evaluator_reference_unavailable' if value is None else 'pass' if value==1 else 'fail' if value==0 else 'partial'
            response={'scores':{'known':1.,'scholar_claim_binding':value},'criterion_statuses':{
                'known':{'status':'pass','reason':'材料与交付已核验。'},'scholar_claim_binding':{'status':state,'reason':'两个固定研究单元独立核对。'}},
                'claim_reviews':{'scholar_claim_binding':[{'unit':i,'claim_id':str(i),'claim':'本题研究的交付与范围',
                    'status':status,'evidence_refs':[] if status=='evaluator_reference_unavailable' else ['evidence-1']}
                    for i,status in enumerate(statuses,1)]}}
            _,scores,_=validate_semantic_response(response,criteria,claim_review_keys=['scholar_claim_binding'])
            final=finalize_cli_score(1.,{},scores,{'automated':.02,'llm_judge':.98})
            self.assertEqual(final['_grading']['valid'],value is not None)
            if value is None:self.assertIsNone(final['overall_score'])
            else:self.assertAlmostEqual(final['overall_score'],.96+.04*value)
            native={'criteria':[{'key':key,'score':score,'status':'unresolved' if score is None else 'judged',
                'reason':'固定材料及交付已独立核验。','evidence_ids':['evidence-1']} for key,score in response['scores'].items()],
                'claim_reviews':response['claim_reviews']}
            request={'rubric':{'criteria':criteria},'claim_review_policy':{'profile':'evidence-aware-v1',
                'criterion_keys':['scholar_claim_binding'],'units':[1,2],'unavailable_score':None,'cite_queried_frozen_evidence':True}}
            RUNTIME._validate_declared_claim_reviews({'judge_evidence':{'claim_review_keys':['scholar_claim_binding']}},request,native)
