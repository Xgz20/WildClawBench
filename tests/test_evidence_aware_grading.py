from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.utils import grading
from src.wildclawbench_grading_core.criterion_states import validate_semantic_response, finalize_cli_score


CRITERIA = [{'key':'known', 'weight':94., 'allowed_scores':[0.,.5,1.]},
            {'key':'scholar_claim_binding', 'weight':4., 'allowed_scores':[0.,.5,1.]}]


def response(value=None):
    return {'scores':{'known':1., 'scholar_claim_binding':value},
        'criterion_statuses':{'known':{'status':'pass','reason':'已核定来源及回答。'},
            'scholar_claim_binding':{'status':'evaluator_reference_unavailable' if value is None else 'pass',
                                    'reason':'参考段落尚不可核定，不按零分处理。'}},
        'claim_reviews':{'scholar_claim_binding':[{'unit':i,'claim_id':str(i),'claim':'某作者的实质解释',
            'status':'evaluator_reference_unavailable' if value is None else 'supported',
            'evidence_refs':[] if value is None else ['reference-source#paragraph-1']} for i in (1,2)]},
        'notes':'保留已确定结果与参考材料缺口。'}


class EvidenceAwareGradingTests(unittest.TestCase):
    def test_reference_unavailable_is_null_not_zero_or_renormalized(self):
        _, scores, _ = validate_semantic_response(response(), CRITERIA, claim_review_keys=['scholar_claim_binding'])
        result=finalize_cli_score(1.,{'link':1.},scores,{'automated':.02,'llm_judge':.98})
        self.assertIsNone(result['overall_score'])
        self.assertIsNone(result['llm_judge.scholar_claim_binding'])
        self.assertEqual(result['_grading']['weights'],{'automated':.02,'llm_judge':.98})
        self.assertFalse(result['_grading']['unknown_zero_filled'])

    def test_zero_placeholder_for_unavailable_is_rejected(self):
        r=response();r['scores']['scholar_claim_binding']=0
        with self.assertRaisesRegex(ValueError,'MUST_BE_NULL'):
            validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])

    def test_missing_reference_cannot_be_called_a_proven_failure(self):
        r=response();r['scores']['scholar_claim_binding']=0
        r['criterion_statuses']['scholar_claim_binding']['status']='fail'
        with self.assertRaisesRegex(ValueError,'CLAIM_SCORE_MISMATCH'):
            validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])

    def test_two_proven_independent_errors_are_real_zero(self):
        r=response(1.)
        r['scores']['scholar_claim_binding']=0.
        r['criterion_statuses']['scholar_claim_binding']['status']='fail'
        for row in r['claim_reviews']['scholar_claim_binding']:row['status']='contradicted'
        _, scores, _=validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])
        result=finalize_cli_score(1.,{'link':1.},scores,{'automated':.02,'llm_judge':.98})
        self.assertEqual(result['overall_score'],.96)
        self.assertTrue(result['_grading']['valid'])

    def test_confirmed_error_decides_only_its_own_unit(self):
        r=response(1.);r['scores']['scholar_claim_binding']=.5
        r['criterion_statuses']['scholar_claim_binding']['status']='partial'
        r['claim_reviews']['scholar_claim_binding'][0]['status']='contradicted'
        _, scores, _=validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])
        self.assertEqual(scores['scholar_claim_binding'],.5)
        r['claim_reviews']['scholar_claim_binding'][1]['status']='evaluator_reference_unavailable'
        with self.assertRaisesRegex(ValueError,'CLAIM_SCORE_MISMATCH'):
            validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])

    def test_claim_decision_requires_cited_evidence_and_both_units(self):
        r=response(1.);r['claim_reviews']['scholar_claim_binding'][0]['evidence_refs']=[]
        with self.assertRaisesRegex(ValueError,'REQUIRES_EVIDENCE'):
            validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])
        r=response(1.);r['claim_reviews']['scholar_claim_binding'].pop()
        with self.assertRaisesRegex(ValueError,'UNIT_MISSING'):
            validate_semantic_response(r,CRITERIA,claim_review_keys=['scholar_claim_binding'])

    def test_unknown_unweighted_diagnostic_does_not_zero_business(self):
        criteria=deepcopy(CRITERIA);criteria[1]['weight']=0
        _, scores, _=validate_semantic_response(response(),criteria,claim_review_keys=['scholar_claim_binding'])
        result=finalize_cli_score(0.,{},scores,{'automated':0.,'llm_judge':1.})
        self.assertEqual(result['overall_score'],1.)
        self.assertIsNone(result['llm_judge.scholar_claim_binding'])

    def test_cli_judge_preserves_null_through_response_validation(self):
        r=response();contract={'semantic_status_profile':'evidence-aware-v1','claim_review_keys':['scholar_claim_binding']}
        with patch.object(grading,'_exec_container_python',return_value=({'candidate_text':json.dumps(r,ensure_ascii=False)},'')):
            score, values, _=grading._grade_llm_rubric('fixture','冻结原分档',CRITERIA,'/trace.jsonl',judge_evidence=contract)
        self.assertIsNone(score);self.assertIsNone(values['scholar_claim_binding'])

    def test_cli_rules_judge_and_written_result_keep_null(self):
        _, values, notes=validate_semantic_response(response(),CRITERIA,claim_review_keys=['scholar_claim_binding'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(grading,'_exec_container_grade',return_value=({'link':1.,'overall_score':1.},'')), patch.object(grading,'_grade_llm_rubric',return_value=(None,values,notes)):
            d=Path(tmp)
            actual=grading.run_grading('fixture','def grade(): pass',d,rubric_criteria=CRITERIA,
                grading_weights={'automated':.02,'llm_judge':.98},judge_evidence={'semantic_status_profile':'evidence-aware-v1'})
            self.assertIsNone(actual['overall_score']);self.assertEqual(json.loads((d/'score.json').read_text()),actual)

    def test_cli_summary_never_falls_back_to_known_checkpoints(self):
        _, values, _=validate_semantic_response(response(),CRITERIA,claim_review_keys=['scholar_claim_binding'])
        score=finalize_cli_score(1.,{'link':1.},values,{'automated':.02,'llm_judge':.98})
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(StringIO()):
            summary=grading.print_global_summary([{'task_id':'fixture','scores':score,'usage':{}}],Path(tmp),'fixture')
        self.assertEqual(summary['scored_task_count'],0)
        self.assertIsNone(summary['global_avg'])
        self.assertEqual(summary['unresolved_score_task_count'],1)

    def test_cli_failure_and_rule_failure_do_not_publish_zero(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(grading,'_exec_container_grade',return_value=({},'missing reference')):
            actual=grading.run_grading('fixture','broken',Path(tmp),rubric_criteria=CRITERIA,
                grading_weights={'automated':.02,'llm_judge':.98},write_error_score=True,
                judge_evidence={'semantic_status_profile':'evidence-aware-v1'})
        self.assertIsNone(actual['overall_score']);self.assertFalse(actual['_grading']['valid'])

    def test_legacy_numeric_protocol_is_unchanged(self):
        values,error=grading._validate_rubric_scores({'scores':{'known':0.,'scholar_claim_binding':1.}},CRITERIA)
        self.assertEqual(values,{'known':0.,'scholar_claim_binding':1.});self.assertEqual(error,'')

    def test_original_final_total_cap_is_shared_with_cli(self):
        _, values, notes=validate_semantic_response(response(1.),CRITERIA,claim_review_keys=['scholar_claim_binding'])
        policy={'mode':'final_total_cap','upper_bound':.49,'reasons':['unresolved_quality_presented_as_determined'],'version':'office026-v2-20261021'}
        raw={'overall_score':1.,'quality':1.,'_score_policy':policy}
        with tempfile.TemporaryDirectory() as tmp, patch.object(grading,'_exec_container_grade',return_value=(raw,'')), patch.object(grading,'_grade_llm_rubric',return_value=(1.,values,notes)):
            result=grading.run_grading('fixture','rules',Path(tmp),rubric_criteria=CRITERIA,
                grading_weights={'automated':.87,'llm_judge':.13},judge_evidence={'semantic_status_profile':'evidence-aware-v1'})
        self.assertEqual(result['overall_score'],.49)
        self.assertTrue(result['_grading']['valid'])
