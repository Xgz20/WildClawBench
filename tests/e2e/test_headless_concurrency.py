import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from src.e2e.common import E2EError
from src.e2e.headless import run_headless_score


class FakeStore:
    def __init__(self, root): pass
    def rows(self):
        return [{'key': str(i), 'task_id': str(i), 'unit_id': 'unit', 'run_index': 1, 'attempt_id': 'a'+str(i)} for i in range(4)]


class HeadlessConcurrencyTests(unittest.TestCase):
    def test_scoring_pool_uses_its_own_limit_and_frozen_job_does_not_change(self):
        active=maximum=0
        lock=threading.Lock()
        def task(*args):
            nonlocal active,maximum
            with lock:
                active+=1;maximum=max(active,maximum)
            time.sleep(0.04)
            with lock:active-=1
            return {'status':'valid','total_score':0.0,'container_released':True}
        config={'harness':'codex','model':'scorer','base_url':'https://example.test/v1','image':'shared:tag','concurrency':2}
        with tempfile.TemporaryDirectory() as path, patch.dict(os.environ,{'E2E_SCORER_API_KEY':'synthetic'}), \
             patch('src.e2e.headless.load_batch',return_value={'schema':'frozen','plan':{'execution_concurrency':7}}), \
             patch('src.e2e.headless.BatchStore',FakeStore), patch('src.e2e.headless.score_one',side_effect=task):
            result=run_headless_score(Path(path)/'batch',Path(path)/'score',config)
            self.assertEqual(maximum,2)
            self.assertEqual(result['summary']['valid'],4)
            self.assertEqual(result['config']['concurrency'],2)
            with self.assertRaisesRegex(E2EError,'REQUEST_DRIFT'):
                run_headless_score(Path(path)/'batch',Path(path)/'score',{**config,'model':'different'})
