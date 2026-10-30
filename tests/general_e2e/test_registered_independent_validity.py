from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture
from tests.general_e2e.test_report_general_e2e import REPORT

GENERAL = RUNTIME.business_capability.general_module()
TASK = '01_Information_Search_Organization_task_006_post_thrombectomy_bp_trials'
WEIGHTS = {'core_accuracy':90,'source_binding':10,'tool_call_contract':0,'verification_calibration':0}
RUBRIC = '\n\n'.join(f'''### Criterion {i}: 冻结证据判定 (key: {key}, weight: {weight})

**Score 1.0**: 完整满足。
**Score 0.5**: 部分满足。
**Score 0.0**: 未满足。
''' for i,(key,weight) in enumerate(WEIGHTS.items(),1))
RULE = '''
ABILITY_MAP={'source_binding':('state_awareness',10),'tool_call_contract':('tool_invocation',10),'verification_calibration':('result_evaluation',10)}
def grade(transcript,workspace_path):return {'diagnostics':{}}
def aggregate_review(scores,statuses,ability_statuses,run_status,*,core_groups=None,critical_error=False,parameter_errors=None):
    valid={'pass','partial','fail'}
    business=90*scores['core_accuracy']+10*scores['source_binding'] if run_status=='valid' and all(statuses[k] in valid for k in ['core_accuracy','source_binding']) else None
    mapping={'source_binding':'state_awareness','tool_call_contract':'tool_invocation','verification_calibration':'result_evaluation'}
    capabilities={dimension:100*scores[key] if run_status=='valid' and statuses[key] in valid and ability_statuses[key] in valid else None for key,dimension in mapping.items()}
    return {'llm_result_score':business,'capabilities':capabilities,'capability_total':sum(capabilities.values())/3 if all(v is not None for v in capabilities.values()) else None}
'''


class RegisteredIndependentValidityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.fixture=Fixture(self.root/'fixture',task_id=TASK,rule=RULE,grading_type='hybrid',
            grading_weights={'automated':0.,'llm_judge':1.},llm_judge_rubric=RUBRIC,
            contract_overrides={'semantic_weight_scale':100.,'rule_result_adapter':{
                'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1',
                'diagnostic_keys':['diagnostics'],'evidence_only':True,'default_overall':None}})
        with zipfile.ZipFile(self.fixture.scoring_package)as z:raw=z.read(next(n for n in z.namelist() if n.endswith('/contract.json')))
        spec=deepcopy(GENERAL.REGISTRY[TASK]);spec['contract_sha256']=hashlib.sha256(raw).hexdigest();spec['automated_source_sha256']=hashlib.sha256(RULE.encode()).hexdigest()
        self.registry=patch.dict(GENERAL.REGISTRY,{TASK:spec});self.registry.start()
        self.attempt=self.fixture.prepare();RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=120)
        RUNTIME.prepare_semantics_attempt(attempt_root=self.attempt)
        candidate=RUNTIME.query_evidence_attempt(attempt_root=self.attempt,mode='catalog',evidence_type='candidate_file')
        trace=RUNTIME.query_evidence_attempt(attempt_root=self.attempt,mode='transcript',offset=0,limit=1000)
        self.eid=candidate['items'][0]['id'];self.qids=[candidate['query_id'],trace['query_id']]

    def tearDown(self):
        self.registry.stop();RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def response(self,unresolved=None,run='valid'):
        value=json.loads((self.attempt/'semantic/response-template.json').read_text())
        review={'query_ids':self.qids,'supporting_evidence_checked':True,'contradicting_evidence_checked':True,'absence_claim':False,'complete_event_range_checked':True}
        for row in value['criteria']:
            missing=row['key']==unresolved
            row.update(status='unresolved' if missing else 'judged',score=None if missing else 1.,reason='合成夹具按已查询证据核对，不判真实候选。',evidence_ids=[self.eid],review=review)
            value['criterion_evidence_statuses'][row['key']]={'status':'evidence_insufficient' if missing else 'pass','reason':'已核对本项证据及相反材料，未知不补零。','evidence_ids':[self.eid],'review':review}
        value['run_validity']={'status':run,'reason':'已核对完整合成轨迹和运行身份，测试污染禁发。','evidence_ids':[self.eid],'review':review}
        for key in value['capability_evidence_statuses']:
            value['capability_evidence_statuses'][key]={'status':'evidence_insufficient' if key==unresolved else 'pass','score':None if key==unresolved else 1.,'reason':'依据冻结查询判定能力证据，缺接口保持未知。','evidence_ids':[self.eid],'review':review}
        value['aggregation_review']={'core_groups':{},'critical_error':False,'parameter_errors':None if unresolved=='tool_call_contract' else 0}
        return value

    def publish(self,value):
        path=self.attempt/'native-response.json';path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        checked=RUNTIME.semantic_aggregation.check(RUNTIME,attempt_root=self.attempt,response_path=path,runtime_python=Path(sys.executable))
        self.assertEqual(checked['status'],'PASS')
        RUNTIME.record_semantics_attempt(attempt_root=self.attempt,response_path=path)
        result=RUNTIME.finalize_score_attempt(attempt_root=self.attempt)['score'];RUNTIME.verify_score_attempt(self.attempt)
        return result,json.loads((self.attempt/'capability-evaluation.json').read_text())

    def test_missing_tool_evidence_keeps_business_valid_with_original_30_budget(self):
        score,record=self.publish(self.response('tool_call_contract'))
        self.assertTrue(score['result']['valid']);self.assertEqual(score['result']['total_score'],1.)
        self.assertEqual(record['capability_budget'],30);self.assertIsNone(record['capability_total_score'])
        view=REPORT.report_views.checkpoints(score,self.attempt/'score.json',REPORT.resolve_file,REPORT.sha256_file)
        self.assertNotIn('llm_judge.tool_call_contract',view['capability_values'])
        self.assertIsNone(record['capabilities']['tool_invocation']['score'])
        proof=self.attempt/record['aggregation_review']['proof_path'];self.assertFalse(json.loads(proof.read_text())['provisional_values_publishable'])
        worker=json.loads((proof.parent/'worker/result.json').read_text());self.assertEqual(worker['result'],{})

    def test_unresolved_business_retains_independently_valid_capabilities(self):
        score,record=self.publish(self.response('core_accuracy'))
        self.assertFalse(score['result']['valid']);self.assertIsNone(score['result']['total_score'])
        self.assertEqual(record['capability_total_score'],1.)

    def test_business_source_exemption_cannot_create_a_retrieval_capability_score(self):
        value=self.response();value['capability_evidence_statuses']['source_binding'].update(status='evidence_insufficient',score=None)
        score,record=self.publish(value);self.assertEqual(score['result']['total_score'],1.)
        self.assertIsNone(record['capabilities']['state_awareness']['score'])

    def test_contaminated_run_disables_both_publications(self):
        score,record=self.publish(self.response(run='contaminated_run'))
        self.assertFalse(score['result']['valid']);self.assertIsNone(record['capability_total_score'])
        self.assertTrue(all(v['score'] is None for v in record['capabilities'].values()))

    def test_aggregation_input_or_worker_drift_is_not_admitted(self):
        value=self.response();score,record=self.publish(value)
        proof=self.attempt/record['aggregation_review']['proof_path'];worker=proof.parent/'worker/result.json'
        worker.write_text(worker.read_text()+' ')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'AGGREGATION_WORKER_DRIFT'):RUNTIME.verify_score_attempt(self.attempt)

    def test_report_uses_original_m_for_multiple_checkpoints_in_one_dimension(self):
        points={'independent_capability_eligible':True,'independent_capabilities':{
            'profile':'independent-business-capability/v2','criteria':[
                {'key':'search','dimension':'reasoning_and_decision_making','budget':5},
                {'key':'inference','dimension':'reasoning_and_decision_making','budget':10}],
            'dimensions':{'reasoning_and_decision_making':{'score':12.5/15}}},
            'capability_values':{'llm_judge.search':.5,'llm_judge.inference':1.}}
        mapping={'fixture':{'llm_judge.search':['reasoning_and_decision_making'],'llm_judge.inference':['reasoning_and_decision_making']}}
        rows=[{'task_id':'fixture','score_status':'valid','checkpoints':points}]
        score=REPORT.report_views.capability_scores(rows,mapping,{'reasoning_and_decision_making':'推理'})
        self.assertAlmostEqual(score['reasoning_and_decision_making']['score'],12.5/15)
        points['independent_capabilities']['dimensions']['reasoning_and_decision_making']['score']=None
        self.assertIsNone(REPORT.report_views.capability_scores(rows,mapping,{'reasoning_and_decision_making':'推理'})['reasoning_and_decision_making']['score'])


if __name__=='__main__':unittest.main()
