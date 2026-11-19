"""Registered releases use the same platform preparation and isolation boundary."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.e2e.common import E2EError
from src.e2e.preparation import _general_catalog
from src.utils.cli_args import build_run_batch_parser
from src.utils.dataset_selection import require_dataset_output_scope


class RegisteredPlatformCatalogTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path('/unused/source-checkout')
        self.definition = object()
        self.registered = SimpleNamespace(status='frozen', definition=self.definition,
                                          manifest_path=Path('/unused/hard-v1.json'))
        self.manifest = {'dataset_id': 'general-hard-v1', 'dataset_digest': 'a' * 64,
                         'source': {'revision': 'b' * 40},
                         'tasks': [{'task_id': 'general_hard_case', 'category': 'data_analysis'}]}

    def test_series_alias_preserves_release_identity_and_frozen_source_pin(self):
        with patch('eval_general_e2e.datasets.catalog.load_registered_dataset', return_value=self.registered), \
             patch('eval_general_e2e.datasets.bundle.load_manifest_lock', return_value=self.manifest), \
             patch('eval_general_e2e.datasets.bundle.compile_dataset', return_value=(self.manifest, [])) as compile_source:
            tasks, _, manifest = _general_catalog(self.repo, 'general-hard')
        self.assertEqual(tasks[0]['dataset'], {'id': 'general-hard-v1', 'digest': 'a' * 64})
        self.assertEqual(manifest, self.manifest)
        compile_source.assert_called_once_with(self.repo, definition=self.definition,
                                               source_revision='b' * 40)

    def test_building_release_is_rejected_before_compilation(self):
        self.registered.status = 'building'
        with patch('eval_general_e2e.datasets.catalog.load_registered_dataset', return_value=self.registered), \
             patch('eval_general_e2e.datasets.bundle.compile_dataset') as compile_source, \
             self.assertRaisesRegex(E2EError, 'GENERAL_DATASET_NOT_FROZEN'):
            _general_catalog(self.repo, 'general-hard')
        compile_source.assert_not_called()

    def test_registered_source_drift_is_rejected(self):
        drifted = deepcopy(self.manifest)
        drifted['dataset_digest'] = 'c' * 64
        with patch('eval_general_e2e.datasets.catalog.load_registered_dataset', return_value=self.registered), \
             patch('eval_general_e2e.datasets.bundle.load_manifest_lock', return_value=self.manifest), \
             patch('eval_general_e2e.datasets.bundle.compile_dataset', return_value=(drifted, [])), \
             self.assertRaisesRegex(E2EError, 'GENERAL_DATASET_SOURCE_DRIFT'):
            _general_catalog(self.repo, 'general-hard-v1')

    def test_builtin_selection_retains_its_existing_contract(self):
        with patch.dict('eval_general_e2e.datasets.bundle.DATASETS', {'sample-builtin': self.definition}), \
             patch('eval_general_e2e.datasets.bundle.dataset_manifest_path', return_value=Path('/unused/builtin.json')), \
             patch('eval_general_e2e.datasets.bundle.load_manifest_lock', return_value=self.manifest), \
             patch('eval_general_e2e.datasets.bundle.compile_dataset', return_value=(self.manifest, [])) as compile_source:
            tasks, _, _ = _general_catalog(self.repo, 'sample-builtin')
        self.assertEqual(tasks[0]['dataset']['id'], self.manifest['dataset_id'])
        compile_source.assert_called_once_with(self.repo, definition=self.definition)

    def test_cli_selectors_are_mutually_exclusive(self):
        parser = build_run_batch_parser('fixture', 1)
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            parser.parse_args(['--dataset', 'general-custom70-v5', '--dataset-id', 'general-hard-v1'])

    def test_output_scope_accepts_same_registered_identity_but_rejects_other_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'evaluation_scope.json'
            value = {'tasks': [{'dataset': {'series_id': 'general-hard', 'release_id': 'general-hard-v1',
                                            'dataset_digest': 'a' * 64, 'manifest_sha256': 'f' * 64}}]}
            path.write_text(json.dumps(value))
            require_dataset_output_scope(root, self.manifest)
            value['tasks'][0]['dataset']['dataset_digest'] = 'c' * 64
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'CLI_DATASET_OUTPUT_SCOPE_CONFLICT'):
                require_dataset_output_scope(root, self.manifest)

    def test_real_scope_writer_is_checked_before_cross_version_reuse(self):
        from eval import run_batch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = {'task_id': 'general_hard_fixture', 'category': 'data_analysis',
                    'file_path': str(root / 'absent-task.md'),
                    'dataset_selection': {'series_id': 'general-hard', 'release_id': 'general-hard-v1',
                                          'dataset_digest': 'a' * 64}}
            run_batch._write_evaluation_scope(root, [task], mode='dataset',
                categories=['data_analysis'], modality=None, include_tags=set(),
                exclude_tags=set(), runs=1, pending_tasks=[task])
            require_dataset_output_scope(root, self.manifest)
            path = root / 'evaluation_scope.json'
            document = json.loads(path.read_text())
            self.assertIn('planned_tasks', document)
            document['planned_tasks'][0]['dataset']['dataset_digest'] = 'c' * 64
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, 'CLI_DATASET_OUTPUT_SCOPE_CONFLICT'):
                require_dataset_output_scope(root, self.manifest)
