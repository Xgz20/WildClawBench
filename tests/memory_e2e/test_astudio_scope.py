import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.astudio_scope import minimal_config, create, load, freeze, bind_batch, profile_rules
from eval_memory_e2e.configuration import ASTUDIO_MEMORY_FIELDS
from eval_memory_e2e.io import MemoryEvaluationError


class AStudioScopeTests(unittest.TestCase):
    def test_import_does_not_copy_user_instructions_other_providers_or_memory(self):
        import tomllib
        result = tomllib.loads(minimal_config('''instructions = "private user notes"
model = "old-model"
[model_providers.astron-spark]
name = "Astron Spark"
base_url = "https://synthetic.invalid"
experimental_bearer_token = "synthetic-token"
unreviewed = "do not copy"
[model_providers.foreign]
api_key = "do not copy"
[memories]
use_memories = false
'''))
        self.assertNotIn('instructions', result)
        self.assertNotIn('model', result)
        self.assertEqual(set(result['model_providers']), {'astron-spark'})
        self.assertNotIn('unreviewed', result['model_providers']['astron-spark'])
        self.assertEqual(result['model_providers']['astron-spark']['experimental_bearer_token'], 'synthetic-token')
        for table, fields in ASTUDIO_MEMORY_FIELDS.items():
            expected = dict(fields)
            if table == 'memories':
                expected['generate_memories'] = False
            self.assertEqual(result[table], expected)
        self.assertTrue(tomllib.loads(minimal_config('[model_providers.astron-spark]\nname="test"\n', True))['memories']['generate_memories'])

    def _created(self, base):
        ordinary = base / 'ordinary'; ordinary.mkdir()
        desktop = ordinary / 'acode/userdata'; desktop.mkdir(parents=True)
        (desktop / 'astron-session.json').write_text(json.dumps({'uid': 'synthetic-account', 'loginMethod': 'wechat', 'modelBearerToken': 'synthetic'}))
        (ordinary / 'config.toml').write_text('[model_providers.astron-spark]\nname="Astron Spark"\n')
        (ordinary / 'memories').mkdir()
        (ordinary / 'memories/real-user.md').write_text('NEVER IMPORT THIS')
        (desktop / 'state.sqlite').write_bytes(b'synthetic-original-database')
        machine = {'debug': base / 'debug', 'acode': ordinary,
                   'overlay': ordinary / 'overlay', 'astudio_db': desktop / 'state.sqlite'}
        return machine

    def test_fresh_units_preserve_login_but_never_copy_memory_or_source_conversations(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve(); machine = self._created(base)
            with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value=machine), \
                 patch('eval_memory_e2e.astudio_scope.installation_witness', return_value={'synthetic': True}):
                first = create(base / 'debug/unit1', case_id='CASE-A', repetition=1, batch_root=base / 'debug/batch1')
                Path(first['paths']['acode'], 'memories').mkdir()
                Path(first['paths']['acode'], 'memories/fact.md').write_text('FIRST ROUND FACT')
                second = create(base / 'debug/unit2', case_id='CASE-A', repetition=2, batch_root=base / 'debug/batch2')
                self.assertEqual(first['account_fingerprint'], second['account_fingerprint'])
                self.assertNotEqual(first['unit_id'], second['unit_id'])
                self.assertFalse(Path(second['paths']['acode'], 'memories').exists())
                self.assertFalse(Path(second['paths']['astudio_db']).exists())
                self.assertEqual(Path(first['paths']['acode'], 'memories/fact.md').read_text(), 'FIRST ROUND FACT')
                self.assertFalse(any('NEVER IMPORT' in p.read_text() for p in Path(second['paths']['runtime']).rglob('*') if p.is_file()))

    def test_scope_binding_rejects_another_case_another_batch_or_multiple_repeats(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve(); machine = self._created(base)
            with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value=machine), \
                 patch('eval_memory_e2e.astudio_scope.installation_witness', return_value={'synthetic': True}):
                unit = create(base / 'debug/unit', case_id='CASE-A', repetition=1, batch_root=base / 'debug/batch')
                for root, cases, repeats in [(base / 'debug/batch', ['CASE-B'], 1),
                                             (base / 'debug/batch2', ['CASE-A'], 1),
                                             (base / 'debug/batch', ['CASE-A'], 2)]:
                    with self.assertRaises(MemoryEvaluationError):
                        bind_batch({}, root, unit['scope'], cases, repeats)
                self.assertEqual(bind_batch({}, base / 'debug/batch', unit['scope'], ['CASE-A'], 1)['isolation'], 'verified_namespace')

    def test_scope_and_installation_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve(); machine = self._created(base)
            with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value=machine), \
                 patch('eval_memory_e2e.astudio_scope.installation_witness', return_value={'synthetic': True}):
                unit = create(base / 'debug/unit', case_id='CASE-A', repetition=1, batch_root=base / 'debug/batch')
                frozen = freeze(unit['scope'])
                data = json.loads(Path(unit['scope']).read_text()); data['case_id'] = 'CASE-B'
                Path(unit['scope']).write_text(json.dumps(data))
                with self.assertRaises(MemoryEvaluationError):
                    load(unit['scope'], frozen)
                with patch('eval_memory_e2e.astudio_scope.installation_witness', return_value={'synthetic': False}):
                    with self.assertRaises(MemoryEvaluationError):
                        load(unit['scope'])

    def test_policy_protects_ordinary_home_all_old_evidence_and_outside_write_caches(self):
        spec = {'paths': {'runtime': '/Users/synthetic/debug/unit/runtime',
                          'candidate': '/Users/synthetic/debug/batch/candidate'}}
        with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value={
                'debug': Path('/Users/synthetic/debug'), 'acode': Path('/Users/synthetic/.acode')}):
            source = profile_rules(spec, '/Users/synthetic/debug/lease/synthetic/allowed')
        self.assertIn('(subpath "/Users/synthetic/.acode")', source)
        self.assertIn('(subpath "/System/Volumes/Data/Users/synthetic/debug")', source)
        self.assertIn('(deny file-write* (require-all', source)
        self.assertIn('(require-not (subpath "/Users/synthetic/debug/unit/runtime"))', source)


if __name__ == '__main__':
    unittest.main()
