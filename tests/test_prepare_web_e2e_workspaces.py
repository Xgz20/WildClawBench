from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
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
    )


class PrepareWebE2EWorkspacesTest(unittest.TestCase):
    TASK_ID = "07_Website_Generation_task_001_daymark_product_website"
    FIXTURE_TASK_ID = "07_Website_Generation_task_010_paperwork_pdf_tool"

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

            self.assertTrue((execution_task / "workspace/.gitkeep").is_file())
            self.assertTrue((execution_task / "PROMPT.md").is_file())
            self.assertNotIn("/tmp_workspace", (execution_task / "PROMPT.md").read_text(encoding="utf-8"))
            self.assertFalse((execution_task / "private-scoring").exists())
            self.assertTrue((score_task / "private-scoring/task_contract.json").is_file())
            self.assertTrue((score_task / ".agents/skills/score-web-e2e/SKILL.md").is_file())
            self.assertTrue((harness_root / "tools/prepare_scoring_workspace.py").is_file())
            self.assertTrue((harness_root / "准备评分工作空间.command").is_file())
            self.assertTrue((harness_root / "准备评分工作空间.cmd").is_file())

            manifest = json.loads((harness_root / "manifest.json").read_text(encoding="utf-8"))
            entry = manifest["tasks"][0]
            self.assertEqual(entry["execution_dir"], f"execution/tasks/{self.TASK_ID}")
            self.assertEqual(entry["scoring_dir"], f"score/tasks/{self.TASK_ID}")
            self.assertEqual(entry["prompt_file"], f"execution/tasks/{self.TASK_ID}/PROMPT.md")

            prefix = "web-smoke__codex/"
            with zipfile.ZipFile(execution_package) as archive:
                execution_names = archive.namelist()
                command_info = archive.getinfo(f"{prefix}准备评分工作空间.command")
            with zipfile.ZipFile(scoring_package) as archive:
                scoring_names = archive.namelist()
            self.assertTrue(all(name.startswith(prefix) for name in execution_names))
            self.assertIn(f"{prefix}score/", execution_names)
            self.assertTrue(any(name.endswith(f"execution/tasks/{self.TASK_ID}/PROMPT.md") for name in execution_names))
            self.assertFalse(any("private-scoring" in name for name in execution_names))
            self.assertTrue(all(name.startswith("score/") for name in scoring_names))
            self.assertTrue(any(name.endswith(".agents/skills/score-web-e2e/SKILL.md") for name in scoring_names))
            self.assertFalse(any("/workspace/" in name for name in scoring_names))
            self.assertFalse(any(name.endswith(("PROMPT.md", "execution_record.json", "task_manifest.json")) for name in scoring_names))
            self.assertTrue((command_info.external_attr >> 16) & 0o100)

            contract = json.loads((score_task / "private-scoring/task_contract.json").read_text(encoding="utf-8"))
            self.assertFalse(Path(contract["source"]["task_file"]).is_absolute())

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
            self.assertEqual(
                sorted(path.name for path in fixtures.iterdir()),
                ["sample-2-pages.pdf", "sample-4-pages.pdf", "sample-image-a.png", "sample-image-b.png"],
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
            self.assertTrue((task_root / ".agents/skills/score-web-e2e/SKILL.md").is_file())
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


if __name__ == "__main__":
    unittest.main()
