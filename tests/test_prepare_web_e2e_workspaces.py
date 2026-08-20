from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = REPO_ROOT / ".agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py"
FALLBACK_SCRIPT = REPO_ROOT / ".agents/skills/prepare-web-e2e-workspaces/scripts/prepare_scoring_workspace.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


prepare_module = load_module("prepare_web_e2e_workspaces", PREPARE_SCRIPT)
fallback_module = load_module("prepare_scoring_workspace", FALLBACK_SCRIPT)


def args_for(tmp: str, task_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(REPO_ROOT),
        output_dir=tmp,
        batch_id="web-smoke",
        task_id=[task_id],
        harness=["codex"],
        model="gpt-5.5",
        model_map=[],
        aesthetic_rubric="",
        include_execution_record=False,
    )


class PrepareWebE2EWorkspacesTest(unittest.TestCase):
    TASK_ID = "07_Website_Generation_task_001_daymark_product_website"
    FIXTURE_TASK_ID = "07_Website_Generation_task_010_paperwork_pdf_tool"

    def test_default_batch_id_includes_hours_minutes_and_seconds(self) -> None:
        fixed = datetime(2026, 8, 20, 14, 35, 42, tzinfo=timezone.utc)
        self.assertEqual(prepare_module.default_batch_id(fixed), "web-e2e-20260820-143542")
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.batch_id = ""
            batch_root = prepare_module.prepare(args)
            self.assertRegex(batch_root.name, r"^web-e2e-\d{8}-\d{6}$")

    def test_parses_real_web_task_contract(self) -> None:
        task = prepare_module.parse_task(REPO_ROOT, self.TASK_ID)
        self.assertEqual(task["task_id"], self.TASK_ID)
        self.assertIn("package.json", task["prompt"])
        self.assertTrue(task["expected_behavior"])
        self.assertGreater(len(task["criteria"]), 0)
        self.assertAlmostEqual(sum(item["weight"] for item in task["criteria"]), 1.0, places=3)

    def test_rewrites_execution_and_scoring_paths_without_prefix_collision(self) -> None:
        prompt = "在 /tmp_workspace 下创建，读取 /tmp_workspace/a.png；保留 /tmp_workspace_backup。"
        rewritten, mapping = prepare_module.rewrite_execution_text(prompt)
        self.assertEqual(rewritten, "在 ./workspace 下创建，读取 ./workspace/a.png；保留 /tmp_workspace_backup。")
        self.assertEqual(mapping, {"/tmp_workspace": "./workspace"})
        rubric = "上传 /tmp_workspace_eval/a.png，检查 /tmp_workspace/out.txt。"
        self.assertEqual(
            prepare_module.rewrite_scoring_text(rubric),
            "上传 ./private-scoring/fixtures/a.png，检查 ./workspace/out.txt。",
        )

    def test_builds_execution_and_score_overlay_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            harness_root = batch_root / "harnesses/codex"
            execution_task = harness_root / "execution/tasks" / self.TASK_ID
            score_task = harness_root / "score/tasks" / self.TASK_ID
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            skill_package = batch_root / "packages/web-smoke__score-web-e2e-skill.zip"

            self.assertTrue((execution_task / "workspace/.gitkeep").is_file())
            self.assertTrue((execution_task / "PROMPT.md").is_file())
            self.assertEqual(sorted(path.name for path in execution_task.iterdir()), ["PROMPT.md", "workspace"])
            self.assertNotIn("/tmp_workspace", (execution_task / "PROMPT.md").read_text(encoding="utf-8"))
            self.assertFalse((execution_task / "private-scoring").exists())
            self.assertFalse((execution_task / "task_manifest.json").exists())
            self.assertFalse((execution_task / "execution_record.json").exists())
            self.assertTrue((score_task / "private-scoring/task_contract.json").is_file())
            self.assertFalse((score_task / ".agents").exists())
            self.assertTrue(skill_package.is_file())
            self.assertTrue((harness_root / "tools/prepare_scoring_workspace.py").is_file())
            self.assertTrue((harness_root / "准备评分工作空间.command").is_file())
            self.assertTrue((harness_root / "准备评分工作空间.cmd").is_file())

            manifest = json.loads((harness_root / "manifest.json").read_text(encoding="utf-8"))
            entry = manifest["tasks"][0]
            self.assertEqual(entry["execution_dir"], f"execution/tasks/{self.TASK_ID}")
            self.assertEqual(entry["prompt_file"], f"execution/tasks/{self.TASK_ID}/PROMPT.md")
            self.assertNotIn("scoring_dir", entry)
            self.assertNotIn("scoring_fixture_files", entry)
            self.assertNotIn("model", manifest)
            self.assertFalse(manifest["execution_record_included"])

            prefix = "web-smoke__codex/"
            with zipfile.ZipFile(execution_package) as archive:
                execution_names = archive.namelist()
                command_info = archive.getinfo(f"{prefix}准备评分工作空间.command")
            with zipfile.ZipFile(scoring_package) as archive:
                scoring_names = archive.namelist()
            with zipfile.ZipFile(skill_package) as archive:
                skill_names = archive.namelist()
            self.assertTrue(all(name.startswith(prefix) for name in execution_names))
            self.assertIn(f"{prefix}score/", execution_names)
            self.assertTrue(any(name.endswith(f"execution/tasks/{self.TASK_ID}/PROMPT.md") for name in execution_names))
            self.assertFalse(any("private-scoring" in name for name in execution_names))
            self.assertTrue(all(name.startswith("score/") for name in scoring_names))
            self.assertFalse(any(".agents/skills/score-web-e2e" in name for name in scoring_names))
            self.assertFalse(any("/workspace/" in name for name in scoring_names))
            self.assertFalse(any(name.endswith(("PROMPT.md", "execution_record.json", "task_manifest.json")) for name in scoring_names))
            self.assertIn("score-web-e2e/SKILL.md", skill_names)
            self.assertTrue(any(name.startswith("score-web-e2e/scripts/") for name in skill_names))
            self.assertTrue((command_info.external_attr >> 16) & 0o100)

            contract = json.loads((score_task / "private-scoring/task_contract.json").read_text(encoding="utf-8"))
            self.assertFalse(Path(contract["source"]["task_file"]).is_absolute())
            self.assertEqual(contract["identity"]["task_id"], self.TASK_ID)
            self.assertEqual(contract["identity"]["harness"]["id"], "codex")
            self.assertNotIn("model", contract["identity"])

    def test_execution_record_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.include_execution_record = True
            batch_root = prepare_module.prepare(args)
            task_root = batch_root / "harnesses/codex/execution/tasks" / self.TASK_ID
            self.assertTrue((task_root / "execution_record.json").is_file())
            self.assertFalse((task_root / "task_manifest.json").exists())
            manifest = json.loads((batch_root / "harnesses/codex/manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["execution_record_included"])

    def test_generates_one_independent_score_skill_zip_per_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.harness = ["codex", "trae"]
            batch_root = prepare_module.prepare(args)
            manifest = json.loads((batch_root / "batch_manifest.json").read_text(encoding="utf-8"))
            skill_packages = [item for item in manifest["packages"] if item["package_type"] == "score_skill"]
            self.assertEqual(len(skill_packages), 1)
            self.assertIsNone(skill_packages[0]["harness"])
            self.assertEqual(
                manifest["score_skill_archive"],
                "packages/web-smoke__score-web-e2e-skill.zip",
            )

    def test_manual_copy_then_scoring_zip_merge_materializes_score_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "manual"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            shutil.copytree(package_root / "execution/tasks", package_root / "score/tasks")
            with zipfile.ZipFile(scoring_package) as archive:
                archive.extractall(package_root)
            task_root = package_root / "score/tasks" / self.TASK_ID
            fallback_module.validate_prepared_score(package_root / "score", json.loads((package_root / "manifest.json").read_text(encoding="utf-8")))
            self.assertTrue((task_root / "workspace/.gitkeep").is_file())
            self.assertTrue((task_root / "private-scoring/task_contract.json").is_file())

    def test_copies_only_rubric_referenced_scoring_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.FIXTURE_TASK_ID))
            fixtures = batch_root / "harnesses/codex/score/tasks" / self.FIXTURE_TASK_ID / "private-scoring/fixtures"
            task = prepare_module.parse_task(REPO_ROOT, self.FIXTURE_TASK_ID)
            self.assertEqual(
                sorted(path.relative_to(fixtures).as_posix() for path in fixtures.rglob("*") if path.is_file()),
                sorted(path.as_posix() for path in prepare_module.referenced_scoring_fixtures(task)),
            )
            contract = json.loads((fixtures.parent / "task_contract.json").read_text(encoding="utf-8"))
            self.assertNotIn("/tmp_workspace_eval", contract["llm_judge_rubric"])
            self.assertIn("./private-scoring/fixtures/sample-image-a.png", contract["llm_judge_rubric"])

    def test_python_fallback_materializes_isolated_score_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            self.assertTrue((package_root / "score").is_dir())
            self.assertFalse(any((package_root / "score").iterdir()))
            score_root = fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            task_root = score_root / "tasks" / self.TASK_ID
            self.assertTrue((task_root / "workspace/.gitkeep").is_file())
            self.assertTrue((task_root / "private-scoring/task_contract.json").is_file())
            self.assertFalse((task_root / ".agents").exists())
            with self.assertRaisesRegex(FileExistsError, "拒绝覆盖"):
                fallback_module.prepare_scoring_workspace(package_root, scoring_package)

    def test_python_fallback_accepts_system_metadata_and_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            score_root = package_root / "score"
            (score_root / ".DS_Store").write_bytes(b"finder metadata")
            (score_root / "tasks/nested-empty").mkdir(parents=True)
            (score_root / "tasks/._temporary").write_bytes(b"appledouble metadata")

            prepared = fallback_module.prepare_scoring_workspace(package_root, scoring_package)

            task_root = prepared / "tasks" / self.TASK_ID
            self.assertTrue((task_root / "workspace/.gitkeep").is_file())
            self.assertTrue((task_root / "private-scoring/task_contract.json").is_file())
            self.assertFalse((prepared / ".DS_Store").exists())
            self.assertFalse((prepared / "tasks/nested-empty").exists())
            self.assertFalse((prepared / "tasks/._temporary").exists())

    def test_python_fallback_rejects_existing_scoring_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            result_path = package_root / "score/tasks" / self.TASK_ID / "private-scoring/task_score.json"
            result_path.parent.mkdir(parents=True)
            result_path.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "拒绝覆盖"):
                fallback_module.prepare_scoring_workspace(package_root, scoring_package)

    def test_python_fallback_rejects_traversal_and_candidate_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("score/../escape.txt", b"bad")
            with self.assertRaisesRegex(ValueError, "不安全路径"):
                fallback_module.extract_overlay(traversal, root / "out-traversal")

            overwrite = root / "overwrite.zip"
            with zipfile.ZipFile(overwrite, "w") as archive:
                archive.writestr(f"score/tasks/{self.TASK_ID}/PROMPT.md", b"bad")
            with self.assertRaisesRegex(ValueError, "覆盖执行产物"):
                fallback_module.extract_overlay(overwrite, root / "out-overwrite")

            embedded_skill = root / "embedded-skill.zip"
            with zipfile.ZipFile(embedded_skill, "w") as archive:
                archive.writestr(f"score/tasks/{self.TASK_ID}/.agents/skills/score-web-e2e/SKILL.md", b"bad")
            with self.assertRaisesRegex(ValueError, "非评分材料"):
                fallback_module.extract_overlay(embedded_skill, root / "out-embedded-skill")


if __name__ == "__main__":
    unittest.main()
