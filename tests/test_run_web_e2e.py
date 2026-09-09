from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/report/skills/run-web-e2e/scripts/run_web_e2e.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_web_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run_module = load_module()


TASK_IDS = ["task-1", "task-2"]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def materialize_batch(base: Path) -> tuple[Path, Path]:
    batch = base / "web-e2e-test"
    harness = batch / "harnesses/workbuddy"
    batch.mkdir(parents=True)
    batch_manifest = {
        "schema_version": "wildclawbench.web-e2e-batch/v3",
        "batch_id": "web-e2e-test",
        "source_revision": "abc123",
        "metric_profile": "artifactsbench-web-v1",
        "task_ids": TASK_IDS,
        "harnesses": ["workbuddy"],
    }
    manifest = {
        "schema_version": "wildclawbench.web-e2e-batch/v3",
        "batch_id": "web-e2e-test",
        "source_revision": "abc123",
        "metric_profile": "artifactsbench-web-v1",
        "harness": {"id": "workbuddy", "display_name": "WorkBuddy"},
        "tasks": [{"task_id": task_id} for task_id in TASK_IDS],
    }
    write_json(batch / "batch_manifest.json", batch_manifest)
    write_json(harness / "manifest.json", manifest)
    for task_id in TASK_IDS:
        workspace = harness / "execution/tasks" / task_id / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "index.html").write_text(f"<main>{task_id}</main>", encoding="utf-8")
        score_workspace = harness / "score/tasks" / task_id / "workspace"
        score_workspace.mkdir(parents=True)
        (score_workspace / "index.html").write_text(f"<main>{task_id}</main>", encoding="utf-8")
        private = harness / "score/tasks" / task_id / "private-scoring"
        private.mkdir()
        (private / "task_score.json").write_text("{}\n", encoding="utf-8")
    return batch, harness


def materialize_results(harness: Path) -> None:
    manifest = json.loads((harness / "manifest.json").read_text(encoding="utf-8"))
    write_json(harness / "execution-receipt.json", {
        "schema_version": "wildclawbench.web-e2e-execution-receipt/v1",
        "batch_id": manifest["batch_id"],
        "harness": manifest["harness"],
        "tasks": [{"task_id": task_id} for task_id in TASK_IDS],
        "integrity": {"valid": True},
    })
    write_json(harness / "submission.json", {
        "schema_version": "wildclawbench.web-e2e-submission/v1",
        "batch_id": manifest["batch_id"],
        "source_revision": manifest["source_revision"],
        "metric_profile": manifest["metric_profile"],
        "unit": {
            "model_id": "xopglm52",
            "model_display_name": "xopglm52",
            "harness_id": "workbuddy",
            "harness_display_name": "WorkBuddy",
        },
        "task_ids": TASK_IDS,
        "candidate_artifacts": [{"task_id": task_id, "valid": True} for task_id in TASK_IDS],
        "tasks": [{"identity": {"task_id": task_id}} for task_id in TASK_IDS],
    })


def declare_runtime_directory_policy(harness: Path) -> None:
    receipt_path = harness / "execution-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["runtime_directory_policy"] = run_module.runtime_directory_policy()
    write_json(receipt_path, receipt)


def init_args(root: Path, scope: str, stages: list[str], preset: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(root=str(root), scope=scope, stage=stages, preset=preset)


class RunWebE2ETest(unittest.TestCase):
    def test_no_stage_has_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch, _ = materialize_batch(Path(tmp))
            result = run_module.init_state(init_args(batch, "batch", []))
            self.assertFalse(result["created"])
            self.assertEqual(result["reason"], "no_stages_selected")
            self.assertFalse((batch / ".run-web-e2e").exists())

    def test_explicit_stages_override_preset_and_validate_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch, harness = materialize_batch(Path(tmp))
            result = run_module.init_state(init_args(harness, "unit", ["execute,score"], "admin"))
            self.assertEqual(result["state"]["selected_stages"], ["execute", "score"])
            self.assertEqual(result["state"]["selection_source"], "explicit_stages")
            with self.assertRaisesRegex(ValueError, "不允许阶段"):
                run_module.init_state(init_args(batch, "batch", ["execute"]))

    def test_init_is_idempotent_and_selection_change_requires_add_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, harness = materialize_batch(Path(tmp))
            args = init_args(harness, "unit", ["execute"])
            first = run_module.init_state(args)
            second = run_module.init_state(args)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            with self.assertRaisesRegex(ValueError, "add-stage"):
                run_module.init_state(init_args(harness, "unit", ["execute", "score"]))
            added = run_module.add_stages(init_args(harness, "unit", ["score", "package"]))
            self.assertEqual(added["state"]["selected_stages"], ["execute", "score", "package"])

    def test_resume_syncs_artifacts_without_expanding_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, harness = materialize_batch(Path(tmp))
            run_module.init_state(init_args(harness, "unit", ["execute", "score"]))
            materialize_results(harness)
            state = run_module.sync_state(harness, "unit")
            self.assertEqual(state["stages"]["execute"], "COMPLETED")
            self.assertEqual(state["stages"]["score"], "COMPLETED")
            self.assertEqual(state["stages"]["package"], "NOT_SELECTED")

    def test_export_and_import_return_are_validated_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            batch, harness = materialize_batch(base)
            materialize_results(harness)
            run_module.init_state(init_args(harness, "unit", ["package"]))
            exported = run_module.export_return(argparse.Namespace(
                package_root=str(harness), output_dir=str(base / "offline"),
            ))
            archive = Path(exported["archive"])
            receipt = Path(exported["receipt"])
            self.assertTrue(archive.is_file())
            self.assertTrue(receipt.is_file())
            before = (harness / "execution/tasks/task-1/workspace/index.html").read_bytes()
            imported = run_module.import_return(argparse.Namespace(
                batch_root=str(batch), archive=str(archive), receipt=str(receipt),
            ))
            self.assertTrue(imported["imported"])
            again = run_module.import_return(argparse.Namespace(
                batch_root=str(batch), archive=str(archive), receipt=str(receipt),
            ))
            self.assertTrue(again["idempotent"])
            self.assertEqual(before, (harness / "execution/tasks/task-1/workspace/index.html").read_bytes())
            self.assertTrue((batch / "returns/workbuddy/submission.json").is_file())

    def test_import_rejects_archive_and_receipt_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            batch, harness = materialize_batch(base)
            materialize_results(harness)
            exported = run_module.export_return(argparse.Namespace(
                package_root=str(harness), output_dir=str(base / "offline"),
            ))
            archive = Path(exported["archive"])
            receipt = Path(exported["receipt"])
            with archive.open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                run_module.import_return(argparse.Namespace(
                    batch_root=str(batch), archive=str(archive), receipt=str(receipt),
                ))

    def test_export_filters_policy_declared_execution_runtime_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, harness = materialize_batch(base)
            materialize_results(harness)
            declare_runtime_directory_policy(harness)
            workspace = harness / "execution/tasks/task-1/workspace"
            for relative in ("node_modules/pkg/index.js", ".cache/state.json", ".vite/cache.json"):
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("runtime", encoding="utf-8")

            exported = run_module.export_return(argparse.Namespace(
                package_root=str(harness), output_dir=str(base / "offline"),
            ))

            self.assertTrue((workspace / "node_modules/pkg/index.js").is_file())
            with zipfile.ZipFile(exported["archive"]) as archive:
                names = archive.namelist()
            self.assertFalse(any(
                part in run_module.IGNORED_RUNTIME_DIRS
                for name in names
                for part in Path(name).parts
            ))

    def test_export_requires_policy_for_execution_runtime_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, harness = materialize_batch(base)
            materialize_results(harness)
            modules = harness / "execution/tasks/task-1/workspace/node_modules/pkg"
            modules.mkdir(parents=True)
            (modules / "index.js").write_text("runtime", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "未获策略允许"):
                run_module.export_return(argparse.Namespace(
                    package_root=str(harness), output_dir=str(base / "offline"),
                ))

    def test_export_still_rejects_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, harness = materialize_batch(base)
            materialize_results(harness)
            declare_runtime_directory_policy(harness)
            git_dir = harness / "execution/tasks/task-1/workspace/.git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "禁止目录"):
                run_module.export_return(argparse.Namespace(
                    package_root=str(harness), output_dir=str(base / "offline"),
                ))

    def test_import_rejects_path_traversal_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            batch, _ = materialize_batch(base)
            for name, member, external_attr, message in (
                ("traversal", "root/../escape", 0, "不安全路径"),
                ("symlink", "root/link", (0o120777 << 16), "符号链接"),
            ):
                archive_path = base / f"{name}.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    info = zipfile.ZipInfo(member)
                    info.external_attr = external_attr
                    archive.writestr(info, b"bad")
                    archive.writestr("root/submission.json", b"{}")
                receipt_path = base / f"{name}.json"
                write_json(receipt_path, {
                    "schema_version": run_module.RETURN_SCHEMA,
                    "archive": {
                        "filename": archive_path.name,
                        "sha256": run_module.sha256_file(archive_path),
                        "size_bytes": archive_path.stat().st_size,
                    },
                })
                with self.assertRaisesRegex(ValueError, message):
                    run_module.import_return(argparse.Namespace(
                        batch_root=str(batch), archive=str(archive_path), receipt=str(receipt_path),
                    ))

    def test_import_rejects_wrong_batch_profile_and_missing_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            batch, harness = materialize_batch(base)
            materialize_results(harness)
            submission_path = harness / "submission.json"
            submission = json.loads(submission_path.read_text(encoding="utf-8"))
            submission["task_ids"] = ["task-1"]
            submission["tasks"] = submission["tasks"][:1]
            submission["candidate_artifacts"] = submission["candidate_artifacts"][:1]
            write_json(submission_path, submission)
            with self.assertRaisesRegex(ValueError, "submission.json"):
                run_module.export_return(argparse.Namespace(
                    package_root=str(harness), output_dir=str(base / "offline"),
                ))


if __name__ == "__main__":
    unittest.main()
