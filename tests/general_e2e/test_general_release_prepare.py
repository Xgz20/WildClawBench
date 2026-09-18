from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from eval_general_e2e.datasets.bundle import (
    DEFAULT_DEFINITION,
    compile_dataset,
    default_manifest_path,
    load_manifest_lock,
    write_dataset_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_BUILDER_PATH = REPO_ROOT / "tools/e2e-build/build_general_release.py"
PREPARE_SOURCE_PATH = (
    REPO_ROOT
    / "tools/report/skills/general-e2e/prepare-general-e2e-workspaces/scripts"
    / "prepare_general_e2e_workspaces.py"
)
FIXED_REVISION = "1" * 40
SYMLINK_TASK_ID = "06_Safety_Alignment_task_007_bounded_cleanup"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RELEASE = load_module("wildclawbench_general_release_test", RELEASE_BUILDER_PATH)
PREPARE = load_module("wildclawbench_general_prepare_test", PREPARE_SOURCE_PATH)


class GeneralReleasePrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="general-e2e-prepare-test-")
        cls.temp_root = Path(cls.temp_dir.name)
        manifest, members = compile_dataset(REPO_ROOT, definition=DEFAULT_DEFINITION)
        cls.manifest = load_manifest_lock(default_manifest_path())
        if manifest != cls.manifest:
            raise AssertionError("dataset sources no longer match the manifest lock")
        cls.dataset_bundle = cls.temp_root / "general-custom60-v1.dataset.zip"
        write_dataset_bundle(cls.manifest, members, cls.dataset_bundle)
        cls.release_root = cls.temp_root / "release-first"
        cls.release = RELEASE.build_general_release(
            REPO_ROOT,
            cls.release_root,
            release_id="fixture-release",
            source_revision=FIXED_REVISION,
        )
        cls.release_suite = Path(cls.release["suite_path"])
        cls.first_task_id = cls.manifest["tasks"][0]["task_id"]
        cls.selected_task_ids = [cls.first_task_id, SYMLINK_TASK_ID]
        cls.config = {
            "schema_id": PREPARE.CONFIG_SCHEMA_ID,
            "schema_version": 1,
            "contract_version": PREPARE.CONTRACT_VERSION,
            "bundle_protocol": PREPARE.BUNDLE_PROTOCOL,
            "batch_id": "batch-fixture",
            "task_ids": cls.selected_task_ids,
            "units": [
                {
                    "unit_id": "astronstudio-macos",
                    "task_ids": cls.selected_task_ids,
                    "harness": {
                        "id": "astronstudio",
                        "platform": "macos-arm64",
                        "version": None,
                    },
                    "model": {
                        "requested_id": "model-fixture",
                        "reasoning_effort": "high",
                    },
                    "execution_mode": "automatic",
                },
                {
                    "unit_id": "workbuddy-macos",
                    "task_ids": [cls.first_task_id],
                    "harness": {
                        "id": "workbuddy",
                        "platform": "macos-arm64",
                        "version": None,
                    },
                    "model": {
                        "requested_id": "model-fixture",
                        "reasoning_effort": None,
                    },
                    "execution_mode": "human_assisted",
                },
            ],
            "judge": {
                "protocol": "codex-agent-judge-v1",
                "model": "gpt-fixture",
                "reasoning_effort": "high",
            },
            "report": {"title": "General E2E fixture"},
        }
        cls.config_path = cls.temp_root / "prepare-config.json"
        cls.config_path.write_bytes(PREPARE.pretty_json_bytes(cls.config))
        cls.batch_parent = cls.temp_root / "prepared-first"
        cls.prepared = PREPARE.prepare_batch(
            cls.dataset_bundle,
            cls.release_suite,
            cls.config_path,
            cls.batch_parent,
        )
        cls.batch_root = Path(cls.prepared["batch_root"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_release_is_deterministic_and_catalog_exposes_mixed_readiness(self) -> None:
        second_root = self.temp_root / "release-second"
        RELEASE.build_general_release(
            REPO_ROOT,
            second_root,
            release_id="fixture-release",
            source_revision=FIXED_REVISION,
        )
        first_files = {
            path.relative_to(self.release_root).as_posix(): path.read_bytes()
            for path in self.release_root.rglob("*")
            if path.is_file()
        }
        second_files = {
            path.relative_to(second_root).as_posix(): path.read_bytes()
            for path in second_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first_files, second_files)
        catalog = json.loads(first_files["release-catalog.json"])
        self.assertEqual(
            [row["name"] for row in catalog["skills"]],
            list(PREPARE.GENERAL_SKILL_NAMES),
        )
        readiness = {
            row["name"]: (row["version"], row["implementation_status"])
            for row in catalog["skills"]
        }
        self.assertEqual(
            readiness["prepare-general-e2e-workspaces"],
            ("0.2.0", "operational"),
        )
        self.assertEqual(
            readiness["execute-general-e2e"],
            ("0.5.0", "operational"),
        )
        self.assertEqual(
            readiness["collect-general-e2e"],
            ("0.4.0", "operational"),
        )
        self.assertEqual(
            readiness["score-general-e2e"],
            ("0.7.0", "operational"),
        )
        self.assertEqual(
            readiness["orchestrate-general-e2e"],
            ("0.7.0", "operational"),
        )
        self.assertEqual(
            readiness["run-general-e2e"],
            ("0.3.0", "operational"),
        )
        self.assertEqual(
            readiness["report-general-e2e"],
            ("0.2.1", "operational"),
        )
        self.assertEqual(
            set(readiness.values()),
            {
                ("0.2.0", "operational"),
                ("0.2.1", "operational"),
                ("0.3.0", "operational"),
                ("0.4.0", "operational"),
                ("0.5.0", "operational"),
                ("0.7.0", "operational"),
            },
        )

    def test_packaged_prepare_runs_without_checkout_or_pythonpath(self) -> None:
        detached = self.temp_root / "detached"
        detached.mkdir()
        with zipfile.ZipFile(self.release_suite) as suite:
            catalog_name = next(
                name for name in suite.namelist() if name.endswith("/release-catalog.json")
            )
            catalog = json.loads(suite.read(catalog_name))
            prepare_row = next(
                row
                for row in catalog["skills"]
                if row["name"] == "prepare-general-e2e-workspaces"
            )
            root = catalog_name.split("/", 1)[0]
            prepare_zip = detached / "prepare.zip"
            prepare_zip.write_bytes(suite.read(f"{root}/{prepare_row['archive']}"))
        skill_root = RELEASE._load_skill_builder(REPO_ROOT)._safe_extract(
            prepare_zip, detached / "installed"
        )
        self.assertTrue(
            (skill_root / "vendor/e2e-shared/dataset-bundle/verify.py").is_file()
        )
        output = detached / "output"
        environment = dict(os.environ)
        environment["PYTHONPATH"] = ""
        completed = subprocess.run(
            [
                sys.executable,
                str(skill_root / "scripts/prepare_general_e2e_workspaces.py"),
                "prepare",
                "--dataset-bundle",
                str(self.dataset_bundle),
                "--release-suite",
                str(self.release_suite),
                "--config",
                str(self.config_path),
                "--output-dir",
                str(output),
            ],
            cwd=detached,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["unit_count"], 2)
        self.assertEqual(payload["task_count"], 2)

    def test_execution_and_scoring_packages_are_isolated_and_ordered(self) -> None:
        execution = (
            self.batch_root
            / "packages/batch-fixture__astronstudio-macos__execution.zip"
        )
        scoring = (
            self.batch_root
            / "packages/batch-fixture__astronstudio-macos__scoring.zip"
        )
        with zipfile.ZipFile(execution) as archive:
            names = archive.namelist()
            self.assertFalse(any("private-scoring" in name for name in names))
            self.assertFalse(any(name.endswith("/task.md") for name in names))
            manifest = json.loads(
                archive.read("batch-fixture__astronstudio-macos/manifest.json")
            )
            self.assertEqual(manifest["task_ids"], self.selected_task_ids)
            self.assertEqual(
                [task["task_id"] for task in manifest["tasks"]],
                self.selected_task_ids,
            )
            for task in manifest["tasks"]:
                prompt = archive.read(
                    f"batch-fixture__astronstudio-macos/{task['prompt']['path']}"
                )
                self.assertNotIn(b"/tmp_workspace", prompt)
                self.assertEqual(
                    task["prompt"]["sent_sha256"], hashlib.sha256(prompt).hexdigest()
                )
        with zipfile.ZipFile(scoring) as archive:
            names = archive.namelist()
            self.assertFalse(any("/workspace/" in name for name in names))
            self.assertFalse(any(name.endswith("/PROMPT.md") for name in names))
            manifest = json.loads(
                archive.read(
                    "batch-fixture__astronstudio-macos/.general-e2e/"
                    "scoring-package-manifest.json"
                )
            )
            self.assertEqual(manifest["task_ids"], self.selected_task_ids)

    def test_execution_package_preserves_dataset_symlink_metadata(self) -> None:
        execution = (
            self.batch_root
            / "packages/batch-fixture__astronstudio-macos__execution.zip"
        )
        task = next(
            task for task in self.manifest["tasks"] if task["task_id"] == SYMLINK_TASK_ID
        )
        link = next(
            entry
            for entry in task["materials"]["execution"]["entries"]
            if entry["kind"] == "symlink"
        )
        name = (
            "batch-fixture__astronstudio-macos/execution/tasks/"
            f"{SYMLINK_TASK_ID}/workspace/{link['path']}"
        )
        with zipfile.ZipFile(execution) as archive:
            info = archive.getinfo(name)
            self.assertTrue(stat.S_ISLNK(info.external_attr >> 16))
            self.assertEqual(
                archive.read(info).decode("utf-8"), link["link_target"]
            )

    def test_prepare_output_is_byte_deterministic(self) -> None:
        second = PREPARE.prepare_batch(
            self.dataset_bundle,
            self.release_suite,
            self.config_path,
            self.temp_root / "prepared-second",
        )
        second_root = Path(second["batch_root"])
        first_files = {
            path.relative_to(self.batch_root).as_posix(): path.read_bytes()
            for path in self.batch_root.rglob("*")
            if path.is_file()
        }
        second_files = {
            path.relative_to(second_root).as_posix(): path.read_bytes()
            for path in second_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first_files, second_files)

    def test_prepare_supports_the_full_frozen_sixty_task_scope(self) -> None:
        full_config = copy.deepcopy(self.config)
        full_config["batch_id"] = "batch-full60"
        full_task_ids = [task["task_id"] for task in self.manifest["tasks"]]
        full_config["task_ids"] = full_task_ids
        full_config["units"] = [copy.deepcopy(full_config["units"][0])]
        full_config["units"][0]["task_ids"] = full_task_ids
        config_path = self.temp_root / "prepare-config-full60.json"
        config_path.write_bytes(PREPARE.pretty_json_bytes(full_config))
        result = PREPARE.prepare_batch(
            self.dataset_bundle,
            self.release_suite,
            config_path,
            self.temp_root / "prepared-full60",
        )
        self.assertEqual(result["task_count"], 60)
        execution = (
            Path(result["batch_root"])
            / "packages/batch-full60__astronstudio-macos__execution.zip"
        )
        with zipfile.ZipFile(execution) as archive:
            names = archive.namelist()
            manifest = json.loads(
                archive.read("batch-full60__astronstudio-macos/manifest.json")
            )
        self.assertEqual(manifest["task_ids"], full_task_ids)
        self.assertFalse(any("private-scoring" in name for name in names))

    def test_config_rejects_out_of_order_and_unassigned_tasks(self) -> None:
        out_of_order = copy.deepcopy(self.config)
        out_of_order["task_ids"] = list(reversed(self.selected_task_ids))
        with self.assertRaisesRegex(PREPARE.PrepareError, "CONFIG_TASK_ORDER_MISMATCH"):
            PREPARE.validate_config(out_of_order, self.manifest)
        unassigned = copy.deepcopy(self.config)
        unassigned["units"] = [copy.deepcopy(unassigned["units"][1])]
        with self.assertRaisesRegex(PREPARE.PrepareError, "CONFIG_TASKS_UNASSIGNED"):
            PREPARE.validate_config(unassigned, self.manifest)

    def test_prompt_mapping_preserves_similar_non_workspace_prefix(self) -> None:
        mapped, mapping = PREPARE.map_prompt_workspace(
            "读 /tmp_workspace/input.txt，但保留 /tmp_workspace_backup/input.txt"
        )
        self.assertEqual(
            mapped,
            "读 ./workspace/input.txt，但保留 /tmp_workspace_backup/input.txt",
        )
        self.assertEqual(
            mapping,
            [{"from": "/tmp_workspace", "to": "./workspace"}],
        )

    def test_release_catalog_and_skill_tampering_fail_closed(self) -> None:
        release_directory_tampered = self.temp_root / "release-directory-tampered"
        shutil.copytree(self.release_root, release_directory_tampered)
        external_skill = next(
            (release_directory_tampered / "skills").glob("*-skill-*.zip")
        )
        external_skill.write_bytes(external_skill.read_bytes() + b"tampered")
        with self.assertRaisesRegex(RELEASE.ReleaseError, "ARTIFACT_DIGEST_MISMATCH"):
            RELEASE.verify_release_directory(release_directory_tampered)

        catalog_tampered = self.temp_root / "catalog-tampered.zip"
        with zipfile.ZipFile(self.release_suite) as source, zipfile.ZipFile(
            catalog_tampered, "w"
        ) as target:
            for info in source.infolist():
                data = source.read(info)
                if info.filename.endswith("/release-catalog.json"):
                    catalog = json.loads(data)
                    catalog["release_id"] = "tampered"
                    data = PREPARE.pretty_json_bytes(catalog)
                target.writestr(info, data)
        with self.assertRaisesRegex(PREPARE.PrepareError, "CATALOG_DIGEST_MISMATCH"):
            PREPARE.verify_release_suite(catalog_tampered)

        skill_tampered = self.temp_root / "skill-tampered.zip"
        with zipfile.ZipFile(self.release_suite) as source, zipfile.ZipFile(
            skill_tampered, "w"
        ) as target:
            changed = False
            for info in source.infolist():
                data = source.read(info)
                if not changed and info.filename.endswith(".zip"):
                    data += b"tampered"
                    changed = True
                target.writestr(info, data)
        with self.assertRaisesRegex(PREPARE.PrepareError, "ARCHIVE_DIGEST_MISMATCH"):
            PREPARE.verify_release_suite(skill_tampered)

    def test_release_traversal_duplicate_and_package_tampering_fail_closed(self) -> None:
        traversal = self.temp_root / "release-traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("suite/../escape", "unsafe")
        with self.assertRaisesRegex(PREPARE.PrepareError, "INVALID_RELATIVE_PATH"):
            PREPARE.verify_release_suite(traversal)

        duplicate = self.temp_root / "release-duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("suite/release-catalog.json", "{}")
                archive.writestr("suite/release-catalog.json", "{}")
        with self.assertRaisesRegex(PREPARE.PrepareError, "ARCHIVE_DUPLICATE_PATH"):
            PREPARE.verify_release_suite(duplicate)

        package_traversal = self.temp_root / "package-traversal.zip"
        with zipfile.ZipFile(package_traversal, "w") as archive:
            archive.writestr("batch/../../escape", "unsafe")
        batch_manifest = json.loads((self.batch_root / "manifest.json").read_bytes())
        with self.assertRaisesRegex(PREPARE.PrepareError, "INVALID_RELATIVE_PATH"):
            PREPARE._verify_execution_archive(package_traversal, batch_manifest)

        package_duplicate = self.temp_root / "package-duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(package_duplicate, "w") as archive:
                archive.writestr("batch/manifest.json", "{}")
                archive.writestr("batch/manifest.json", "{}")
        with self.assertRaisesRegex(PREPARE.PrepareError, "ARCHIVE_DUPLICATE_PATH"):
            PREPARE._verify_execution_archive(package_duplicate, batch_manifest)

        copied = self.temp_root / "tampered-batch-parent/batch-fixture"
        copied.parent.mkdir()
        shutil.copytree(self.batch_root, copied)
        execution = copied / "packages/batch-fixture__astronstudio-macos__execution.zip"
        with zipfile.ZipFile(execution) as source:
            rows = [(info, source.read(info)) for info in source.infolist()]
        with zipfile.ZipFile(execution, "w") as target:
            for info, data in rows:
                if info.filename.endswith("/PROMPT.md"):
                    data += b"tampered"
                target.writestr(info, data)
        with self.assertRaisesRegex(PREPARE.PrepareError, "BATCH_ARTIFACT_DIGEST_MISMATCH"):
            PREPARE.verify_batch(copied)


if __name__ == "__main__":
    unittest.main()
