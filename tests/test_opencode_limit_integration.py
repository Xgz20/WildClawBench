"""Opt-in real CLI/schema and wire tests; mock HTTP stays inside a network-none container.

WCB_RUN_OPENCODE_DOCKER_TESTS=1 python -m unittest tests.test_opencode_limit_integration
Optional WCB_OPENCODE_DOCKER_SSH=root@host uses an existing remote image, not a deployment.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import unittest
from unittest.mock import patch

from src.agents.opencode.runner import OpenCodeAgent
from src.utils.model_limits import clear_model_limit_caches


CONTAINER_PROBE = r'''
import copy, json, os, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

config = __CONFIG__
requests = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append({'path': self.path, 'model': body.get('model'),
                         'max_tokens': body.get('max_tokens'), 'stream': body.get('stream')})
        base = {'id': 'chatcmpl-limit-test', 'created': int(time.time()), 'model': body['model']}
        usage = {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}
        self.send_response(200)
        if body.get('stream'):
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, reason in [({'role': 'assistant', 'content': 'limit-probe-ok'}, None), ({}, 'stop')]:
                chunk = {**base, 'object': 'chat.completion.chunk',
                         'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
                if reason: chunk['usage'] = usage
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        else:
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({**base, 'object': 'chat.completion', 'usage': usage,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'limit-probe-ok'},
                             'finish_reason': 'stop'}]}).encode())

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
config['provider']['openrouter']['options']['baseURL'] = f'http://127.0.0.1:{server.server_port}/v1'
# Isolate the unrelated native title-model selection from this limit regression.
config['small_model'] = 'openrouter/spark-x2.6'
env = dict(os.environ, OPENCODE_DISABLE_MODELS_FETCH='true', OPENCODE_DISABLE_AUTOUPDATE='true')
version = subprocess.check_output(['opencode', '--version'], text=True).strip()
results = {'version': version, 'cases': {}}
try:
    for case in ['missing_context', 'complete_limit', 'disabled_limit']:
        candidate = copy.deepcopy(config)
        model = candidate['provider']['openrouter']['models']['spark-x2.6']
        if case == 'missing_context': del model['limit']['context']
        elif case == 'disabled_limit': del model['limit']
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps(candidate)
        check = subprocess.run(['opencode', 'debug', 'config'], env=env, text=True,
                               capture_output=True, timeout=30)
        results['cases'][case] = {'returncode': check.returncode,
            'missing_context_error': 'limit.context' in (check.stderr + check.stdout)}
        if check.returncode == 0:
            resolved = json.loads(check.stdout)
            results['cases'][case]['limit'] = resolved['provider']['openrouter']['models']['spark-x2.6'].get('limit')
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(config)
    run = subprocess.run(['opencode', 'run', 'Reply with limit-probe-ok only. Do not use tools.',
                          '--model', 'openrouter/spark-x2.6', '--format', 'json', '--yolo'],
                         env=env, text=True, capture_output=True, timeout=45)
    results['wire'] = {'returncode': run.returncode, 'requests': requests,
                       'completion_seen': 'limit-probe-ok' in run.stdout}
    if run.returncode: results['wire']['diagnostic'] = (run.stderr + run.stdout)[-1500:]
finally:
    server.shutdown(); server.server_close()
print(json.dumps(results))
'''


@unittest.skipUnless(os.environ.get("WCB_RUN_OPENCODE_DOCKER_TESTS") == "1", "opt-in Docker integration")
class OpenCodeLimitIntegrationTests(unittest.TestCase):
    def test_real_cli_accepts_complete_pair_and_serializes_output_budget(self):
        clear_model_limit_caches()
        try:
            agent = OpenCodeAgent(openrouter_api_key="diagnostic-placeholder",
                                  openrouter_base_url="https://maas.example/v2")
            with patch.dict(os.environ, {
                "WILDCLAW_MAAS_MAX_TOKENS_ENABLED": "true", "MAAS_MAX_TOKENS": "4096",
                "OPENCODE_CONTEXT_WINDOW": "65536",
            }, clear=True):
                config = json.loads(agent._render_opencode_config("openrouter/spark-x2.6", redact_secrets=False))
        finally:
            clear_model_limit_caches()
        script = CONTAINER_PROBE.replace("__CONFIG__", repr(config))
        command = ['docker', 'run', '--rm', '--pull=never', '--network', 'none', '-i',
                   '--entrypoint', 'python3', 'wildclawbench-opencode-ubuntu:v0.1', '-']
        remote = os.environ.get("WCB_OPENCODE_DOCKER_SSH")
        if remote:
            command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                       '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=5',
                       '-o', 'ServerAliveCountMax=1', remote, shlex.join(command)]
        result = subprocess.run(command, input=script, text=True, capture_output=True, timeout=115)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        print('OpenCode limit integration:', json.dumps(observed, ensure_ascii=False))
        self.assertEqual(observed['version'], '1.19.6')
        cases = observed['cases']
        self.assertNotEqual(cases['missing_context']['returncode'], 0)
        self.assertTrue(cases['missing_context']['missing_context_error'])
        self.assertEqual(cases['complete_limit']['returncode'], 0)
        self.assertEqual(cases['complete_limit']['limit'], {'context': 65536, 'output': 4096})
        self.assertEqual(cases['disabled_limit']['returncode'], 0)
        self.assertIsNone(cases['disabled_limit']['limit'])
        self.assertEqual(observed['wire']['returncode'], 0)
        self.assertTrue(observed['wire']['completion_seen'])
        calls = observed['wire']['requests']
        self.assertTrue(calls)
        self.assertTrue(all(call['model'] == 'spark-x2.6' for call in calls))
        self.assertTrue(all(call['path'] == '/v1/chat/completions' for call in calls))
        self.assertTrue(any(call['max_tokens'] == 4096 for call in calls))


if __name__ == '__main__':
    unittest.main()
