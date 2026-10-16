import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.batch import prepare, default_profiles, load_batch
from eval_memory_e2e.io import read_json, verify_artifact, MemoryEvaluationError
from eval_memory_e2e.observation import capture_state


class ObservationTests(unittest.TestCase):
    def test_snapshot_distinguishes_before_and_after_replacement_without_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve(); root = base / 'batch'; store = base / 'native-memory'; store.mkdir()
            profiles = default_profiles(); profiles['QwenWork']['state_observation'] = True
            prepare(root, batch_id='observe', seed='observe', harnesses=['QwenWork'], scenario_ids=['MEM-01'], profiles=profiles)
            item = load_batch(root)['episodes'][1]
            facts = read_json(root / 'private/scenarios.json')[item['private_key']]['facts']
            request = {'harness': 'QwenWork', 'action': 'execute_step', 'episode_id': item['id'], 'operation_id': 'test-observation', 'step_id': 's1'}
            note = store / 'daily.md'; note.write_text(facts['project'] + '\n' + facts['code'])
            with patch('eval_memory_e2e.observation.STORE_ROOTS', {'QwenWork': (store,)}):
                before = capture_state(root, request, 'before')
                self.assertEqual(capture_state(root, request, 'before'), before)
                note.write_text('A later maintenance summary with no target facts')
                after = capture_state(root, request, 'after')
            one, two = [read_json(root / v['snapshot']['path']) for v in (before, after)]
            self.assertTrue(one['files'][0]['scoped_text_presence']['code'])
            self.assertFalse(two['files'][0]['scoped_text_presence']['code'])
            self.assertFalse(two['semantic_fact_retention_verified'])
            self.assertFalse(two['formation_event_verified'])
            self.assertEqual((root / before['snapshot']['path']).stat().st_mode & 0o777, 0o600)
            verify_artifact(root, one['files'][0]['artifact'])

    def test_codex_rejected_before_reading_any_manifest_or_store(self):
        with patch('eval_memory_e2e.observation.read_json') as read:
            with self.assertRaises(MemoryEvaluationError): capture_state('/unused', {'harness': 'Codex'}, 'before')
            read.assert_not_called()
