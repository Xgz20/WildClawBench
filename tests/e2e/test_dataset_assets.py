"""Deployed dataset preparation uses content and final bundles without Git."""
from pathlib import Path
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets.bundle import compile_dataset, write_manifest_lock
from eval_general_e2e.datasets.catalog import load_registered_dataset
from eval_general_e2e.datasets.discovery import discover_frozen_tasks
from src.case_catalog import index
from src.e2e.common import E2EError
from src.e2e.dataset_assets import ASSET_ROOT, frozen_dataset, maintained_releases, publish
from tests.general_e2e import test_dataset_catalog as catalog_fixture


REPO = Path(__file__).resolve().parents[2]


class DatasetAssetsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = catalog_fixture.DatasetCatalogTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo = self.fixture.root
        self.fixture.dump(self.repo / 'datasets/case-library.yaml', {
            'scenarios': {'general': '通用'},
            'datasets': {'sample': {'name': '样例', 'scene': 'general', 'modes': ['e2e'],
                                     'task_root': 'datasets/sample/tasks', 'release_series': 'sample'}},
        })

    def compile_current(self):
        definition = load_registered_dataset(self.repo, 'sample').definition
        return compile_dataset(self.repo, definition=definition)

    def freeze(self):
        manifest, _ = self.compile_current()
        write_manifest_lock(manifest, self.fixture.base / 'manifests/sample-v1.json')
        self.fixture.family['releases']['sample-v1']['status'] = 'frozen'
        self.fixture.save_sources()
        return manifest

    def test_content_identity_needs_no_git_and_tracks_selected_materials(self):
        with patch('subprocess.run', side_effect=AssertionError('runtime must not call Git')):
            first, _ = self.compile_current()
            (self.repo / 'unrelated.txt').write_text('not a selected input')
            same, _ = self.compile_current()
            material = self.fixture.base / 'workspace/research' / self.fixture.ids[0] / 'exec/input.txt'
            material.write_text(material.read_text() + '\nchanged input')
            changed, _ = self.compile_current()
        self.assertRegex(first['source']['revision'], r'^sha256:[0-9a-f]{64}$')
        self.assertEqual(first, same)
        self.assertNotEqual(first['source']['revision'], changed['source']['revision'])
        self.assertNotEqual(first['dataset_digest'], changed['dataset_digest'])

    def test_final_bundle_can_be_read_without_git_or_original_materials(self):
        expected = self.freeze()
        output = self.repo / ASSET_ROOT
        with patch('subprocess.run', side_effect=AssertionError('runtime must not call Git')):
            publish(self.repo, output)
            # The bundle, not the editable source tree, is authoritative.
            material = self.fixture.base / 'workspace/research' / self.fixture.ids[0] / 'exec/input.txt'
            material.unlink()
            manifest, members = frozen_dataset(self.repo, 'sample')
        self.assertEqual(manifest, expected)
        self.assertTrue(any(member.path.endswith('/execution/exec/input.txt') for member in members))

    def test_missing_bundle_and_tampered_archive_fail_without_git_fallback(self):
        self.freeze()
        with patch('subprocess.run', side_effect=AssertionError('must not fall back to Git')):
            with self.assertRaisesRegex(E2EError, 'ASSETS_MISSING'):
                frozen_dataset(self.repo, 'sample')
            output = self.repo / ASSET_ROOT
            publish(self.repo, output)
            archive = output / 'datasets/sample-v1.zip'
            with archive.open('ab') as stream:
                stream.write(b'tampered')
            with self.assertRaisesRegex(E2EError, 'ASSETS_DRIFT'):
                frozen_dataset(self.repo, 'sample')

    def test_only_final_releases_are_offered_and_old_ids_cannot_start_new_batches(self):
        self.assertEqual(set(maintained_releases(REPO)), {
            'general-custom60-v1', 'general-custom70-v6', 'general-challenge60-v3', 'xiaofa-legal30-v1',
        })
        group = index(REPO, 'general-work')['datasets'][0]
        self.assertEqual([row['id'] for row in group['releases']], ['general-custom70-v6'])
        with self.assertRaisesRegex(E2EError, 'GENERAL_DATASET_RETIRED'):
            frozen_dataset(REPO, 'general-custom70-v5')
        with self.assertRaisesRegex(ValueError, 'CASE_LIBRARY_RELEASE_UNKNOWN'):
            index(REPO, 'general-work', 'general-custom70-v5')
        with self.assertRaisesRegex(E2EError, 'GENERAL_DATASET_UNKNOWN'):
            frozen_dataset(REPO, 'general-challenge-v3')

    def test_cli_release_missing_assets_never_tries_to_rebuild_from_git(self):
        self.freeze()
        (self.repo / '.wildclawbench-revision').write_text('a' * 40 + '\n')
        with patch('subprocess.run', side_effect=AssertionError('must not rebuild from Git')), \
             self.assertRaisesRegex(E2EError, 'GENERAL_DATASET_ASSETS_MISSING'):
            discover_frozen_tasks(self.repo, 'sample')
