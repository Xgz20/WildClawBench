from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture


RULE='''def check_impact_fields(candidate_value, reference_row, daily_row=None):
    return {"passed": None, "需语义复核字段": [candidate_value]}
def check_source_evidence(table_name, reference_row, expected_refs, actual_refs, context):
    return {"passed": None, "需语义复核来源": list(actual_refs)}
def grade(transcript, workspace_path):
    a=check_impact_fields("别名", {"expected":"字段"}, {"员工编号":"E1"})["passed"]
    b=check_source_evidence("table", {"id":"one"}, {"expected"}, {"alias"}, {})["passed"]
    return {"impact":float(a),"source":float(b),"overall_score":(int(a)+int(b))/2}
'''


class DeclaredRuleReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.matches=patch.object(RUNTIME.rule_review,'matches',return_value=True);self.matches.start()
        def correction(manifest,source):
            effective=source+RUNTIME.rule_review.WRAPPERS
            return effective,{'schema_version':RUNTIME.RULE_SOURCE_CORRECTION_SCHEMA,
                'correction_id':RUNTIME.rule_review.PROFILE,'task_id':manifest['identity']['task_id'],
                'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest()}
        self.correction=patch.object(RUNTIME,'_effective_rule_source',side_effect=correction);self.correction.start()
        fixture=Fixture(self.root/'fixture',rule=RULE,grading_type='hybrid',
            grading_weights={'automated':.78,'llm_judge':.22},llm_judge_rubric='fixture')
        self.attempt=fixture.prepare()
        self.manifest=json.loads((self.attempt/'attempt-manifest.json').read_text())

    def tearDown(self):
        self.correction.stop();self.matches.stop()
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def discover_and_response(self):
        before=RUNTIME._inventory_tree(self.attempt/'runtime/workspace')[1]
        result=RUNTIME.rule_review_runtime.prepare(RUNTIME,attempt_root=self.attempt,runtime_python=Path(sys.executable))
        self.assertEqual(result['context_count'],2)
        self.assertEqual(before,RUNTIME._inventory_tree(self.attempt/'runtime/workspace')[1])
        self.assertFalse((self.attempt/'rule-component.json').exists())
        raw=json.loads((self.attempt/'rule-review/discovery/worker/result.json').read_text())
        self.assertEqual(raw['result'],{});self.assertNotIn('raw_result',raw)
        self.assertTrue(raw['rule_review']['provisional_scores_suppressed'])
        self.assertFalse((self.attempt/'rule-review/discovery/runtime').exists())
        response=json.loads((self.attempt/'rule-review/response-template.json').read_text())
        for offset,row in enumerate(response['decisions']):
            page=RUNTIME.rule_review_runtime.query(RUNTIME,attempt_root=self.attempt,offset=offset,limit=1)
            self.assertEqual(row['context_id'],page['items'][0]['id'])
            row.update(status='judged',passed=page['items'][0]['context']['kind']=='impact-fields',
                       reason='根据冻结候选与参考材料完成字段和来源复核。',query_ids=[page['query_id']])
        return response

    def test_discovery_never_publishes_scores_and_review_drives_original_arithmetic(self):
        response=self.discover_and_response();path=self.attempt/'review-input.json';path.write_text(json.dumps(response))
        result=RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=path)
        self.assertFalse(result['numeric_score_assigned'])
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'ALREADY_TERMINAL'):
            RUNTIME.rule_review_runtime.query(RUNTIME,attempt_root=self.attempt)
        scored=RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=120)
        self.assertEqual(scored['rule_component']['score'],.5)
        self.assertEqual(scored['rule_component']['raw_scores']['impact'],1.)
        self.assertEqual(scored['rule_component']['raw_scores']['source'],0.)
        RUNTIME._verify_rule_source_correction(self.attempt,self.manifest)

    def test_wrong_scope_unqueried_context_and_numeric_placeholders_are_rejected(self):
        response=self.discover_and_response();path=self.attempt/'review-input.json'
        bad=json.loads(json.dumps(response));bad['decisions'].pop();path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'SCOPE_MISMATCH'):
            RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=path)
        for update in [{'passed':1},{'query_ids':['missing-query']},
                       {'query_ids':response['decisions'][1]['query_ids']}]:
            bad=json.loads(json.dumps(response));bad['decisions'][0].update(update);path.write_text(json.dumps(bad))
            with self.subTest(update=update),self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESPONSE_INVALID'):
                RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=path)
        self.assertFalse((self.attempt/'rule-review/audit.json').exists())

    def test_unresolved_review_stays_unavailable_and_does_not_create_a_rule_score(self):
        response=self.discover_and_response();response['decisions'][0].update(status='unresolved',passed=None,
            reason='当前冻结材料不足以确定字段含义，保留不可判定。')
        path=self.attempt/'review-input.json';path.write_text(json.dumps(response))
        result=RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=path)
        self.assertEqual(result['status'],'NEEDS_ATTENTION')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'EVIDENCE_INSUFFICIENT'):
            RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=120)
        self.assertFalse((self.attempt/'worker').exists())
        self.assertFalse((self.attempt/'rule-component.json').exists())


if __name__=='__main__':unittest.main()
