import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.e2e.headless import normalize_config
from src.e2e import headless_worker as worker


class ClaudeScoringTests(unittest.TestCase):
    def config(self, **overrides):
        return normalize_config({'harness': 'claudecode', 'model': 'test-model',
            'base_url': 'https://gateway.test/anthropic', 'image': 'scorer:v0.2', **overrides})

    def test_anthropic_protocol_and_effort_are_required(self):
        self.assertEqual(self.config()['api_format'], 'anthropic')
        self.assertEqual(self.config()['reasoning_effort'], 'high')
        for extra in [{'api_format': 'openai_chat'}, {'reasoning_effort': 'none'}]:
            with self.assertRaises(ValueError):
                self.config(**extra)

    def test_cli_uses_stdin_private_config_and_native_model_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'claude'
            binary.write_text('''#!/usr/bin/env python3
import json, os, sys
assert sys.stdin.read() == 'Read the frozen scoring evidence'
assert os.environ['ANTHROPIC_API_KEY'] == 'synthetic-key'
assert os.environ['ANTHROPIC_BASE_URL'] == 'https://gateway.test/anthropic'
assert 'E2E_SCORER_API_KEY' not in os.environ
assert '--strict-mcp-config' in sys.argv
if os.environ.get('SCORER_TEST_ERROR'):
    print(json.dumps({'type':'result','subtype':'success','is_error':True,'api_error_status':503,
                      'result':'API Error: 503 no available channel synthetic-key'}))
    sys.exit(1)
print(json.dumps({'type':'system','subtype':'init','model':'test-model'}))
print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'{"score": 1}'}))
''')
            binary.chmod(0o755)
            with patch.object(worker, 'ROOT', root), patch.dict(os.environ, {
                    'E2E_SCORER_API_KEY': 'synthetic-key',
                    'PATH': str(root) + os.pathsep + os.environ['PATH']}):
                worker.launch_agent(self.config(), 'Read the frozen scoring evidence', root)
                self.assertEqual(json.loads((root / 'agent-final.txt').read_text()), {'score': 1})
                proof = worker.agent_identity(self.config())
                self.assertEqual(proof['verification'], 'native-model-readback+launch-effort')
                self.assertNotIn('synthetic-key', (root / 'judge-native.jsonl').read_text())
                launch = json.loads((root / 'agent-launch.json').read_text())
                launch['command'][launch['command'].index('--effort') + 1] = 'low'
                (root / 'agent-launch.json').write_text(json.dumps(launch))
                with self.assertRaisesRegex(RuntimeError, 'REASONING_BINDING_MISMATCH'):
                    worker.agent_identity(self.config())
                (root / 'judge.log').write_text('{"type":"system","subtype":"init","model":"other-model"}\n')
                with self.assertRaisesRegex(RuntimeError, 'MODEL_BINDING_MISMATCH'):
                    worker.agent_identity(self.config())
                with patch.dict(os.environ, {'SCORER_TEST_ERROR': '1'}), \
                     self.assertRaisesRegex(RuntimeError, 'SCORING_CLAUDE_API_ERROR_503:.*no available channel') as failure:
                    worker.launch_agent(self.config(), 'Read the frozen scoring evidence', root)
                self.assertNotIn('synthetic-key', str(failure.exception))


if __name__ == '__main__':
    unittest.main()
