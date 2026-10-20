import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.batch import prepare, default_profiles, load_batch
from eval_memory_e2e.io import read_json, verify_artifact, MemoryEvaluationError
from eval_memory_e2e.observation import capture_state


class ObservationTests(unittest.TestCase):
    def test_scoped_workbuddy_never_falls_back_to_ordinary_memory(self):
        import json
        class ForbiddenOrdinary:
            def __truediv__(self, other):raise AssertionError('ordinary memory must not be inspected')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();root=base/'batch';home=base/'private-home'
            note=home/'memories/global/MEMORY.md';note.parent.mkdir(parents=True);note.write_text('synthetic private note')
            profiles=default_profiles();profiles['WorkBuddy']['state_observation']=True
            prepare(root,batch_id='scoped-observe',seed='scope',harnesses=['WorkBuddy'],scenario_ids=['MEM-01'],profiles=profiles)
            manifest=read_json(root/'manifest.json');manifest['profiles']['WorkBuddy']['workbuddy_scope']={'scope':'synthetic-scope'}
            (root/'manifest.json').write_text(json.dumps(manifest));ep=manifest['episodes'][0]
            request={'harness':'WorkBuddy','action':'execute_step','episode_id':ep['id'],'operation_id':'op','step_id':'s1','scope':'A'}
            with patch('eval_memory_e2e.observation.PATHS',{'workbuddy':ForbiddenOrdinary()}), \
                 patch('eval_memory_e2e.workbuddy_scope.load',return_value={'app_home':str(home)}):
                result=capture_state(root,request,'before')
            snapshot=read_json(root/result['snapshot']['path'])
            self.assertEqual([x['source_path'] for x in snapshot['files']],[str(note)])

    def test_workbuddy_workspace_store_is_observed_separately_from_global_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve(); root = base / 'batch'; store = base / 'global-memory'; store.mkdir()
            profiles = default_profiles(); profiles['WorkBuddy']['state_observation'] = True
            prepare(root, batch_id='workspace-observe', seed='scope', harnesses=['WorkBuddy'], scenario_ids=['MEM-01'], profiles=profiles)
            item = load_batch(root)['episodes'][1]; workspace = Path(item['workspaces']['A'])
            local = workspace / '.workbuddy/memory/MEMORY.md'; local.parent.mkdir(parents=True); local.write_text('workspace note')
            (store / 'MEMORY.md').write_text('global note')
            request = {'harness':'WorkBuddy','action':'execute_step','episode_id':item['id'],'operation_id':'op','step_id':'s1','scope':'A'}
            with patch('eval_memory_e2e.observation.STORE_ROOTS', {'WorkBuddy':(store,)}):
                result = capture_state(root, request, 'after')
            snapshot = read_json(root / result['snapshot']['path'])
            observed = {f['source_path']:f['channel_location'] for f in snapshot['files']}
            self.assertEqual(observed[str(local)], 'workspace_files')
            self.assertEqual(observed[str(store/'MEMORY.md')], 'native_local_files')
            self.assertFalse(snapshot['global_store_exhaustiveness_verified'])

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
