import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from eval_memory_e2e.batch import prepare
from eval_memory_e2e.io import MemoryEvaluationError, events
from eval_memory_e2e.runner import register_intent
from eval_memory_e2e.recovery import recover_ui_lock
from eval_memory_e2e.scoring import review_template


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name).resolve();self.root=self.parent/'batch'
        prepare(self.root,batch_id='test-recovery',seed='test-recovery',harnesses=['QwenWork'],scenario_ids=['MEM-10'],mode='native')
        self.episode='QwenWork__MEM-10__r01__cold'
        self.request=register_intent(self.root,self.episode)
        self.owner={'id':str(uuid4()),'host':socket.gethostname(),'pid':12345,'operation_id':self.request['operation_id']}
        self.lock=self.parent/'.memory-native-ui.lock';self.lock.write_text(json.dumps(self.owner))
        self.patch=patch('eval_memory_e2e.recovery.DEBUG_ROOT',self.parent);self.patch.start();self.addCleanup(self.patch.stop)

    def test_dead_owner_is_archived_without_changing_send_intent(self):
        previous=self.lock.read_bytes();before=events(self.root)
        with patch('eval_memory_e2e.recovery.os.kill',side_effect=ProcessLookupError):
            result=recover_ui_lock(self.root,self.owner['id'])
        self.assertEqual(Path(result['archive']).read_bytes(),previous)
        self.assertFalse(self.lock.exists())
        self.assertEqual(events(self.root)[:-1],before)
        self.assertFalse(result['prompt_send_attempted'])

    def test_live_or_unknown_owner_is_never_removed(self):
        with patch('eval_memory_e2e.recovery.os.kill'):
            with self.assertRaises(MemoryEvaluationError):recover_ui_lock(self.root,self.owner['id'])
        self.assertTrue(self.lock.exists())
        with self.assertRaises(MemoryEvaluationError):recover_ui_lock(self.root,str(uuid4()))
        self.assertTrue(self.lock.exists())

    def test_archive_symlink_is_rejected(self):
        other=self.parent/'other';other.mkdir();(self.root/'runtime-recovery').symlink_to(other)
        with patch('eval_memory_e2e.recovery.os.kill',side_effect=ProcessLookupError):
            with self.assertRaises(MemoryEvaluationError):recover_ui_lock(self.root,self.owner['id'])
        self.assertTrue(self.lock.exists());self.assertEqual(list(other.iterdir()),[])

    def test_immediate_smoke_cannot_enter_capability_scoring(self):
        from eval_memory_e2e.batch import default_profiles
        root=self.parent/'smoke';profiles=default_profiles();profiles['QwenWork']['memory_protocol']={'formal_scoring_allowed':False}
        prepare(root,batch_id='smoke-score',seed='smoke-score',harnesses=['QwenWork'],scenario_ids=['MEM-10'],profiles=profiles,mode='native')
        with self.assertRaisesRegex(MemoryEvaluationError,'immediate automation only'):
            review_template(root,self.episode)
