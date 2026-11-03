from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR as M

class ReadonlyVerificationPoolTests(unittest.TestCase):
    def fixture(self, root, count=5):
        tasks=[]
        for i in range(count):
            path=root/str(i);path.mkdir();manifest=path/'attempt-manifest.json';manifest.write_text('{}')
            tasks.append({'task_id':str(i),'attempt_path':str(i),'attempt_manifest_sha256':M._sha256_file(manifest)})
        return {'score_skill':{'frozen':'unchanged'},'tasks':tasks}
    def test_exact_readonly_calls_use_at_most_three_workers_and_no_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();state=self.fixture(root);lock=threading.Lock();active=peak=calls=0
            def verify(skill,args):
                nonlocal active,peak,calls
                self.assertIs(skill,state['score_skill']);self.assertEqual(args[:2],['verify','--attempt-root'])
                with lock:active+=1;peak=max(peak,active);calls+=1
                time.sleep(.02)
                with lock:active-=1
                return {'status':'PASS','path':args[2]}
            with patch.object(M,'_run_score_command',side_effect=verify):
                result=M._preverify_normal_attempts(root,state);again=M._preverify_normal_attempts(root,state)
            self.assertEqual(result,again);self.assertEqual(calls,10);self.assertEqual(peak,3)
            self.assertEqual(list(result),['0','1','2','3','4'])
    def test_errors_preserve_original_task_order_and_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();state=self.fixture(root,3)
            def verify(skill,args):
                task=Path(args[2]).name
                if task=='0':time.sleep(.03)
                raise ValueError('TRACE_HANDOFF_ARTIFACT_DRIFT:'+task)
            with patch.object(M,'_run_score_command',side_effect=verify):result=M._preverify_normal_attempts(root,state)
            self.assertEqual(list(result),['0','1','2'])
            for task,(value,error) in result.items():
                self.assertIsNone(value);self.assertIn('DRIFT:'+task,str(error))
    def test_special_repairs_and_unsafe_or_changed_manifests_keep_sequential_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();state=self.fixture(root,4)
            (root/'0/attempt-manifest.json').write_text('changed')
            state['tasks'][1]['scoring_error']={'kind':M.generated_evidence_globs.ERROR_KIND}
            state['tasks'][2]['attempt_path']='../escape'
            with patch.object(M,'_run_score_command') as invoke:
                result=M._preverify_normal_attempts(root,state,'3')
            self.assertEqual(result,{});invoke.assert_not_called()
