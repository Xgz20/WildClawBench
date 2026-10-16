import contextlib
import io
import unittest
from unittest.mock import patch

from eval_memory_e2e.worker import run_worker, accepted_observation_binding
from eval_memory_e2e.io import MemoryEvaluationError


class WorkerTests(unittest.TestCase):
    def test_retry_requires_the_exact_operation_native_binding_and_observation_mode(self):
        request={'episode_id':'owned','operation_id':'op-owned','action':'execute_step'}
        history=[{'kind':'RECEIPT','episode_id':'other','payload':{'operation_id':'op-owned','native':{'session_id':'s','turn_id':'t'}}},
                 {'kind':'RECEIPT','episode_id':'owned','payload':{'operation_id':'op-other','native':{'session_id':'s','turn_id':'t'}}}]
        with patch('eval_memory_e2e.worker.events',return_value=history):
            self.assertIsNone(accepted_observation_binding('/unused',{'status':'OBSERVE_ONLY','request':request}))
            history.append({'kind':'RECEIPT','episode_id':'owned','payload':{'operation_id':'op-owned','native':{'session_id':'s','turn_id':'t'}}})
            self.assertEqual(accepted_observation_binding('/unused',{'status':'OBSERVE_ONLY','request':request}),{'session_id':'s','turn_id':'t'})
            self.assertIsNone(accepted_observation_binding('/unused',{'status':'READY','request':request}))

    def retry_simulation(self, accepted, failures):
        calls=[];complete=False
        def action(root, episode):
            return {'status':'COMPLETED'} if complete else {'status':'OBSERVE_ONLY','request':{'operation_id':'same-operation'}}
        def advance(root, episode):
            nonlocal complete
            calls.append('observe')
            if len(calls)<=failures:raise MemoryEvaluationError('DRIVER_PROCESS_ERROR','transient control failure')
            complete=True;return {'status':'completed'}
        with patch('eval_memory_e2e.worker.load_batch',return_value={'episodes':[{'id':'owned','harness':'AstronStudio'}]}), \
             patch('eval_memory_e2e.worker.next_action',side_effect=action), \
             patch('eval_memory_e2e.worker.advance',side_effect=advance), \
             patch('eval_memory_e2e.worker.accepted_observation_binding',return_value={'session_id':'s','turn_id':'t'} if accepted else None), \
             patch('eval_memory_e2e.worker.lock',return_value=contextlib.nullcontext()), \
             patch('eval_memory_e2e.worker.append') as journal, patch('eval_memory_e2e.worker.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
            result=run_worker('/unused',poll_seconds=.01)
        retries=[call for call in journal.call_args_list if call.args[1]=='OBSERVATION_RETRY']
        return result,calls,retries

    def test_bound_transient_observation_recovers_without_dispatching_again(self):
        result,calls,retries=self.retry_simulation(True,2)
        self.assertEqual(result['status'],'EXECUTION_COMPLETED');self.assertEqual(calls,['observe']*3)
        self.assertEqual(len(retries),2)
        self.assertTrue(all(call.args[3]['prompt_resend_authorized'] is False for call in retries))

    def test_unbound_failure_is_not_automatically_retried(self):
        result,calls,retries=self.retry_simulation(False,2)
        self.assertEqual(result['status'],'NEEDS_ATTENTION');self.assertEqual(len(calls),1);self.assertEqual(retries,[])

    def test_persistent_bound_control_failures_pause_after_three_observation_retries(self):
        result,calls,retries=self.retry_simulation(True,20)
        self.assertEqual(result['status'],'NEEDS_ATTENTION');self.assertEqual(len(calls),4);self.assertEqual(len(retries),3)

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
