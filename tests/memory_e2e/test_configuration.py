import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.configuration import configuration_probe, set_memory_feature, set_toml_fields, ASTUDIO_MEMORY_FIELDS, _replace_owned
import tomllib
from eval_memory_e2e.io import MemoryEvaluationError


class ConfigurationTests(unittest.TestCase):
    def test_codex_rejected_before_any_io(self):
        with patch('eval_memory_e2e.configuration.subprocess.run') as command:
            with self.assertRaisesRegex(MemoryEvaluationError, 'Codex is excluded'):
                configuration_probe('/not-created', ['Codex'], True)
            command.assert_not_called()

    def test_feature_editor_preserves_unrelated_sections_and_comments(self):
        source = '# keep\n[features] # flags\nmemories = false # retained\nother = true\n[model]\nname = "model-x"\n'
        changed = set_memory_feature(source, True)
        self.assertEqual(changed, source.replace('memories = false', 'memories = true'))
        self.assertEqual(set_memory_feature(changed, False), source)

    def test_feature_table_is_added_without_rewriting_existing_config(self):
        source = 'model = "model-x"\n'
        self.assertTrue(set_memory_feature(source, True).startswith(source))

    def test_dotted_feature_table_is_refused_without_overwriting(self):
        with self.assertRaises(MemoryEvaluationError):
            set_memory_feature('features.memories = false\n', True)

    def test_restore_never_overwrites_a_concurrent_user_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.toml'
            path.write_bytes(b'user changed configuration\n')
            with self.assertRaises(MemoryEvaluationError):
                _replace_owned(path, b'our previous bytes\n', b'original\n', path.stat().st_mode)
            self.assertEqual(path.read_bytes(), b'user changed configuration\n')

    def test_full_memory_configuration_preserves_unrelated_values_and_comments(self):
        source = '# keep\nmodel = "main-model"\n[features] # flags\nmemories = false # gate\nother = true\n[memories]\nuse_memories = false # read\nextract_model = "old"\n[other]\nvalue = "untouched"\n'
        changed = source
        for table, fields in ASTUDIO_MEMORY_FIELDS.items():
            changed = set_toml_fields(changed, table, fields)
        parsed = tomllib.loads(changed)
        for table, fields in ASTUDIO_MEMORY_FIELDS.items():
            for key, value in fields.items():
                self.assertEqual(parsed[table][key], value)
        self.assertIn('memories = true # gate', changed)
        self.assertIn('use_memories = true # read', changed)
        self.assertEqual(parsed['model'], 'main-model')
        self.assertEqual(parsed['other']['value'], 'untouched')

    def test_removing_our_added_fields_keeps_other_concurrent_edits(self):
        text = '[memories]\nextract_model = "spark-x2.5"\nother = "user edit"\n'
        changed = set_toml_fields(text, 'memories', {'extract_model': None})
        self.assertEqual(tomllib.loads(changed)['memories'], {'other': 'user edit'})

    def test_full_editor_refuses_unreviewed_keys_and_dotted_tables(self):
        with self.assertRaises(MemoryEvaluationError):
            set_toml_fields('', 'features', {'unrelated': True})
        with self.assertRaises(MemoryEvaluationError):
            set_toml_fields('memories.use_memories = false\n', 'memories', {'use_memories': True})
