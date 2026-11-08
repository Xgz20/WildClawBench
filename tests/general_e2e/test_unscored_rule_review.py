from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/unscored_rule_review.py'
SPEC = importlib.util.spec_from_file_location('_unscored_review_test_module', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UnscoredReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.attempt = self.root / 'attempt'
        self.folder = self.attempt / 'rule-review'
        (self.folder / 'discovery/worker').mkdir(parents=True)
        self.identity = {'task_id': 'synthetic', 'scoring_attempt_id': 'synthetic-score'}
        self.judge = {'protocol': 'codex-agent-judge-v1', 'model': 'gpt-6.1-sol', 'reasoning_effort': 'high', 'attempt_id': 'synthetic-score'}
        self.locks = {k: str(i) * 64 for i, k in enumerate(MODULE.LOCK_KEYS, 1)}
        self.manifest = {'identity': self.identity, 'judge': self.judge, 'digests': self.locks,
                         'runtime': {'rule_review_profile': 'synthetic-declared/v1'},
                         'paths': {'candidate_original': 'candidate-original/workspace', 'gt': 'private/gt'}}
        self.write(self.attempt / 'attempt-manifest.json', self.manifest)
        self.write(self.folder / 'discovery/worker/request.json', {'synthetic': 'request'})
        self.write(self.folder / 'discovery/worker/result.json', {'synthetic': 'result'})
        self.request = {'identity': self.identity, 'judge': self.judge, 'profile': 'synthetic-declared/v1',
                        'input_locks': self.locks, 'public_candidate_root': 'candidate-original/workspace',
                        'private_reference_root': 'private/gt', 'contexts': [{'id': 'c1'}, {'id': 'c2'}]}
        self.write(self.folder / 'request.json', self.request)
        self.response = {'identity': self.identity, 'judge': self.judge,
                         'locks': {'input_locks': self.locks, 'request_sha256': self.sha(self.folder / 'request.json')},
                         'decisions': [{'context_id': 'c1', 'status': 'judged', 'passed': True, 'query_ids': ['q1'], 'reason': '合成已判定'},
                                       {'context_id': 'c2', 'status': 'unresolved', 'passed': None, 'query_ids': ['q1'], 'reason': '合成证据不足'}]}
        self.write(self.folder / 'response.json', self.response)
        request_sha = self.sha(self.folder / 'request.json')
        self.write(self.folder / 'query-log.json', {'queries': [{'query_id': 'q1', 'context_ids': ['c1', 'c2'], 'request_sha256': request_sha}]})
        self.write(self.folder / 'discovery-audit.json', {
            'identity': self.identity, 'profile': 'synthetic-declared/v1', 'provisional_scores_published': False,
            'request_sha256': request_sha, 'worker_request_sha256': self.sha(self.folder / 'discovery/worker/request.json'),
            'worker_result_sha256': self.sha(self.folder / 'discovery/worker/result.json')})
        self.audit = {'identity': self.identity, 'profile': 'synthetic-declared/v1', 'status': 'unresolved',
                      'input_locks': self.locks, 'numeric_score_assigned': False,
                      'reviewed_context_count': 2, 'unresolved_context_ids': ['c2'],
                      **{key: self.sha(self.folder / name) for key, name in [
                          ('request_sha256', 'request.json'), ('response_sha256', 'response.json'),
                          ('query_log_sha256', 'query-log.json'), ('discovery_audit_sha256', 'discovery-audit.json')]}}
        self.write(self.folder / 'audit.json', self.audit)
        (self.root / 'prompt.md').write_text('frozen synthetic prompt')
        self.task = {'task_id': 'synthetic', 'attempt_path': 'attempt', 'prompt_path': 'prompt.md',
                     'thread': {'status': 'COMPLETED', 'thread_id': 'synthetic-thread'}, 'score': None}
        self.rt = SimpleNamespace(_read_json=lambda p: json.loads(p.read_text()), _sha256_file=self.sha)

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def evidence(self):
        return MODULE.evidence(self.rt, self.root, {}, self.task)

    def test_complete_unresolved_review_is_retained_without_numeric_assignment(self):
        value = self.evidence()
        self.assertEqual(value['reviewed_context_count'], 2)
        self.assertEqual(value['unresolved_context_count'], 1)
        self.assertGreater(len(value['locks']), 5)
        self.assertFalse((self.attempt / 'score.json').exists())

    def test_active_judge_or_existing_score_cannot_be_closed_as_unscored(self):
        self.task['thread']['status'] = 'RUNNING'
        with self.assertRaises(ValueError): self.evidence()
        self.task['thread']['status'] = 'COMPLETED'
        self.write(self.attempt / 'score.json', {})
        with self.assertRaises(ValueError): self.evidence()

    def test_response_or_discovery_drift_is_rejected(self):
        self.write(self.folder / 'response.json', {**self.response, 'decisions': []})
        with self.assertRaisesRegex(ValueError, 'HASH'): self.evidence()
        self.write(self.folder / 'response.json', self.response)
        self.write(self.folder / 'discovery/worker/result.json', {'synthetic': 'changed'})
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_HASH'): self.evidence()

    def test_missing_context_or_invented_query_is_rejected_even_with_recomputed_audit(self):
        for response in [
            {**self.response, 'decisions': self.response['decisions'][:1]},
            {**self.response, 'decisions': [{**d, 'query_ids': ['not-observed']} for d in self.response['decisions']]},
        ]:
            self.write(self.folder / 'response.json', response)
            self.write(self.folder / 'audit.json', {**self.audit, 'response_sha256': self.sha(self.folder / 'response.json')})
            with self.assertRaises(ValueError): self.evidence()

    def test_unresolved_is_not_converted_into_a_boolean_or_zero(self):
        response = deepcopy(self.response)
        response['decisions'][1]['passed'] = False
        self.write(self.folder / 'response.json', response)
        self.write(self.folder / 'audit.json', {**self.audit, 'response_sha256': self.sha(self.folder / 'response.json')})
        with self.assertRaises(ValueError): self.evidence()

    def test_declared_source_failure_keeps_only_owned_grader_output_drift(self):
        workspace=self.attempt/'runtime/workspace';workspace.mkdir(parents=True)
        business=workspace/'business.txt';business.write_bytes(b'original')
        output=workspace/'评分证据';output.mkdir()
        for name in ['分析与验收.json','汇总与差异.json','规则核验.json']:self.write(output/name,{'synthetic':'complete'})
        contract=self.attempt/'contract.json';self.write(contract,{'automated_checks':'synthetic source'})
        worker_folder=self.attempt/'worker';worker_folder.mkdir()
        request={'automated_checks':'synthetic applied rule'};self.write(worker_folder/'request.json',request)
        message='评测不可判定，禁止形成正式综合分：'+'；'.join('无法安全识别来源等价表示：托收服务结算.xlsx|结算_TG01_合同|'+x+'...' for x in ['125','126','131'])
        self.write(worker_folder/'result.json',{'ok':False,'result':None,'error':{'type':'RuntimeError','message':message}})
        audit={'status':'failed','identity':{'task_id':MODULE.SOURCE_TASK,'scoring_attempt_id':'synthetic'},
               'worker':{'request_sha256':self.sha(worker_folder/'request.json'),'return_code':1,'process_tree_cleanup':{'remaining':False}},
               'runtime_workspace':{'drifted':True}}
        self.write(self.attempt/'rule-audit.json',audit)
        self.write(self.attempt/'scoring-attention-report.json',{'task_id':MODULE.SOURCE_TASK,'scoring_attempt_id':'synthetic','formal_score_published':False,'candidate_original_modified':False})
        baseline=hashlib.sha256(b'business.txt\0file\0'+self.sha(business).encode()+b'\n').hexdigest()
        manifest={'identity':audit['identity'],'runtime':{'rule_review_profile':'escrow-status-equivalence-review/v6','workspace_argument':'runtime/workspace'},
                  'digests':{'contract_sha256':MODULE.SOURCE_CONTRACT,'runtime_initial_sha256':baseline},'paths':{'contract':'contract.json'}}
        review={'status':'completed','reviewed_context_count':2276,'unresolved_context_ids':[]}
        self.write(self.folder/'request.json',{'contexts':[{'id':str(i)} for i in range(2276)]})
        with (patch.object(MODULE,'SOURCE_SHA',hashlib.sha256(b'synthetic source').hexdigest()),
              patch.object(MODULE,'SOURCE_WORKER',hashlib.sha256(b'synthetic applied rule').hexdigest())):
            proof=MODULE._declared_source_review(self.rt,self.attempt,manifest,review)
            self.assertEqual(proof['source_reference_ambiguity_count'],3)
            self.assertTrue(proof['original_runtime_drift_flag'])
            self.assertEqual(len(proof['declared_grader_output_files']),3)
            business.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BUSINESS_RUNTIME_DRIFT'):
                MODULE._declared_source_review(self.rt,self.attempt,manifest,review)

    def test_ellipsis_source_proof_uses_frozen_context_count_without_native_report(self):
        workspace=self.attempt/'runtime/workspace';workspace.mkdir(parents=True)
        business=workspace/'business.txt';business.write_bytes(b'original')
        output=workspace/'评分证据';output.mkdir()
        for name in ['分析与验收.json','汇总与差异.json','规则核验.json']:
            self.write(output/name,{'synthetic':'complete'})
        self.write(self.attempt/'contract.json',{'automated_checks':'synthetic source'})
        worker=self.attempt/'worker';worker.mkdir()
        self.write(worker/'request.json',{'automated_checks':'synthetic applied rule'})
        message='评测不可判定，禁止形成正式综合分：'+'；'.join(
            '无法安全识别来源等价表示：…另'+str(i)+'处（见来源索引）' for i in [1,2,3])
        self.write(worker/'result.json',{'ok':False,'result':None,'error':{'type':'RuntimeError','message':message}})
        identity={'task_id':MODULE.SOURCE_TASK,'scoring_attempt_id':'synthetic'}
        self.write(self.attempt/'rule-audit.json',{'status':'failed','identity':identity,
            'worker':{'request_sha256':self.sha(worker/'request.json'),'return_code':1,'process_tree_cleanup':{'remaining':False}},
            'runtime_workspace':{'drifted':True}})
        baseline=hashlib.sha256(b'business.txt\0file\0'+self.sha(business).encode()+b'\n').hexdigest()
        manifest={'identity':identity,'runtime':{'rule_review_profile':'escrow-status-equivalence-review/v6','workspace_argument':'runtime/workspace'},
            'digests':{'contract_sha256':MODULE.SOURCE_CONTRACT,'runtime_initial_sha256':baseline},'paths':{'contract':'contract.json'}}
        review={'status':'completed','reviewed_context_count':2059,'unresolved_context_ids':[]}
        self.write(self.folder/'request.json',{'contexts':[{'id':str(i)} for i in range(2059)]})
        with (patch.object(MODULE,'SOURCE_SHA',hashlib.sha256(b'synthetic source').hexdigest()),
              patch.object(MODULE,'SOURCE_WORKER',hashlib.sha256(b'synthetic applied rule').hexdigest())):
            proof=MODULE._declared_source_review(self.rt,self.attempt,manifest,review)
            self.assertEqual(proof['profile'],'ellipsis-source-locator-ambiguity/v1')
            self.assertIn('not a native agent message',proof['record_origin'])
            self.assertEqual(proof['source_reference_ambiguity_count'],3)
            self.assertFalse((self.attempt/'scoring-attention-report.json').exists())
            self.assertIsNone(MODULE._declared_source_review(self.rt,self.attempt,manifest,{**review,'reviewed_context_count':2058}))
            business.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'BUSINESS_RUNTIME_DRIFT'):
                MODULE._declared_source_review(self.rt,self.attempt,manifest,review)
            business.write_bytes(b'original')
            self.write(worker/'result.json',{'ok':False,'result':None,'error':{'type':'RuntimeError','message':'unregistered failure'}})
            with self.assertRaisesRegex(ValueError,'FAILURE_SIGNATURE_INVALID'):
                MODULE._declared_source_review(self.rt,self.attempt,manifest,review)
            business.write_bytes(b'original')
            self.write(worker/'result.json',{'ok':False,'result':None,'error':{'type':'RuntimeError','message':message+' different'}})
            with self.assertRaisesRegex(ValueError,'FAILURE_SIGNATURE_INVALID'):
                MODULE._declared_source_review(self.rt,self.attempt,manifest,review)

    def test_completed_review_without_context_uncertainty_requires_registered_source_blocker(self):
        response=deepcopy(self.response);response['decisions'][1].update(status='judged',passed=False)
        self.write(self.folder/'response.json',response)
        audit={**self.audit,'status':'completed','unresolved_context_ids':[],
               'response_sha256':self.sha(self.folder/'response.json')}
        self.write(self.folder/'audit.json',audit)
        with self.assertRaisesRegex(ValueError,'IDENTITY_OR_STATUS_INVALID'):self.evidence()
        for name in ['rule-audit.json','rule-source-correction.json','scoring-attention-report.json']:
            self.write(self.attempt/name,{'synthetic':'source retention'})
        (self.attempt/'worker').mkdir()
        with patch.object(MODULE,'_declared_source_review',return_value={'profile':'synthetic declared source','declared_grader_output_files':[]}):
            proof=self.evidence()
        self.assertEqual(proof['unresolved_context_count'],0)
        self.assertEqual(proof['declared_source_review']['profile'],'synthetic declared source')
        self.assertFalse((self.attempt/'score.json').exists())


if __name__ == '__main__':
    unittest.main()
