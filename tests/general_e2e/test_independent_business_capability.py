from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from eval_general_e2e.contracts import validate_contract_file
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture
from tests.general_e2e.test_report_general_e2e import REPORT


WEIGHTS={'core_accuracy':85,'source_binding':15,'scope_execution':0,'difference_inference':0,
         'tool_call_contract':0,'verification_calibration':0}
RUBRIC='\n\n'.join(f'''### Criterion {i}: 判定依据 (key: {key}, weight: {weight})

**Score 1.0**: 完整满足。
**Score 0.5**: 部分满足。
**Score 0.0**: 未满足。
''' for i,(key,weight) in enumerate(WEIGHTS.items(),1))


class IndependentBusinessCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.fixture=Fixture(self.root/'fixture',task_id=RUNTIME.business_capability.TASK,
            rule="def grade(transcript,workspace_path): return {'overall_score':0.0,'diagnostics':{}}",
            grading_type='hybrid',grading_weights={'automated':0.,'llm_judge':1.},llm_judge_rubric=RUBRIC,
            contract_overrides={'semantic_weight_scale':100.,'rule_result_adapter':{
                'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1',
                'diagnostic_keys':['diagnostics','诊断'],'evidence_only':True,'default_overall':None}})
        with zipfile.ZipFile(self.fixture.scoring_package) as z:
            raw=z.read(next(n for n in z.namelist() if n.endswith('/contract.json')))
        self.matches=patch.object(RUNTIME.business_capability,'matches',return_value=True);self.matches.start()
        self.contract=patch.object(RUNTIME.business_capability,'CONTRACT_SHA',hashlib.sha256(raw).hexdigest());self.contract.start()
        self.attempt=self.fixture.prepare()
        RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=120)
        RUNTIME.prepare_semantics_attempt(attempt_root=self.attempt)
        candidate=RUNTIME.query_evidence_attempt(attempt_root=self.attempt,mode='catalog',evidence_type='candidate_file')
        trace=RUNTIME.query_evidence_attempt(attempt_root=self.attempt,mode='transcript',offset=0,limit=1000)
        self.eid=candidate['items'][0]['id'];self.qids=[candidate['query_id'],trace['query_id']]

    def tearDown(self):
        self.contract.stop();self.matches.stop();RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def response(self,*,unresolved=None,run_status='valid'):
        value=json.loads((self.attempt/'semantic/response-template.json').read_text())
        review={'query_ids':self.qids,'supporting_evidence_checked':True,'contradicting_evidence_checked':True,
                'absence_claim':False,'complete_event_range_checked':True}
        for row in value['criteria']:
            missing=row['key']==unresolved
            row.update(status='unresolved' if missing else 'judged',score=None if missing else 1.,
                       reason='已依据冻结材料核对本项证据及相反情形。',evidence_ids=[self.eid],review=review)
        value['run_validity']={'status':run_status,'reason':'已无过滤核对完整公开轨迹及隔离证据。',
                               'evidence_ids':[self.eid],'review':review}
        for key in value['capability_evidence_statuses']:
            value['capability_evidence_statuses'][key]={'status':'evidence_insufficient' if key==unresolved else 'pass',
                'reason':'已核对能力证据；缺少接口时保留不可判定。','evidence_ids':[self.eid],'review':review}
        return value

    def publish(self,response):
        from tests.general_e2e.test_general_semantic_scoring import fixture_evaluator_decision_requests
        response['decision_requests'] = fixture_evaluator_decision_requests(response)
        path=self.attempt/'response-input.json';path.write_text(json.dumps(response,ensure_ascii=False),encoding='utf-8')
        imported=RUNTIME.record_semantics_attempt(attempt_root=self.attempt,response_path=path)
        final=RUNTIME.finalize_score_attempt(attempt_root=self.attempt)
        RUNTIME.verify_score_attempt(self.attempt)
        validate_contract_file(self.attempt/'score.json')
        return imported,final['score']

    def test_zero_weight_unresolved_keeps_business_valid_and_capability_null(self):
        imported,score=self.publish(self.response(unresolved='tool_call_contract'))
        self.assertEqual(imported['business_semantic_status'],'completed')
        self.assertTrue(score['result']['valid']);self.assertEqual(score['result']['total_score'],1.)
        self.assertFalse(any(r['status']=='unresolved' for r in score['evaluation']['criteria']))
        raw=json.loads((self.attempt/'semantic/semantic-component.json').read_text())
        self.assertEqual(raw['status'],'evaluation_error')
        independent=json.loads((self.attempt/'capability-evaluation.json').read_text())
        self.assertEqual(len(independent['semantic_criteria']),6)
        self.assertIsNone(independent['capability_total_score'])
        points=REPORT.report_views.checkpoints(score,self.attempt/'score.json',REPORT.resolve_file,REPORT.sha256_file)
        self.assertNotIn('llm_judge.tool_call_contract',points['capability_values'])
        row={'task_id':RUNTIME.business_capability.TASK,'score_status':'valid','checkpoints':points}
        result=REPORT.report_views.capability_scores([row],{row['task_id']:{'llm_judge.tool_call_contract':['tool_invocation']}},{'tool_invocation':'工具调用'})
        self.assertEqual(result['tool_invocation'],{'score':None,'known':0,'total':1})
        independent['capability_total_score']=0.
        (self.attempt/'capability-evaluation.json').write_text(json.dumps(independent))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'DRIFT'):
            RUNTIME.verify_score_attempt(self.attempt)

    def test_business_unresolved_can_still_publish_independent_valid_process_scores(self):
        _,score=self.publish(self.response(unresolved='core_accuracy'))
        self.assertFalse(score['result']['valid']);self.assertIsNone(score['result']['total_score'])
        independent=json.loads((self.attempt/'capability-evaluation.json').read_text())
        self.assertEqual(independent['capability_total_score'],1.)
        points=REPORT.report_views.checkpoints(score,self.attempt/'score.json',REPORT.resolve_file,REPORT.sha256_file)
        row={'task_id':RUNTIME.business_capability.TASK,'score_status':'evaluation_error','checkpoints':points}
        result=REPORT.report_views.capability_scores([row],{row['task_id']:{'llm_judge.tool_call_contract':['tool_invocation']}},{'tool_invocation':'工具调用'})
        self.assertEqual(result['tool_invocation'],{'score':1.,'known':1,'total':1})

    def test_business_source_score_does_not_substitute_for_missing_retrieval_capability(self):
        response=self.response()
        response['capability_evidence_statuses']['source_binding']['status']='evidence_insufficient'
        _,score=self.publish(response)
        self.assertEqual(score['result']['total_score'],1.)
        points=REPORT.report_views.checkpoints(score,self.attempt/'score.json',REPORT.resolve_file,REPORT.sha256_file)
        self.assertEqual(points['values']['llm_judge.source_binding'],1.)
        self.assertNotIn('llm_judge.source_binding',points['capability_values'])
        self.assertIsNone(points['independent_capabilities']['total_score'])

    def test_contaminated_run_blocks_both_business_and_capability_publication(self):
        _,score=self.publish(self.response(run_status='contaminated_run'))
        self.assertFalse(score['result']['valid']);self.assertIsNone(score['result']['total_score'])
        independent=json.loads((self.attempt/'capability-evaluation.json').read_text())
        self.assertIsNone(independent['capability_total_score'])
        self.assertTrue(all(r['score'] is None for r in independent['capability_criteria']))
        points=REPORT.report_views.checkpoints(score,self.attempt/'score.json',REPORT.resolve_file,REPORT.sha256_file)
        self.assertFalse(points['independent_capability_eligible'])
        self.assertEqual(points['values'],{})

    def test_valid_run_requires_actual_complete_trace_query_proof(self):
        response=self.response();response['run_validity']['review']={**response['run_validity']['review'],'complete_event_range_checked':False}
        path=self.attempt/'response-input.json';path.write_text(json.dumps(response))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'COMPLETE_TRACE_REQUIRED'):
            RUNTIME.record_semantics_attempt(attempt_root=self.attempt,response_path=path)
        self.assertFalse((self.attempt/'capability-evaluation.json').exists())


if __name__=='__main__':unittest.main()
