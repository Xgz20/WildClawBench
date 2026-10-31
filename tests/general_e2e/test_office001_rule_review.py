from copy import deepcopy
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT, Fixture
from tests.general_e2e import test_office001_native_profile
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR

REVIEW=RUNTIME.office001_rule_review


class OfficeNumericReviewTests(unittest.TestCase):
    def source(self):
        return test_office001_native_profile.OfficeNativeProfileTests().source()

    def manifest(self):
        return {'identity':{'task_id':REVIEW.TASK},
            'digests':{'contract_sha256':REVIEW.CONTRACT_SHA},
            'judge':{'protocol':'codex-agent-judge-v1'},
            'runtime':{'rule_review_profile':REVIEW.PROFILE}}

    def test_only_exact_new_attempt_gets_the_declared_unknown_branch(self):
        source=self.source()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),REVIEW.SOURCE_SHA)
        self.assertEqual(REVIEW.effective_source({},source,source,None),(source,None))
        fixed,receipt=RUNTIME._effective_rule_source(self.manifest(),source)
        self.assertIn('office001-numeric-field',fixed)
        self.assertEqual(receipt['correction_id'],REVIEW.PROFILE)
        self.assertFalse(receipt['discovery_provisional_scores_publishable'])
        # Everything outside the explicitly declared unknown numeric branch stays exact.
        a=source.split('                if uncertain:unparsed.append',1)
        self.assertTrue(fixed.startswith(a[0]))
        tail=a[1].split("                match=bool(obs) and all(number(o['value'])==t[k] for o in obs)",1)[1]
        self.assertIn(tail,fixed)
        for mutate in [lambda m:m['digests'].update(contract_sha256='0'*64),
                       lambda m:m['identity'].update(task_id='other'),
                       lambda m:m['judge'].update(protocol='api-judge-v1')]:
            manifest=self.manifest();mutate(manifest)
            with self.assertRaises(RUNTIME.ScoringRuntimeError):
                RUNTIME._effective_rule_source(manifest,source)
        with self.assertRaises(RUNTIME.ScoringRuntimeError):
            RUNTIME._effective_rule_source(self.manifest(),source+'\n')

    def worker(self,mode,decisions=None,known_error=False):
        # Synthetic inputs exercise the exact rule branch in the isolated Worker.
        # They are not candidate artifacts, reference changes or actual scoring.
        source,_=RUNTIME._effective_rule_source(self.manifest(),self.source())
        source += '''
def extract_docx(path):
    return {'paragraphs':['XQ-001 计划量10'], 'tables':[], 'images':0}
def rows_from_tables(doc):
    return [{'id':'XQ-001','locator':'synthetic table row 2'}]
def field_observations(rows,key):
    values={'name':'任务','dept':'部门','issue':'I1','done':8,'accepted':7,'acceptance_total':7,'open_issues':0}
    return [] if key not in values else [{'value':values[key],'locator':'synthetic '+key}]
def grade(transcript,workspace_path):
    facts=[{'id':'XQ-001','name':'任务','dept':'部门','issue':'I1','planned':10,'done':8,
            'accepted':7,'acceptance_total':7,'open_issues':0,'qualifier':''}]
    if _SYNTHETIC_KNOWN_ERROR:facts[0]['done']=9
    scores,_=rule_scores(workspace_path,facts)
    return {'numeric':scores['automated.c3_numeric_facts']['score']}
'''
        source+='\n_SYNTHETIC_KNOWN_ERROR='+repr(known_error)+'\n'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'workspace';(workspace/'results').mkdir(parents=True)
            (workspace/'results/project_report.docx').write_bytes(b'synthetic fixture')
            request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'automated_checks':source,
                'workspace_path':str(workspace),'transcript':[],
                'rule_review':RUNTIME.rule_review.worker_configuration(mode,decisions,profile=REVIEW.PROFILE)}
            path=root/'request.json';path.write_text(json.dumps(request),encoding='utf-8')
            result=root/'result.json'
            process=subprocess.run([sys.executable,'-I',str(REPO_ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/rule_worker.py'),
                '--request',str(path),'--result',str(result)],capture_output=True)
            return process.returncode,json.loads(result.read_text())

    def test_discovery_suppresses_scores_then_independent_bools_keep_the_original_denominator(self):
        code,discovery=self.worker('discover')
        self.assertEqual(code,0);self.assertEqual(discovery['result'],{})
        self.assertNotIn('raw_result',discovery)
        contexts=discovery['rule_review']['contexts'];self.assertEqual(len(contexts),1)
        key,context=next(iter(contexts.items()))
        self.assertEqual((context['kind'],context['task_id'],context['field'],context['expected']),
            ('office001-numeric-field','XQ-001','planned',10))
        for passed,expected in [(True,1.),(False,.8)]:
            code,actual=self.worker('apply',{key:passed})
            self.assertEqual(code,0);self.assertEqual(actual['result']['numeric'],expected)
        # A judge's true for the unknown field cannot erase a known original error.
        code,actual=self.worker('apply',{key:True},known_error=True)
        self.assertEqual(code,0);self.assertEqual(actual['result']['numeric'],.8)
        for decisions in [{},{key:1},{'other':True}]:
            code,actual=self.worker('apply',decisions)
            self.assertNotEqual(code,0);self.assertFalse(actual['ok'])

    def test_old_failed_numeric_attempt_can_be_retained_but_native_and_unknown_errors_cannot(self):
        source=self.source();manifest=self.manifest();contract={'automated_checks':source}
        row={'status':'undetermined','score':None,'reason':'Requires semantic adjudication','evidence':[]}
        prefix='Unresolved rule evidence; use embedded run() for six-state results: '
        error={'type':'RuntimeError','message':prefix+json.dumps({'automated.c3_numeric_facts':row})}
        self.assertTrue(ORCHESTRATOR._office001_declared_numeric_review(manifest,contract,error))
        for bad in [dict(error,type='ValueError'),dict(error,message=prefix+'invalid json'),
                    dict(error,message=prefix+json.dumps({'automated.c5_editability':row})),
                    dict(error,message=prefix+json.dumps({'automated.c3_numeric_facts':dict(row,status='evaluator_error')})),
                    dict(error,message='Unexpected infrastructure failure')]:
            self.assertFalse(ORCHESTRATOR._office001_declared_numeric_review(manifest,contract,bad))
        changed=deepcopy(manifest);changed['digests']['contract_sha256']='0'*64
        self.assertFalse(ORCHESTRATOR._office001_declared_numeric_review(changed,contract,error))


class OfficeReviewTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch.object(RUNTIME.rule_review,'matches',return_value=False),
            patch.object(REVIEW,'matches',return_value=True),
            patch.object(RUNTIME,'_effective_rule_source',side_effect=self.correction)]
        for p in self.patches:p.start()
        rule="def grade(transcript,workspace_path):\n value=float(_rr_decide({'kind':'office001-numeric-field','expected':10,'candidate':'plan:10'}))\n return {'numeric':value,'overall_score':value}"
        self.attempt=Fixture(self.root/'fixture',rule=rule,grading_type='hybrid',
            grading_weights={'automated':.6,'llm_judge':.4},llm_judge_rubric='fixture').prepare()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def correction(self,manifest,source):
        common=RUNTIME.rule_review.WRAPPERS.split('_rr_original_impact=',1)[0].replace(RUNTIME.rule_review.PROFILE,REVIEW.PROFILE)
        effective=source+common
        return effective,{'schema_version':RUNTIME.RULE_SOURCE_CORRECTION_SCHEMA,
            'correction_id':REVIEW.PROFILE,'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest()}

    def response(self):
        before=RUNTIME._inventory_tree(self.attempt/'runtime/workspace')[1]
        prepared=RUNTIME.rule_review_runtime.prepare(RUNTIME,attempt_root=self.attempt,runtime_python=Path(sys.executable))
        self.assertEqual(prepared['context_count'],1)
        self.assertEqual(before,RUNTIME._inventory_tree(self.attempt/'runtime/workspace')[1])
        self.assertFalse((self.attempt/'rule-component.json').exists())
        response=json.loads((self.attempt/'rule-review/response-template.json').read_text())
        query=RUNTIME.rule_review_runtime.query(RUNTIME,attempt_root=self.attempt)
        response['decisions'][0].update(status='judged',passed=True,reason='逐字段核对候选计划量十与冻结参考一致。',
            query_ids=[query['query_id']],evidence_locations=['candidate-original/workspace/answer.txt:1'])
        return response

    def record(self,response):
        path=self.attempt/'independent-test-response.json';path.write_text(json.dumps(response),encoding='utf-8')
        return RUNTIME.rule_review_runtime.record(RUNTIME,attempt_root=self.attempt,response_path=path)

    def test_full_managed_review_pipeline_binds_locations_and_original_runtime(self):
        response=self.response()
        self.assertEqual(self.record(response)['status'],'PASS')
        result=RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'],1.)
        manifest=json.loads((self.attempt/'attempt-manifest.json').read_text())
        RUNTIME._verify_rule_source_correction(self.attempt,manifest)
        self.assertEqual(json.loads((self.attempt/'worker/request.json').read_text())['rule_review']['profile'],REVIEW.PROFILE)

    def test_location_query_and_identity_tampering_do_not_consume_or_accept_response(self):
        response=self.response()
        for change in [dict(evidence_locations=[]),dict(evidence_locations=[False]),dict(query_ids=['unknown']),dict(passed=1)]:
            invalid=deepcopy(response);invalid['decisions'][0].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESPONSE_INVALID'):
                self.record(invalid)
        invalid=deepcopy(response);invalid['locks']['request_sha256']='0'*64
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'LOCK_MISMATCH'):self.record(invalid)
        self.assertFalse((self.attempt/'rule-review/audit.json').exists())

    def test_unresolved_numeric_review_preserves_null_and_does_not_launch_numeric_worker(self):
        response=self.response();response['decisions'][0].update(status='unresolved',passed=None,
            evidence_locations=[],reason='字段仍缺少可验证证据，不能猜测数值。')
        self.assertEqual(self.record(response)['status'],'NEEDS_ATTENTION')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'EVIDENCE_INSUFFICIENT'):
            RUNTIME.run_rules_attempt(attempt_root=self.attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertFalse((self.attempt/'worker').exists())
        self.assertFalse((self.attempt/'rule-component.json').exists())


if __name__=='__main__':unittest.main()
