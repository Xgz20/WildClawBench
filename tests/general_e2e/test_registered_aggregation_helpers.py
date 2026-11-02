"""Run the frozen original arithmetic helpers with synthetic decisions only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture, REPO_ROOT

GENERAL=RUNTIME.business_capability.general_module()


class RegisteredAggregationHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.base=Fixture(self.root/'base').prepare()
        manifest=json.loads((self.base/'attempt-manifest.json').read_text())
        self.lock=self.base/manifest['paths']['runtime_lock']
        self.sequence=0

    def tearDown(self):
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def original(self,task,policy,value):
        _,sections,_=_parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(task+'.md')))
        code=_strip_codeblock(sections['Automated Checks'])
        self.assertEqual(hashlib.sha256(code.encode()).hexdigest(),policy['automated_source_sha256'])
        args,placeholders=GENERAL.helper_arguments(policy,value)
        source=GENERAL.worker_source(code,args);self.sequence+=1
        path=self.root/str(self.sequence);path.mkdir();workspace=path/'workspace';workspace.mkdir()
        RUNTIME._import_grading_core()
        from wildclawbench_grading_core import inspect_rule_dependencies
        worker=RUNTIME._WorkerExecutor(attempt_root=path,runtime_python=Path(sys.executable),
            runtime_lock_path=self.lock,timeout_seconds=30,playwright_browsers_path=None,
            rule_result_adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics']})
        worker(source,{'dependencies':inspect_rule_dependencies(source),'workspace_path':str(workspace),'transcript':[]})
        raw=json.loads((path/'worker/result.json').read_text());self.assertEqual(raw['result'],{})
        return raw['raw_result']['diagnostics']['aggregation_review']

    def unavailable(self,policy):
        auxiliary={k:None for k in policy['aggregation_auxiliary_keys']}
        for key in auxiliary:
            if key.endswith('error'):auxiliary[key]=False
        if 'process_error_ledger' in auxiliary:auxiliary['process_error_ledger']=[]
        return {'criteria':[{'key':k,'status':'unresolved','score':None} for k in policy['criterion_keys']],
            'criterion_evidence_statuses':{k:{'status':'evidence_insufficient'} for k in policy['criterion_keys']},
            'capability_evidence_statuses':{k:{'status':'evidence_insufficient','score':None} for k in policy['ability_map']},
            'aggregation_review':auxiliary,'run_validity':{'status':'valid'}}

    def test_all_fifteen_original_helpers_retain_unavailable_scores(self):
        self.assertEqual(len(GENERAL.REGISTRY),15)
        for task,policy in GENERAL.REGISTRY.items():
            with self.subTest(task=task):
                result=self.original(task,policy,self.unavailable(policy))
                self.assertIsNone(result[policy['helper_result_key']])
                self.assertTrue(all(v is None for v in result['capabilities'].values()))
                self.assertIsNone(result['capability_total'])

    def raptor(self):
        task=next(t for t in GENERAL.REGISTRY if '_task_005_' in t);policy=GENERAL.REGISTRY[task]
        value=self.unavailable(policy)
        for row in value['criteria']:
            row.update(status='judged',score=1.)
            value['criterion_evidence_statuses'][row['key']]['status']='pass'
        for item in value['capability_evidence_statuses'].values():item.update(status='pass',score=1.)
        return task,policy,value

    def available(self,task,policy):
        value=self.unavailable(policy)
        for row in value['criteria']:
            row.update(status='judged',score=1.)
            value['criterion_evidence_statuses'][row['key']]['status']='pass'
        for item in value['capability_evidence_statuses'].values():item.update(status='pass',score=1.)
        aux=value['aggregation_review']
        if 'core_groups' in aux:aux['core_groups']={key:1. for key in policy['constants']['CORE_GROUPS']}
        if 'parameter_errors' in aux:aux['parameter_errors']=0
        if 'rule_units' in aux:aux['rule_units']=4
        if 'processing_units' in aux:aux['processing_units']=[True]*4 if '_task_016_' in task else 4
        return value

    def derived(self,policy,value,result):
        rows=[{'key':r['key'],'status':r['status'],'score':r['score'],'weight':policy['business_weights'].get(r['key'],0)} for r in value['criteria']]
        def decisions(values):return {k:{**v,'reason':'合成夹具，不判真实候选','evidence':[],'query_ids':[]} for k,v in values.items()}
        aux={'run_validity':value['run_validity'],'criteria':decisions(value['criterion_evidence_statuses']),
             'capabilities':decisions(value['capability_evidence_statuses'])}
        return GENERAL.derive_record({'identity':{'task_id':'fixture'}},{'criteria':rows},aux,{},policy,{'original_result':result})

    def test_original_complete_and_one_unavailable_tool_totals_all_fifteen_profiles(self):
        for task,policy in GENERAL.REGISTRY.items():
            with self.subTest(task=task):
                value=self.available(task,policy);result=self.original(task,policy,value)
                record=self.derived(policy,value,result)
                self.assertEqual(record['business_result']['score'],1.)
                self.assertEqual(record['capability_total_score'],1.)
                self.assertEqual(sum(x['budget'] for x in record['capability_criteria']),policy['capability_budget'])
                key=next(k for k in policy['ability_map'] if k in ['tool_call_contract','ability_call_contract'])
                next(r for r in value['criteria'] if r['key']==key).update(status='unresolved',score=None)
                value['criterion_evidence_statuses'][key]['status']='evidence_insufficient'
                value['capability_evidence_statuses'][key].update(status='evidence_insufficient',score=None)
                result=self.original(task,policy,value);record=self.derived(policy,value,result)
                self.assertEqual(record['business_result']['score'],1.)
                self.assertIsNone(record['capability_total_score']);self.assertIsNone(record['capabilities']['tool_invocation']['score'])

    def test_total_and_budget_cannot_drift_while_each_dimension_looks_correct(self):
        task,policy,value=self.raptor();result=self.original(task,policy,value)
        wrong=deepcopy(result);wrong['capability_total']=99
        with self.assertRaisesRegex(ValueError,'TOTAL_HELPER_MISMATCH'):self.derived(policy,value,wrong)
        wrong_policy=deepcopy(policy);wrong_policy['capability_budget']+=1
        with self.assertRaisesRegex(ValueError,'BUDGET_MISMATCH'):self.derived(wrong_policy,value,result)

    def test_shfe_real_source_helper_keeps_business_exemption_separate_from_numeric_ability(self):
        task=next(t for t in GENERAL.REGISTRY if '_task_019_' in t);policy=GENERAL.REGISTRY[task]
        value=self.available(task,policy);value['capability_evidence_statuses']['source_binding'].update(status='partial',score=.5)
        result=self.original(task,policy,value);record=self.derived(policy,value,result)
        self.assertEqual(record['business_result']['score'],1.)
        self.assertEqual(record['capabilities']['state_awareness']['score'],.5)
        self.assertEqual(next(r for r in record['semantic_criteria'] if r['key']=='source_binding')['score'],1.)

    def test_raptor_two_mappings_use_five_plus_ten_not_equal_or_45_budget(self):
        task,policy,value=self.raptor();key='process_search_planning'
        next(r for r in value['criteria'] if r['key']==key)['score']=.5
        value['criterion_evidence_statuses'][key]['status']='partial';value['capability_evidence_statuses'][key].update(status='partial',score=.5)
        value['aggregation_review']['process_error_ledger']=[{'error_id':'unique-search','owner':key,'kind':'deduction','amount':50,'evidence':['synthetic-query'],'reason':'合成夹具校验唯一归属，不判真实候选。'}]
        result=self.original(task,policy,value)
        self.assertEqual(result['result_final'],100)
        self.assertAlmostEqual(result['capabilities']['reasoning_and_decision_making'],100*(5*.5+10)/15)
        self.assertAlmostEqual(result['capability_total'],100*72.5/75)
        record=self.derived(policy,value,result)
        self.assertEqual(record['capability_budget'],75)
        self.assertAlmostEqual(record['capabilities']['reasoning_and_decision_making']['score'],12.5/15)
        self.assertAlmostEqual(record['capability_total_score'],72.5/75)

    def test_raptor_zero_weight_result_diagnostic_is_still_a_business_dependency(self):
        task,policy,value=self.raptor();key='result_topic'
        next(r for r in value['criteria'] if r['key']==key).update(status='unresolved',score=None)
        value['criterion_evidence_statuses'][key]['status']='evidence_insufficient'
        next(r for r in value['criteria'] if r['key']=='result_final').update(status='unresolved',score=None)
        value['criterion_evidence_statuses']['result_final']['status']='evidence_insufficient'
        result=self.original(task,policy,value);self.assertIsNone(result['result_final'])
        self.assertEqual(result['capability_total'],100)

    def test_raptor_critical_inference_limits_and_unique_attribution_are_not_waived(self):
        task,policy,value=self.raptor();value['aggregation_review']['critical_inference_error']=True
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'critical inference'):self.original(task,policy,value)
        value['aggregation_review']['critical_inference_error']=False
        value['aggregation_review']['process_error_ledger']=[{'error_id':'dup','owner':'process_search_planning','kind':'deduction','amount':5,'evidence':['x'],'reason':'合成错误'}, {'error_id':'dup','owner':'process_tool_routing','kind':'deduction','amount':5,'evidence':['x'],'reason':'同一个错误不得跨项重复'}]
        with self.assertRaises(RUNTIME.ScoringRuntimeError):self.original(task,policy,value)


if __name__=='__main__':unittest.main()
