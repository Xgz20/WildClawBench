"""Frozen CLI workspaces retain historical inputs and refuse cache drift."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets.bundle import _tree_materials, load_manifest_lock
from eval_general_e2e.datasets.discovery import discover_frozen_tasks
from eval_general_e2e.datasets.workspaces import (
    FrozenWorkspaceError, frozen_workspace_path, materialize_verified_workspaces,
)
from src.utils.dataset_selection import dataset_task_paths, require_dataset_output_scope


REPO_ROOT = Path(__file__).resolve().parents[2]


class FrozenWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.task_id = "sample_task_001_case"
        for tree, filename, data in (("exec", "run.sh", b"#!/bin/sh\nexit 0\n"),
                                     ("gt", "reference.txt", b"historical reference\n")):
            target = self.root / "source" / tree / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.root / "source/exec/run.sh").chmod(0o755)
        self.cache = self.root / "cache"

    def compile_fixture(self, link_target=None):
        if link_target is not None:
            link = self.root / "source/exec/cleanup_area/cache/link_to_outside"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(link_target)
            sentinel = self.root / "source/exec/outside_guard/sentinel.txt"
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("keep me\n")
        execution, public_members = _tree_materials(self.root / "source/exec", f"tasks/{self.task_id}/execution/exec")
        private, private_members = _tree_materials(self.root / "source/gt", f"tasks/{self.task_id}/private-scoring/gt")
        manifest = {"dataset_id": "general-custom70-v3", "dataset_digest": "a" * 64,
                    "tasks": [{"task_id": self.task_id, "category": "sample",
                               "source": {"task_path": f"tasks/sample/{self.task_id}.md"},
                               "materials": {"execution": execution, "private_scoring": private}}]}
        return manifest, [*public_members, *private_members]

    def test_materializes_verified_bytes_modes_and_isolated_release_paths(self):
        manifest, members = self.compile_fixture()
        target = materialize_verified_workspaces(manifest, members, self.cache)
        self.assertEqual(target, self.cache / manifest["dataset_id"] / manifest["dataset_digest"])
        self.assertEqual(frozen_workspace_path(manifest, self.cache, self.task_id), target / self.task_id)
        self.assertEqual((target / self.task_id / "gt/reference.txt").read_bytes(), b"historical reference\n")
        self.assertEqual(stat.S_IMODE((target / self.task_id / "exec/run.sh").stat().st_mode), 0o755)
        self.assertEqual(materialize_verified_workspaces(manifest, members, self.cache), target)
        newer = {**manifest, "dataset_digest": "b" * 64}
        self.assertNotEqual(materialize_verified_workspaces(newer, members, self.cache), target)

    def test_cache_rejects_changed_missing_extra_and_replaced_materials(self):
        manifest, members = self.compile_fixture()
        for mutation in ("changed", "missing", "extra", "symlink", "hardlink"):
            with self.subTest(mutation=mutation):
                cache = self.root / mutation
                target = materialize_verified_workspaces(manifest, members, cache)
                material = target / self.task_id / "gt/reference.txt"
                if mutation == "changed":
                    material.write_text("current unrelated reference")
                elif mutation == "missing":
                    material.unlink()
                elif mutation == "extra":
                    (target / self.task_id / "gt/unexpected.txt").write_text("extra")
                elif mutation == "symlink":
                    material.unlink()
                    material.symlink_to(self.root / "source/gt/reference.txt")
                else:
                    material.unlink()
                    os.link(self.root / "source/gt/reference.txt", material)
                with self.assertRaises(FrozenWorkspaceError):
                    materialize_verified_workspaces(manifest, members, cache)

    def test_locked_bounded_symlink_is_preserved_and_target_drift_is_rejected(self):
        manifest, members = self.compile_fixture("../../outside_guard/sentinel.txt")
        target = materialize_verified_workspaces(manifest, members, self.cache)
        link = target / self.task_id / "exec/cleanup_area/cache/link_to_outside"
        self.assertEqual(os.readlink(link), "../../outside_guard/sentinel.txt")
        self.assertEqual(link.read_text(), "keep me\n")
        materialize_verified_workspaces(manifest, members, self.cache)
        link.unlink()
        link.symlink_to("../../run.sh")
        with self.assertRaisesRegex(FrozenWorkspaceError, "LINK_DRIFT"):
            materialize_verified_workspaces(manifest, members, self.cache)

    def test_parent_filesystem_alias_does_not_reject_a_locked_bounded_link(self):
        manifest, members = self.compile_fixture("../../outside_guard/sentinel.txt")
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        alias = self.root / "parent-alias"
        alias.symlink_to(real_parent, target_is_directory=True)
        cache = alias / "cache"
        target = materialize_verified_workspaces(manifest, members, cache)
        self.assertNotEqual(target, target.resolve())
        self.assertEqual(materialize_verified_workspaces(manifest, members, cache), target)

    def test_cache_root_and_dataset_directory_cannot_be_links(self):
        manifest, members = self.compile_fixture()
        real_root = self.root / "real-root"
        real_root.mkdir()
        self.cache.symlink_to(real_root, target_is_directory=True)
        with self.assertRaisesRegex(FrozenWorkspaceError, "CACHE_LINK"):
            materialize_verified_workspaces(manifest, members, self.cache)
        self.cache.unlink()
        self.cache.mkdir()
        (self.cache / manifest["dataset_id"]).symlink_to(real_root, target_is_directory=True)
        with self.assertRaisesRegex(FrozenWorkspaceError, "CACHE_LINK"):
            materialize_verified_workspaces(manifest, members, self.cache)

    def test_link_escape_and_cross_exec_gt_targets_fail_before_publish(self):
        for link_target in ("../../../gt/reference.txt", "/tmp/reference.txt"):
            with self.subTest(link_target=link_target):
                manifest, members = self.compile_fixture()
                manifest = deepcopy(manifest)
                data = link_target.encode()
                entry = {"path": "cleanup_area/cache/link", "kind": "symlink", "mode": "0777",
                         "link_target": link_target, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                manifest["tasks"][0]["materials"]["execution"]["entries"].append(entry)
                from eval_general_e2e.datasets.bundle import BundleMember
                members.append(BundleMember(f"tasks/{self.task_id}/execution/exec/{entry['path']}", data, "symlink", 0o777))
                with self.assertRaises(ValueError):
                    materialize_verified_workspaces(manifest, members, self.cache)
                self.assertFalse(frozen_workspace_path(manifest, self.cache).exists())

    def test_bundle_material_bytes_must_match_the_verified_manifest(self):
        manifest, members = self.compile_fixture()
        members[0] = replace(members[0], data=b"unverified bytes")
        with self.assertRaisesRegex(FrozenWorkspaceError, "BUNDLE_BYTES_MISMATCH"):
            materialize_verified_workspaces(manifest, members, self.cache)

    def test_legacy_selector_materializes_once_without_changing_return_contract(self):
        manifest, members = self.compile_fixture()
        with patch("eval_general_e2e.datasets.bundle.compile_dataset", return_value=(manifest, members)) as compiler, \
                patch("eval_general_e2e.datasets.bundle.load_manifest_lock", return_value=manifest), \
                patch("eval_general_e2e.datasets.source_history.dataset_task_path", side_effect=lambda repo, relative, *args: repo / relative):
            selected, groups = dataset_task_paths(REPO_ROOT, manifest["dataset_id"], materialize_root=self.cache)
        compiler.assert_called_once()
        self.assertEqual(selected, manifest)
        self.assertEqual(groups, {"sample": [REPO_ROOT / manifest["tasks"][0]["source"]["task_path"]]})
        self.assertTrue((frozen_workspace_path(manifest, self.cache, self.task_id) / "gt/reference.txt").is_file())

    def test_discovery_materializes_historical_gt_instead_of_current_reference(self):
        dataset = "general-info004-open-v1"
        manifest = load_manifest_lock(REPO_ROOT / f"eval_general_e2e/datasets/manifests/{dataset}.json")
        record = manifest["tasks"][0]
        current = REPO_ROOT / record["source"]["workspace_path"] / "gt/reference_answer.md"
        current_before = current.read_bytes()
        selected = discover_frozen_tasks(REPO_ROOT, dataset, workspace_cache=self.cache)
        material = Path(selected.tasks[0]["workspace_path"]) / "gt/reference_answer.md"
        expected = next(entry for entry in record["materials"]["private_scoring"]["entries"] if entry["path"] == "reference_answer.md")
        self.assertEqual(hashlib.sha256(material.read_bytes()).hexdigest(), expected["sha256"])
        self.assertNotEqual(material.read_bytes(), current_before)
        self.assertEqual(current.read_bytes(), current_before)
        material.write_text("tampered cache")
        with self.assertRaisesRegex(FrozenWorkspaceError, "BYTES_DRIFT"):
            discover_frozen_tasks(REPO_ROOT, dataset, workspace_cache=self.cache)


class DatasetOutputScopeTests(unittest.TestCase):
    def test_planned_tasks_are_checked_even_when_legacy_tasks_claim_matching_identity(self):
        manifest = {"dataset_id": "sample-v1", "dataset_digest": "a" * 64}
        valid = {"dataset": {"id": "sample-v1", "digest": "a" * 64}}
        rich = {"dataset": {"release_id": "sample-v1", "dataset_digest": "a" * 64}}
        invalid = {"dataset": {"release_id": "sample-v1", "dataset_digest": "b" * 64}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = [({"planned_tasks": [invalid], "tasks": [valid]}, False),
                     ({"planned_tasks": [rich], "planned_task_count": 1}, True),
                     ({"planned_tasks": [rich], "planned_task_count": 2}, False),
                     ({"planned_tasks": [{}]}, False),
                     ({"tasks": [valid]}, True), ({"tasks": [invalid]}, False)]
            for payload, accepted in cases:
                with self.subTest(payload=payload):
                    (root / "evaluation_scope.json").write_text(json.dumps(payload))
                    if accepted:
                        require_dataset_output_scope(root, manifest)
                    else:
                        with self.assertRaisesRegex(ValueError, "CLI_DATASET_OUTPUT_SCOPE_CONFLICT"):
                            require_dataset_output_scope(root, manifest)


if __name__ == "__main__":
    unittest.main()
