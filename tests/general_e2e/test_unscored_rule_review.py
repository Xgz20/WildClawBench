from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

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


if __name__ == '__main__':
    unittest.main()
