from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture,REPO_ROOT
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock

REVIEW=RUNTIME.escrow_state_review
RULE="def grade(transcript,workspace_path):\n return {'overall_score':0.}"
BASE="""def _ge2e_escrow_original_grade(transcript,workspace_path):
    row={'状态':'别称','_candidate_location':'synthetic.xlsx|Sheet|行2'}
    value=_ge2e_escrow_state('状态',row,{'批准','取消'})
    return {'status_match':float(value=='批准'),'overall_score':float(value=='批准')}
"""


class EscrowStateReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        common=RUNTIME.rule_review.WRAPPERS.split('_rr_original_impact=',1)[0].replace(RUNTIME.rule_review.PROFILE,REVIEW.PROFILE)
        def effective(manifest,source):
            code=BASE+common+REVIEW.WRAPPERS
            return code,{'schema_version':RUNTIME.RULE_SOURCE_CORRECTION_SCHEMA,'correction_id':REVIEW.PROFILE,
                'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),'effective_source_sha256':hashlib.sha256(code.encode()).hexdigest()}
        self.patches=[patch.object(RUNTIME.rule_review,'matches',return_value=False),
            patch.object(RUNTIME.office001_rule_review,'matches',return_value=False),patch.object(REVIEW,'matches',return_value=True),
            patch.object(RUNTIME,'_effective_rule_source',side_effect=effective)]
        for p in self.patches:p.start()
        self.attempt=Fixture(self.root/'fixture',rule=RULE,grading_type='hybrid',grading_weights={'automated':.8,'llm_judge':.2},llm_judge_rubric='fixture').prepare()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def response(self,choice):
        result=RUNTIME.rule_review_runtime.prepare(RUNTIME,attempt_root=self.attempt,runtime_python=Path(sys.executable))
        self.assertEqual(result['context_count'],3)
        query=RUNTIME.rule_review_runtime.query(RUNTIME,attempt_root=self.attempt)
        response=json.loads((self.attempt/'rule-review/response-template.json').read_text());contexts={i['id']:i['context'] for i in query['items']}
        for row in response['decisions']:
            selected=contexts[row['context_id']]['canonical_choice']
            row.update(status='judged',passed=selected==choice,reason='合成状态用语复核仅验证判定传输，不按参考事实修正候选。',query_ids=[query['query_id']])
        return response

    def record(self,response):
        file=self.attempt/'independent-synthetic-response.json';file.write_text(json.dumps(response),encoding='utf-8')
        return RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=file)

    def test_independent_boolean_choices_drive_original_comparison_without_publishing_discovery_scores(self):
        response=self.response('批准');self.assertFalse((self.attempt/'rule-component.json').exists())
        self.assertEqual(self.record(response)['status'],'PASS')
        scored=RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(scored['rule_component']['score'],1.)

    def test_distinct_literal_remains_wrong_under_original_comparison(self):
        response=self.response('__keep_literal_known_distinct__');self.record(response)
        scored=RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(scored['rule_component']['score'],0.)

    def test_ambiguous_or_nonunique_decisions_never_launch_numerical_worker(self):
        response=self.response('no-option')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'EXACTLY_ONE_CHOICE'):self.record(response)
        response['decisions'][0].update(status='unresolved',passed=None,reason='语义仍不确定，不猜测等价关系。')
        self.assertEqual(self.record(response)['status'],'NEEDS_ATTENTION')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'EVIDENCE_INSUFFICIENT'):
            RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertFalse((self.attempt/'worker').exists())


class ExactEscrowSourceTests(unittest.TestCase):
    def test_real_source_profile_is_exact_and_keeps_normalization_opt_in(self):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(REVIEW.TASK+'.md'));_,s,_=_parse_task_source(task)
        source=_strip_codeblock(s['Automated Checks']);self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),REVIEW.SOURCE_SHA)
        manifest={'identity':{'task_id':REVIEW.TASK},'digests':{'contract_sha256':REVIEW.CONTRACT_SHA},'runtime':{'rule_review_profile':REVIEW.PROFILE}}
        code,receipt=RUNTIME._effective_rule_source(manifest,source)
        compile(code,'<exact-escrow-review>','exec');self.assertFalse(receipt['numeric_decisions_assigned'])
        self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))


if __name__=='__main__':unittest.main()
