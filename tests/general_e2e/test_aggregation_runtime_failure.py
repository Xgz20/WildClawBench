import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ENTRY = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/aggregation_runtime_failure.py'
SPEC = importlib.util.spec_from_file_location('aggregation_runtime_failure_test', ENTRY)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AggregationFailureTests(unittest.TestCase):
    def test_only_completed_unpublished_runtime_mismatch_can_be_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = root / 'attempt'
            (attempt / 'semantic/aggregation-checks/original').mkdir(parents=True)
            (attempt / 'semantic/request.json').write_text('{}')
            (root / 'prompt.md').write_text('check-aggregation')
            manifest = {'runtime': {'business_capability_profile': MODULE.PROFILE},
                        'paths': {'runtime_lock': 'runtime-lock.json'}}
            (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
            (attempt / 'runtime-lock.json').write_text(json.dumps({'python': {'major': 3, 'minor': 11}}))
            python = {'executable': '/original/frozen/python', 'version': [3, 12, 16]}
            state = {'score_skill': {'python': python}}
            task = {'attempt_path': 'attempt', 'prompt_path': 'prompt.md', 'thread': {'status': 'COMPLETED'}}
            rt = SimpleNamespace(_read_json=lambda p: json.loads(p.read_text()),
                                 _score_python_lock=lambda p: dict(python),
                                 _sha256_file=lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
            result = MODULE.evidence(rt, root, state, task)
            self.assertEqual(result['expected_python'], [3, 11])
            self.assertFalse(result['semantic_result_published'])
            task['thread']['status'] = 'RUNNING'
            with self.assertRaisesRegex(ValueError, 'THREAD_NOT_COMPLETED'):
                MODULE.evidence(rt, root, state, task)
            task['thread']['status'] = 'COMPLETED'
            (attempt / 'score.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'HAS_RESULT'):
                MODULE.evidence(rt, root, state, task)
            (attempt / 'score.json').unlink()
            python['version'] = [3, 11, 18]
            with self.assertRaisesRegex(ValueError, 'NOT_MISMATCHED'):
                MODULE.evidence(rt, root, state, task)
            python['version'] = [3, 12, 16]
            rt._score_python_lock = lambda p: {**python, 'version': [3, 12, 17]}
            with self.assertRaisesRegex(ValueError, 'INTERPRETER_DRIFT'):
                MODULE.evidence(rt, root, state, task)
