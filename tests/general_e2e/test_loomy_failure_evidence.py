"""Independent admission checks for retained Loomy provider failures; no model calls."""
import base64
import copy
import json
import unittest

from tests.general_e2e.test_general_scoring_orchestration import SCORE_RUNTIME as SCORE


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


class LoomyFailureEvidenceTests(unittest.TestCase):
    def fixture(self, mutate=None):
        module = SCORE.failure_evidence
        prompt = '仅处理本题。'
        identity = {'batch_id': 'batch', 'unit_id': 'loomy', 'task_id': 'arbitrary-task', 'attempt_id': 'attempt'}
        error = {'code': 'LOOMY_NATIVE_HTTP_ERROR', 'message': 'Native primary model HTTP 502 after provider retries'}
        runtime = {'ppid': 99, 'executable': '/app/opencode', 'binary_sha256': 'a' * 64,
                   'database': '/data/opencode.db', 'database_owned': True, 'health_version': '1.14.22'}
        api_error = {'name': 'AI_APICallError', 'url': 'https://loomyad.xunfei.cn/api/v1/chat/completions',
                     'statusCode': 502, 'requestBodyValues': {'model': 'spark-x2.6',
                     'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}]}}
        line = 'ERROR 1970-01-01T00:00:02 +1ms service=llm providerID=imodel modelID=spark-x2.6 session.id=ses_root small=false agent=loomy mode=primary error=' + json.dumps({'error': api_error}, ensure_ascii=False)
        def row(mid, data):
            return {'id': mid, 'session_id': 'ses_root', 'data': json.dumps(data, ensure_ascii=False)}
        native = {'profile': 'loomy-opencode-sqlite/v1', 'snapshot': {'method': 'readonly-source-sqlite-online-backup', 'quick_check': 'ok'},
                  'sessions': [{'id': 'ses_root', 'parent_id': None, 'directory': '/workspace'}],
                  'messages': [row('user', {'role': 'user', 'model': {'providerID': 'imodel', 'modelID': 'spark-x2.6', 'variant': 'high'}}),
                               row('empty', {'role': 'assistant', 'providerID': 'imodel', 'modelID': 'spark-x2.6', 'variant': 'high', 'time': {'created': 1000, 'completed': 3000}})],
                  'parts': [dict(row('prompt', {'type': 'text', 'text': prompt}), message_id='user')]}
        proof = {'profile': 'loomy-native-primary-http-failure/v1', 'identity': identity,
                 'prompt_sha256': module.sha(prompt.encode()), 'session_id': 'ses_root', 'final_message_id': 'empty',
                 'observed_at': '1970-01-01T00:00:04Z',
                 'original_runtime': runtime, 'observed_runtime': copy.deepcopy(runtime), 'runtime_status': {},
                 'source_lines': []}
        if mutate:
            line = mutate(proof, native, line)
        raw = line.encode()
        proof['source_lines'] = [{'bytes_base64': base64.b64encode(raw).decode(), 'sha256': module.sha(raw), 'size': len(raw), 'line_number': 1}]
        config = encoded({'process': {'pid': 99}})
        proof_bytes = encoded(proof)
        binding = {'path': 'native-http-failure.json', 'sha256': module.sha(proof_bytes), 'size': len(proof_bytes)}
        journal = {'identity': identity, 'phase': 'FAILED', 'dispatch_attempt_count': 1, 'send_status': 'sent',
                   'input_locks': {'config': module.sha(config)}, 'native_error': error, 'native_http_failure': binding}
        state = {'identity': identity, 'execution': {'error': error}, 'extensions': {'loomy': {
            'native_http_failure': binding, 'final_message_id': 'empty', 'runtime': runtime}}}
        execution = {'identity': identity, 'execution': {'error': error}, 'prompt': {'sha256': module.sha(prompt.encode())},
                     'session': {'session_id': 'ses_root', 'cwd': '/workspace'}}
        files = {'PROMPT.md': prompt.encode(), 'native-http-failure.json': proof_bytes,
                 'native-scoped-snapshot.json': encoded(native), 'dispatch-journal.json': encoded(journal), 'frozen-run-config.json': config}
        files['original-evidence-manifest.json'] = encoded({'identity': identity, 'artifacts': [
            {'path': 'evidence/trace/raw/' + name, 'sha256': module.sha(files[name]), 'size': len(files[name])}
            for name in ('native-http-failure.json', 'native-scoped-snapshot.json', 'dispatch-journal.json', 'frozen-run-config.json')]})
        return execution, state, files

    def test_validates_primary_failure_without_task_allowlist_or_numeric_score(self):
        SCORE.failure_evidence._validate_loomy_sources(*self.fixture())

    def test_rejects_other_requests_busy_runtime_and_nonempty_head(self):
        def change_model(proof, native, line):
            data = json.loads(native['messages'][0]['data']); data['model']['variant'] = 'low'
            native['messages'][0]['data'] = json.dumps(data); return line
        def nonempty(proof, native, line):
            native['parts'].append({'id': 'text', 'message_id': 'empty', 'session_id': 'ses_root', 'data': '{"type":"text","text":"answer"}'})
            return line
        def busy(proof, native, line):
            proof['runtime_status']['ses_root'] = {'type': 'busy'}; return line
        def different_binary(proof, native, line):
            proof['observed_runtime']['binary_sha256'] = 'b' * 64; return line
        mutations = [change_model, nonempty, busy, different_binary,
                     lambda p, n, line: line.replace('session.id=ses_root ', 'session.id=ses_other '),
                     lambda p, n, line: line.replace('agent=loomy ', 'agent=memory_extraction '),
                     lambda p, n, line: line.replace('"statusCode": 502', '"statusCode": 402'),
                     lambda p, n, line: line.replace('仅处理本题。', 'another request')]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                SCORE.failure_evidence._validate_loomy_sources(*self.fixture(mutate))


if __name__ == '__main__':
    unittest.main()
