import contextlib
import io
import unittest
from unittest.mock import patch

from eval_memory_e2e.worker import run_worker
from eval_memory_e2e.io import MemoryEvaluationError


class WorkerTests(unittest.TestCase):
    def simulate(self, failed=None):
        names=['AstronStudio','WorkBuddy','QwenWork','DoubaoWork']
        episodes=[{'id':name+'-'+arm,'harness':name} for name in names for arm in ['cold','experienced']]
        state={item['id']:0 for item in episodes}; live=set(); order=[]; maximum=0
        def next_action(root,key):
            return {'status':'COMPLETED'} if state[key]==2 else {'status':'READY' if state[key]==0 else 'OBSERVE_ONLY','request':{'operation_id':key}}
        def advance(root,key):
            nonlocal maximum
            order.append(key)
            if failed and key.startswith(failed):raise MemoryEvaluationError('FAKE_ENVIRONMENT_FAILURE','keep the attempt')
            if state[key]==0:
                state[key]=1;live.add(key);maximum=max(maximum,len(live));return {'status':'active','episode_id':key}
            state[key]=2;live.remove(key);return {'status':'completed','episode_id':key}
        with patch('eval_memory_e2e.worker.load_batch',return_value={'episodes':episodes}), \
             patch('eval_memory_e2e.worker.next_action',side_effect=next_action), \
             patch('eval_memory_e2e.worker.advance',side_effect=advance), \
             patch('eval_memory_e2e.worker.lock',return_value=contextlib.nullcontext()), \
             patch('eval_memory_e2e.worker.append'), patch('eval_memory_e2e.worker.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
            result=run_worker('/not-a-client',poll_seconds=.01)
        return result,order,maximum

    def test_round_robin_keeps_ui_calls_serial_and_background_harnesses_in_flight(self):
        result,order,maximum=self.simulate()
        self.assertEqual(result['status'],'EXECUTION_COMPLETED')
        self.assertEqual(result['completed_episodes'],8)
        self.assertEqual(maximum,4)
        self.assertEqual(order[:4],['AstronStudio-cold','WorkBuddy-cold','QwenWork-cold','DoubaoWork-cold'])
        for name in ['AstronStudio','WorkBuddy','QwenWork','DoubaoWork']:
            self.assertLess(order.index(name+'-cold')+1,order.index(name+'-experienced'))

    def test_one_harness_failure_does_not_discard_other_harnesses_or_replay_it(self):
        result,order,_=self.simulate(failed='QwenWork')
        self.assertEqual(result['status'],'NEEDS_ATTENTION')
        self.assertEqual(result['completed_episodes'],6)
        self.assertEqual(list(result['blocked_harnesses']),['QwenWork'])
        self.assertEqual(order.count('QwenWork-cold'),1)
        self.assertNotIn('QwenWork-experienced',order)
