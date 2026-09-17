from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from eval_general_e2e.datasets.bundle import (
    DEFAULT_DEFINITION,
    compile_dataset,
    default_manifest_path,
    load_manifest_lock,
    verify_dataset_bundle,
    write_dataset_bundle,
)
from eval_general_e2e.shared.dataset_bundle.verify import _validate_bounded_symlink


REPO_ROOT = Path(__file__).resolve().parents[2]


class GeneralDatasetBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled_manifest, cls.members = compile_dataset(
            REPO_ROOT, definition=DEFAULT_DEFINITION
        )
        cls.locked_manifest = load_manifest_lock(default_manifest_path())

    def test_frozen_manifest_matches_sources_and_expected_distribution(self) -> None:
        self.assertEqual(self.compiled_manifest, self.locked_manifest)
        self.assertEqual(self.locked_manifest["task_count"], 60)
        self.assertEqual(
            self.locked_manifest["statistics"]["category_counts"],
            dict(DEFAULT_DEFINITION.expected_category_counts),
        )
        self.assertEqual(
            self.locked_manifest["statistics"]["grading_type_counts"],
            {"automated": 19, "hybrid": 35, "llm_judge": 6},
        )
        task_ids = [task["task_id"] for task in self.locked_manifest["tasks"]]
        self.assertEqual(len(task_ids), len(set(task_ids)))
        for task in self.locked_manifest["tasks"]:
            self.assertEqual(task["tags"], ["custom"])
            self.assertEqual(set(task["digests"]), {
                "task_sha256",
                "prompt_sha256",
                "execution_contract_sha256",
                "scoring_contract_sha256",
                "workspace_exec_sha256",
                "private_scoring_sha256",
            })

    def test_bundle_is_deterministic_and_verifies_without_source_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.zip"
            second = Path(tmp) / "second.zip"
            write_dataset_bundle(self.locked_manifest, self.members, first)
            write_dataset_bundle(self.locked_manifest, self.members, second)
            first_bytes = first.read_bytes()
            self.assertEqual(first_bytes, second.read_bytes())
            result = verify_dataset_bundle(first)
            self.assertEqual(result["task_count"], 60)
            self.assertEqual(
                result["dataset_digest"], self.locked_manifest["dataset_digest"]
            )
            self.assertEqual(
                result["bundle_sha256"], hashlib.sha256(first_bytes).hexdigest()
            )

    def test_bundle_preserves_bounded_cleanup_symlink_as_link_metadata(self) -> None:
        task_id = "06_Safety_Alignment_task_007_bounded_cleanup"
        task = next(
            item for item in self.locked_manifest["tasks"] if item["task_id"] == task_id
        )
        link = next(
            item
            for item in task["materials"]["execution"]["entries"]
            if item["kind"] == "symlink"
        )
        self.assertEqual(
            link["link_target"], "../../outside_guard/sentinel.txt"
        )
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "dataset.zip"
            write_dataset_bundle(self.locked_manifest, self.members, bundle)
            name = (
                f"{self.locked_manifest['dataset_id']}/"
                f"{task['materials']['execution']['root']}/{link['path']}"
            )
            with zipfile.ZipFile(bundle) as archive:
                info = archive.getinfo(name)
                self.assertTrue(stat.S_ISLNK(info.external_attr >> 16))
                self.assertEqual(
                    archive.read(info).decode("utf-8"), link["link_target"]
                )

    def test_independent_verifier_rejects_symlink_targets_that_escape_tree_root(self) -> None:
        _validate_bounded_symlink(
            "cleanup_area/cache/link_to_outside",
            "../../outside_guard/sentinel.txt",
        )
        with self.assertRaisesRegex(ValueError, "escapes its root"):
            _validate_bounded_symlink("link", "../outside")
        with self.assertRaisesRegex(ValueError, "absolute"):
            _validate_bounded_symlink("nested/link", "/outside")

    def test_verifier_rejects_modified_task_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original.zip"
            corrupted = Path(tmp) / "corrupted.zip"
            write_dataset_bundle(self.locked_manifest, self.members, original)
            target_suffix = "/tasks/01_Productivity_Flow_task_001_expense_policy_check/task.md"
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(corrupted, "w") as target:
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename.endswith(target_suffix):
                        data += b"\ncorrupted\n"
                    target.writestr(info, data)
            with self.assertRaisesRegex(ValueError, "task_sha256 mismatch"):
                verify_dataset_bundle(corrupted)

    def test_verifier_rejects_archive_traversal_before_parsing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "traversal.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            with self.assertRaisesRegex(ValueError, "archive member is unsafe"):
                verify_dataset_bundle(archive_path)

    def test_schema_identifier_matches_frozen_contract(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "eval_general_e2e/datasets/schemas/dataset-manifest-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$id"], self.locked_manifest["schema_id"])


if __name__ == "__main__":
    unittest.main()
