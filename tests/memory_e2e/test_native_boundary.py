import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e import EXECUTION_GUARD
from eval_memory_e2e.batch import prepare,load_batch
from eval_memory_e2e.io import MemoryEvaluationError,events,read_json,verify_artifact
from eval_memory_e2e.runner import advance,next_action


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'batch'

    def test_all_native_prompts_freeze_the_same_no_codex_boundary(self):
        prepare(self.root,batch_id='boundary',seed='boundary',scenario_ids=['MEM-10'],mode='native')
        manifest=load_batch(self.root);probes=[]
        for episode in manifest['episodes']:
            steps=read_json(self.root/episode['plan_path'])['steps']
            self.assertTrue(all(s['prompt'].startswith(EXECUTION_GUARD+'\n\n') for s in steps))
            probes.extend(s['prompt'] for s in steps if s['phase']=='probe')
        self.assertEqual(len(set(probes)),1)
        self.assertNotIn('Codex',manifest['harnesses'])

    def test_transport_timeout_preserves_partial_logs_and_observe_only_state(self):
        prepare(self.root,batch_id='timeout',seed='timeout',scenario_ids=['MEM-10'],harnesses=['WorkBuddy'],mode='fixture')
        episode='WorkBuddy__MEM-10__r01__cold'
        expired=subprocess.TimeoutExpired(['driver'],180,output=b'partial stdout',stderr=b'partial stderr')
        with patch('eval_memory_e2e.runner.subprocess.run',side_effect=expired) as command:
            with self.assertRaises(MemoryEvaluationError) as error:advance(self.root,episode,driver_timeout=180)
            self.assertEqual(command.call_args.kwargs['timeout'],180)
        self.assertEqual(error.exception.code,'DRIVER_TRANSPORT_TIMEOUT')
        journal=events(self.root)
        self.assertEqual(sum(e['kind']=='INTENT' for e in journal),1)
        diagnostic=next(e['payload'] for e in journal if e['kind']=='DRIVER_DIAGNOSTIC')
        self.assertEqual(verify_artifact(self.root,diagnostic['artifacts']['stdout']),b'partial stdout')
        self.assertEqual(next_action(self.root,episode)['status'],'OBSERVE_ONLY')

    def test_invalid_transport_budget_never_invokes_a_driver(self):
        prepare(self.root,batch_id='bad-budget',seed='bad-budget',scenario_ids=['MEM-10'],harnesses=['WorkBuddy'],mode='fixture')
        with patch('eval_memory_e2e.runner.subprocess.run') as command:
            with self.assertRaises(MemoryEvaluationError):advance(self.root,'WorkBuddy__MEM-10__r01__cold',driver_timeout=True)
            command.assert_not_called()
