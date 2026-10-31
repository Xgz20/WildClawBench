from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture,REPO_ROOT,load_module
from tests.general_e2e import test_general_semantic_scoring as semantic_tests

POLICY=RUNTIME.work_order_final_policy
ORCHESTRATION_POLICY=load_module('orchestration_work_order_final_policy_test',
    REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/work_order_final_policy.py')


class OriginalFinalTotalCapTests(unittest.TestCase):
    def policy(self):
        return {'mode':'final_total_cap','version':POLICY.VERSION,'upper_bound':.49,
            'reasons':['unresolved_quality_presented_as_determined','critical_events_unmarked_or_missing']}

    def test_original_reasons_choose_minimum_cap_and_unknown_policy_is_rejected(self):
        policy=self.policy();final={'result':{'valid':True,'total_score':.86},'weights':{'automated':.9,'llm_judge':.1},
            'components':{'rules':{'score':.9},'semantics':{'score':.5}},
            'capabilities':{'reasoning_and_decision_making':.9}}
        result=POLICY.apply(final,policy)
        self.assertEqual(result['result']['total_score'],.49);self.assertEqual(final['result']['total_score'],.86)
        self.assertEqual(result['weights'],final['weights'])
        self.assertEqual(result['components'],final['components'])
        self.assertEqual(result['capabilities'],final['capabilities'])
        low=deepcopy(final);low['result']['total_score']=.2;self.assertEqual(POLICY.apply(low,policy)['result']['total_score'],.2)
        invalid={'result':{'valid':False,'total_score':None}};self.assertIsNone(POLICY.apply(invalid,policy)['result']['total_score'])
        for update in [dict(upper_bound=.59),dict(upper_bound=True),dict(reasons=['unknown_reason']),dict(version='other')]:
            with self.subTest(update=update),self.assertRaises(ValueError):POLICY.validate_policy(dict(policy,**update))

    def test_original_failure_requires_complete_original_numeric_result_and_only_policy_adapter_error(self):
        manifest={'digests':{'contract_sha256':'synthetic'}}
        audit={'status':'failed','error':{'code':'SCORE_VALUE_INVALID'}}
        keys={'order_scope','source_binding','labor_reconciliation','order_allocation',
            'quality_metrics','anomaly_detection','workbook_usable','overall_score'}
        result={**dict.fromkeys(keys,.8),'_score_policy':self.policy()}
        worker={'ok':True,'error':None,'result':result}
        malformed=[]
        for key in keys:
            missing=deepcopy(worker);del missing['result'][key];malformed.append(missing)
        malformed.extend([
            dict(worker,result={'unrelated_score':.8,'_score_policy':self.policy()}),
            dict(worker,result=dict(result,unexpected=.8)),
            dict(worker,result=[]),dict(worker,result=None),dict(worker,ok=False),
            dict(worker,error={'type':'EvaluationError','message':'another failure'}),
        ])
        for value in [True,float('nan'),float('inf'),-.1,1.1,{},None]:
            malformed.append(dict(worker,result=dict(result,order_scope=value)))
        malformed.append(dict(worker,result=dict(result,_score_policy=dict(self.policy(),upper_bound=.59))))
        for module in [POLICY,ORCHESTRATION_POLICY]:
            with self.subTest(module=module.__name__),patch.object(module,'marker',return_value={'synthetic':True}):
                before=deepcopy(worker)
                self.assertTrue(module.original_failure(manifest,{},audit,worker))
                self.assertEqual(worker,before)
                for index,value in enumerate(malformed):
                    with self.subTest(index=index):
                        self.assertFalse(module.original_failure(manifest,{},audit,value))
                self.assertFalse(module.original_failure(manifest,{},dict(audit,error=None),worker))
                self.assertFalse(module.original_failure(manifest,{},dict(audit,status='completed'),worker))
            self.assertFalse(module.original_failure(manifest,{},audit,worker))

    def test_legacy_manifest_keeps_original_adapter_and_active_profile_requires_exact_marker(self):
        adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics']}
        contract={'task_id':'unrelated-task','automated_checks':''}
        for module in [POLICY,ORCHESTRATION_POLICY]:
            with self.subTest(module=module.__name__):
                self.assertIs(module.effective_adapter({'runtime':{}},contract,adapter),adapter)
                marker={'profile':module.PROFILE,'synthetic_fixture':True}
                manifest={'runtime':{'work_order_final_total_policy_profile':marker},'digests':{'contract_sha256':'synthetic'}}
                with self.assertRaisesRegex(ValueError,'WORK_ORDER_FINAL_POLICY_PROFILE_MISMATCH'):
                    module.effective_adapter(manifest,contract,adapter)
                with patch.object(module,'marker',return_value=marker):
                    adapted=module.effective_adapter(manifest,contract,adapter)
                    self.assertEqual(adapted,dict(adapter,final_total_policy_object_key='_score_policy'))
                    self.assertNotIn('final_total_policy_object_key',adapter)

    def test_rule_dependency_failure_without_worker_result_finalizes_invalid_and_verifies(self):
        with tempfile.TemporaryDirectory(prefix='office026-cap-failure-test-') as folder:
            root=Path(folder);marker={'profile':POLICY.PROFILE,'synthetic_fixture':True}
            adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':[]}
            rule='def grade(transcript,workspace_path):\n import office026_synthetic_undeclared_dependency\n return {}'
            with patch.object(POLICY,'marker',return_value=marker):
                attempt=Fixture(root/'fixture',rule=rule,contract_overrides={'rule_result_adapter':adapter}).prepare()
                try:
                    with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RULE_DEPENDENCY_UNDECLARED'):
                        RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                    self.assertFalse((attempt/'worker/result.json').exists())
                    audit=json.loads((attempt/'rule-audit.json').read_text())
                    self.assertEqual(audit['error']['code'],'RULE_DEPENDENCY_UNDECLARED')
                    RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
                    result=RUNTIME.finalize_score_attempt(attempt_root=attempt)['score']
                    self.assertFalse(result['result']['valid'])
                    self.assertIsNone(result['result']['total_score'])
                    self.assertEqual(result['evaluation']['error']['code'],'RULE_DEPENDENCY_UNDECLARED')
                    self.assertFalse(RUNTIME.verify_score_attempt(attempt)['score_valid'])
                    RUNTIME._remove_tree(attempt/'runtime')
                    self.assertFalse(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])
                    self.assertFalse((attempt/'worker/result.json').exists())
                finally:RUNTIME._remove_tree(root)

    def test_valid_numeric_score_still_rejects_missing_or_invalid_original_policy(self):
        for defect in ['missing','incorrect_cap']:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory(prefix='office026-cap-integrity-test-') as folder:
                root=Path(folder);marker={'profile':POLICY.PROFILE,'synthetic_fixture':True}
                rule="def grade(transcript,workspace_path):\n return {'accuracy':.8,'overall_score':.8,'_score_policy':"+repr(self.policy())+"}"
                adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':[]}
                with patch.object(POLICY,'marker',return_value=marker):
                    attempt=Fixture(root/'fixture',rule=rule,contract_overrides={'rule_result_adapter':adapter}).prepare()
                    try:
                        RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                        worker_path=attempt/'worker/result.json';worker=json.loads(worker_path.read_text())
                        if defect=='missing':del worker['raw_result']['_score_policy']
                        else:worker['raw_result']['_score_policy']['upper_bound']=.59
                        worker_path.write_text(json.dumps(worker),encoding='utf-8')
                        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
                        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'FINAL_TOTAL_POLICY_INVALID'):
                            RUNTIME.finalize_score_attempt(attempt_root=attempt)
                        self.assertFalse((attempt/'score.json').exists())
                    finally:RUNTIME._remove_tree(root)

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
