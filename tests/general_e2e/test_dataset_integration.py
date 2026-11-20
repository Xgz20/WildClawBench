"""Regression coverage for built-in products beside independent catalog families."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import gc
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets import bundle
from eval_general_e2e.datasets.catalog import CatalogError, load_registered_dataset
from eval_general_e2e.datasets.capability_audit import generate_capability_matrix
from eval_general_e2e.datasets.definition import DATASETS, DatasetDefinition
from eval_general_e2e.datasets.discovery import discover_frozen_tasks
from eval_general_e2e.datasets.layout import cli_category_paths, cli_task_path
from eval_general_e2e.datasets.source_history import dataset_task_path
from src.utils.task_parser import parse_task_md
from tools.report.lib.eval_dataset.selectors import select_task_files


REPO_ROOT = Path(__file__).resolve().parents[2]
CHALLENGE_MANIFEST_SHA256 = "9d29be72598a9d002a25ac4f8435ac18714a3b1343072f3e389810523350b78d"


class DatasetIntegrationTests(unittest.TestCase):
    def test_builtin_public_definitions_and_catalog_keep_the_existing_locations(self) -> None:
        self.assertIs(bundle.DatasetDefinition, DatasetDefinition)
        self.assertIs(bundle.DATASETS, DATASETS)
        challenge = load_registered_dataset(REPO_ROOT, "general-challenge")
        self.assertEqual(challenge.kind, "family")
        self.assertEqual(hashlib.sha256(challenge.manifest_path.read_bytes()).hexdigest(), CHALLENGE_MANIFEST_SHA256)
        challenge_ids = set(challenge.definition.task_ids)
        for dataset_id, definition in DATASETS.items():
            with self.subTest(dataset_id=dataset_id):
                selected = load_registered_dataset(REPO_ROOT, dataset_id, release_id=dataset_id)
                locked = bundle.load_manifest_lock(bundle.dataset_manifest_path(dataset_id))
                self.assertEqual(selected.kind, "legacy" if dataset_id == "general-custom60-v1" else "builtin")
                self.assertEqual(selected.definition.task_root, definition.task_root)
                self.assertEqual(selected.definition.workspace_root, definition.workspace_root)
                self.assertEqual(selected.definition.frozen_source_index, definition.frozen_source_index)
                self.assertEqual(selected.definition.current_source_paths, definition.current_source_paths)
                self.assertEqual(selected.definition.source_revision, locked["source"]["revision"])
                self.assertEqual(set(selected.definition.task_ids), {task["task_id"] for task in locked["tasks"]})
                self.assertFalse(challenge_ids.intersection(selected.definition.task_ids))
                with self.assertRaisesRegex(CatalogError, "only its frozen release"):
                    load_registered_dataset(REPO_ROOT, dataset_id, release_id="general-hard-v1")

    def test_explicit_selections_keep_logical_paths_and_exact_release_membership(self) -> None:
        for dataset_id in (*DATASETS, "general-challenge-v3"):
            with self.subTest(dataset_id=dataset_id):
                registered = load_registered_dataset(REPO_ROOT, dataset_id)
                result = select_task_files(REPO_ROOT, dataset_id=dataset_id)
                self.assertEqual(result.issues, [])
                self.assertEqual(len(result.files), registered.definition.expected_task_count)
                self.assertEqual({path.stem for path in result.files}, set(registered.definition.task_ids))
                self.assertTrue(all(path.is_relative_to(REPO_ROOT / "tasks") for path in result.files))
        legacy = select_task_files(REPO_ROOT, dataset_id="general-custom60-v1").files[0]
        outside = select_task_files(REPO_ROOT, dataset_id="general-challenge", task_paths=[legacy])
        self.assertEqual(outside.files, [])
        self.assertEqual([issue.code for issue in outside.issues], ["DATASET_TASK_OUTSIDE_ROOT"])

    def test_challenge_catalog_exposes_only_the_numbered_release(self) -> None:
        selected = load_registered_dataset(REPO_ROOT, "general-challenge")
        self.assertEqual(selected.definition.dataset_id, "general-challenge-v3")
        self.assertEqual(selected, load_registered_dataset(REPO_ROOT, "general-challenge-v3"))
        for retired in ("general-hard", "general-hard-v1", "general-challenge-v2"):
            with self.subTest(retired=retired), self.assertRaises(CatalogError):
                load_registered_dataset(REPO_ROOT, retired)
        with self.assertRaises(CatalogError):
            load_registered_dataset(REPO_ROOT, "general-challenge", release_id="general-challenge-v2")

    def test_numbered_challenge_cli_categories_and_legacy_task_aliases(self) -> None:
        tasks_root = REPO_ROOT / "tasks"
        old_id = "general_hard_office_documents_task_001_policy_crosswalk"
        new_id = "01_Office_Documents_task_001_policy_crosswalk"
        task = cli_task_path(REPO_ROOT, tasks_root, new_id)
        self.assertEqual(task, cli_task_path(REPO_ROOT, tasks_root, old_id))
        self.assertEqual(task, cli_task_path(REPO_ROOT, tasks_root,
                         f"tasks/general/challenge/office_documents/{old_id}.md"))
        self.assertEqual(parse_task_md(task, repo_root=REPO_ROOT)["category"], "office_documents")
        old_category = cli_category_paths(tasks_root, "general/challenge/office_documents")
        self.assertEqual(old_category, cli_category_paths(tasks_root, "general/challenge/01_Office_Documents"))
        self.assertEqual(len(old_category), 16)
        self.assertIn(task, old_category)

    def test_historical_discovery_and_both_build_interfaces_read_the_same_snapshot(self) -> None:
        definition = DATASETS["general-info004-open-v1"]
        registered = load_registered_dataset(REPO_ROOT, definition.dataset_id)
        locked = bundle.load_manifest_lock(registered.manifest_path)
        record = locked["tasks"][0]
        logical = REPO_ROOT / record["source"]["task_path"]
        archived = dataset_task_path(REPO_ROOT, record["source"]["task_path"], definition.frozen_source_index,
                                     definition.current_source_paths)
        self.assertNotEqual(archived, logical)
        self.assertEqual(hashlib.sha256(archived.read_bytes()).hexdigest(), record["digests"]["task_sha256"])
        selected = discover_frozen_tasks(REPO_ROOT, definition.dataset_id)
        expected = parse_task_md(archived, repo_root=REPO_ROOT)
        for key in ("prompt", "automated_checks", "workspace_path"):
            self.assertEqual(selected.tasks[0][key], expected[key])
        self.assertEqual(selected.identity["dataset_digest"], locked["dataset_digest"])
        audit = generate_capability_matrix(REPO_ROOT, dataset_id=definition.dataset_id)
        self.assertEqual(audit["dataset"]["dataset_digest"], locked["dataset_digest"])
        self.assertEqual(audit["summary"]["task_count"], 1)
        with tempfile.TemporaryDirectory() as temporary:
            original, catalogued = [Path(temporary) / name for name in ("original.zip", "catalogued.zip")]
            bundle.build_default_bundle(REPO_ROOT, original, definition=definition)
            bundle.build_registered_bundle(REPO_ROOT, definition.dataset_id, catalogued)
            self.assertEqual(original.read_bytes(), catalogued.read_bytes())

    def test_cli_update_lock_is_idempotent_and_rejects_frozen_manifest_changes(self) -> None:
        manifest = {"dataset_id": "general-custom70-v2", "dataset_digest": "a" * 64, "task_count": 70}
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "locked.json"
            bundle.write_manifest_lock(manifest, target)
            original = target.read_bytes()
            for selector in ([], ["--dataset", "general-custom70-v2"]):
                with self.subTest(selector=selector), patch.object(bundle, "dataset_manifest_path", return_value=target), redirect_stdout(io.StringIO()):
                    with patch.object(bundle, "compile_dataset", return_value=(manifest, [])):
                        self.assertEqual(bundle.main(["update-lock", *selector]), 0)
                    with patch.object(bundle, "compile_dataset", return_value=({**manifest, "dataset_digest": "b" * 64}, [])):
                        with self.assertRaisesRegex(FileExistsError, "new dataset version"):
                            bundle.main(["update-lock", *selector])
                    self.assertEqual(target.read_bytes(), original)

    def test_old_and_catalog_cli_selectors_dispatch_explicitly_and_reject_mixing(self) -> None:
        result = {"dataset_id": "test", "task_count": 0}
        with patch.object(bundle, "build_default_bundle", return_value=result) as legacy, redirect_stdout(io.StringIO()):
            self.assertEqual(bundle.main(["build", "--repo-root", str(REPO_ROOT), "--dataset", "general-custom70-v2"]), 0)
        self.assertIs(legacy.call_args.kwargs["definition"], DATASETS["general-custom70-v2"])
        with patch.object(bundle, "build_registered_bundle", return_value=result) as registered, redirect_stdout(io.StringIO()):
            self.assertEqual(bundle.main(["build", "--repo-root", str(REPO_ROOT), "--dataset-id", "general-challenge", "--release-id", "general-challenge-v3"]), 0)
        self.assertEqual(registered.call_args.args[1], "general-challenge")
        self.assertEqual(registered.call_args.kwargs["release_id"], "general-challenge-v3")
        for command in (["build", "--dataset", "general-custom70-v2", "--dataset-id", "general-challenge"],
                        ["build", "--release-id", "general-challenge-v3"],
                        ["build", "--dataset-id", "general-challenge", "--manifest", "another.json"]):
            with self.subTest(command=command), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                bundle.main(command)
            self.assertEqual(stopped.exception.code, 2)


class FrozenDatasetCompilationTests(unittest.TestCase):
    def test_all_builtin_and_challenge_releases_match_their_original_locks(self) -> None:
        # This matrix intentionally compiles one release at a time. Keep it out
        # of parallel test invocations: some products include large workspaces.
        for dataset_id in (*DATASETS, "general-challenge-v3"):
            with self.subTest(dataset_id=dataset_id):
                registered = load_registered_dataset(REPO_ROOT, dataset_id)
                locked = bundle.load_manifest_lock(registered.manifest_path)
                manifest, members = bundle.compile_dataset(REPO_ROOT, definition=registered.definition)
                self.assertEqual(manifest, locked)
                del members, manifest
                gc.collect()


if __name__ == "__main__":
    unittest.main()
