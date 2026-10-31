from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture
from tests.general_e2e import test_general_semantic_scoring as semantic_tests

POLICY=RUNTIME.work_order_final_policy


class OriginalFinalTotalCapTests(unittest.TestCase):
    def policy(self):
        return {'mode':'final_total_cap','version':POLICY.VERSION,'upper_bound':.49,
            'reasons':['unresolved_quality_presented_as_determined','critical_events_unmarked_or_missing']}

    def test_original_reasons_choose_minimum_cap_and_unknown_policy_is_rejected(self):
        policy=self.policy();final={'result':{'valid':True,'total_score':.86},'weights':{'automated':.9,'llm_judge':.1}}
        result=POLICY.apply(final,policy)
        self.assertEqual(result['result']['total_score'],.49);self.assertEqual(final['result']['total_score'],.86)
        self.assertEqual(result['weights'],final['weights'])
        low=deepcopy(final);low['result']['total_score']=.2;self.assertEqual(POLICY.apply(low,policy)['result']['total_score'],.2)
        invalid={'result':{'valid':False,'total_score':None}};self.assertIsNone(POLICY.apply(invalid,policy)['result']['total_score'])
        for update in [dict(upper_bound=.59),dict(upper_bound=True),dict(reasons=['unknown_reason']),dict(version='other')]:
            with self.subTest(update=update),self.assertRaises(ValueError):POLICY.validate_policy(dict(policy,**update))

    def test_managed_rule_policy_survives_transport_caps_only_final_and_archived_verify_recomputes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);policy=self.policy();marker={'profile':POLICY.PROFILE,'synthetic_fixture':True}
            rule="def grade(transcript,workspace_path):\n return {'accuracy':.8,'overall_score':.8,'_score_policy':"+repr(policy)+"}"
            adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics','诊断']}
            with patch.object(POLICY,'marker',return_value=marker):
                attempt=Fixture(root/'fixture',rule=rule,grading_type='hybrid',grading_weights={'automated':.9,'llm_judge':.1},
                    llm_judge_rubric=semantic_tests.RUBRIC,contract_overrides={'rule_result_adapter':adapter}).prepare()
                try:
                    RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                    worker=json.loads((attempt/'worker/result.json').read_text())
                    self.assertEqual(worker['raw_result']['_score_policy'],policy)
                    self.assertNotIn('_score_policy',worker['result'])
                    self.assertEqual(json.loads((attempt/'rule-component.json').read_text())['score'],.8)
                    helper=semantic_tests.GeneralSemanticScoringTests();response,candidate,transcript=helper._prepare_and_query(attempt)
                    for row,score,ids,queries in zip(response['criteria'],[1.,.5],[[candidate],[transcript]],[['query-0001'],['query-0002']]):
                        row.update(status='judged',score=score,reason='合成响应仅验证原业务封顶政策的机械合分与归档，不改任何独立能力项。',
                            evidence_ids=ids,review={'query_ids':queries,'supporting_evidence_checked':True,'contradicting_evidence_checked':True,'absence_claim':False,'complete_event_range_checked':False})
                    source=attempt/'synthetic-response.json';source.write_text(json.dumps(response,ensure_ascii=False),encoding='utf-8')
                    RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=source)
                    result=RUNTIME.finalize_score_attempt(attempt_root=attempt)['score']
                    self.assertEqual(result['result']['total_score'],.49)
                    self.assertEqual(result['components']['rules']['score'],.8)
                    self.assertIn('upper_bound=0.49',result['evaluation']['criteria'][0]['reason'])
                    self.assertTrue(RUNTIME.verify_score_attempt(attempt)['score_valid'])
                    RUNTIME._remove_tree(attempt/'runtime')
                    self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])
                finally:RUNTIME._remove_tree(root)


if __name__=='__main__':unittest.main()
