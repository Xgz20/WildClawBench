from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = REPO_ROOT / ".agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py"
FALLBACK_SCRIPT = REPO_ROOT / ".agents/skills/prepare-web-e2e-workspaces/scripts/prepare_scoring_workspace.py"
INIT_SCORE = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/init_score.mjs"
FINALIZE_SCORE = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/finalize_score.mjs"
BUILD_SUBMISSION = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/build_submission.mjs"
SCORING_CONTROL = REPO_ROOT / ".agents/skills/orchestrate-web-e2e/scripts/scoring-control.mjs"
CHECK_SKILLS = REPO_ROOT / ".agents/skills/run-web-e2e/scripts/check_web_e2e_skills.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


prepare_module = load_module("prepare_web_e2e_workspaces", PREPARE_SCRIPT)
fallback_module = load_module("prepare_scoring_workspace", FALLBACK_SCRIPT)
check_skills_module = load_module("check_web_e2e_skills", CHECK_SKILLS)


def materialize_execution_receipt(package_root: Path, *, model_mode: str = "explicit") -> None:
    manifest = json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
    tasks = []
    for entry in manifest["tasks"]:
        snapshot = fallback_module.snapshot_workspace(
            package_root / "execution" / "tasks" / entry["task_id"] / "workspace"
        )
        tasks.append({
            "task_id": entry["task_id"],
            "attempt_id": f"attempt-{entry['task_id']}",
            "model_selection": {
                "mode": model_mode,
                "requested_model": "gpt-5.5" if model_mode == "explicit" else None,
                "actual_model": "gpt-5.5",
                "method": "test-readback",
            },
            "workspace": {
                "final_sha256": snapshot["sha256"],
                "receipt_check_sha256": snapshot["sha256"],
                "receipt_check_matches_final": True,
            },
        })
    (package_root / "execution-receipt.json").write_text(
        json.dumps({
            "schema_version": "wildclawbench.web-e2e-execution-receipt/v1",
            "generated_at": "2026-09-06T00:00:00Z",
            "batch_id": manifest["batch_id"],
            "run_id": "test-run",
            "harness": manifest["harness"],
            "model": {"id": "gpt-5.5", "display_name": "gpt-5.5"},
            "tasks": tasks,
            "integrity": {"valid": True, "workspaces_match_final": True},
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def args_for(tmp: str, task_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(REPO_ROOT),
        output_dir=tmp,
        batch_id="web-smoke",
        task_id=[task_id],
        harness=["codex"],
        model="gpt-5.5",
        model_map=[],
        reasoning_effort="high",
        reasoning_effort_map=[],
        metric_profile="auto",
        aesthetic_rubric="",
        include_execution_record=False,
    )


class PrepareWebE2EWorkspacesTest(unittest.TestCase):
    def test_known_harness_display_names_include_current_desktop_clients(self) -> None:
        self.assertEqual(prepare_module.KNOWN_HARNESSES["astronstudio"], "AstronStudio")
        self.assertEqual(prepare_module.KNOWN_HARNESSES["qwenwork"], "QwenWork")
        self.assertEqual(prepare_module.KNOWN_HARNESSES["workbuddy"], "WorkBuddy")
        self.assertEqual(prepare_module.KNOWN_HARNESSES["doubaowork"], "DoubaoWork")

    TASK_ID = "07_Website_Generation_task_001_daymark_product_website"
    FIXTURE_TASK_ID = "07_Website_Generation_task_010_paperwork_pdf_tool"
    ARTIFACTSBENCH_TASK_ID = "07_Website_Generation_task_ab020_magic_academy_game"

    def test_python_and_node_candidate_hash_implementations_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            (root / "nested").mkdir(parents=True)
            (root / "index.html").write_text("<main>ok</main>", encoding="utf-8")
            (root / "nested/app.js").write_text("console.log('ok')", encoding="utf-8")
            (root / "中文页面.html").write_text("中文", encoding="utf-8")
            (root / "Ångström.txt").write_text("accent", encoding="utf-8")
            (root / "😀.txt").write_text("emoji", encoding="utf-8")
            (root / "node_modules/pkg").mkdir(parents=True)
            (root / "node_modules/pkg/index.js").write_text("ignored", encoding="utf-8")
            (root / "link.js").symlink_to("nested/app.js")
            python_hash = fallback_module.snapshot_workspace(root)["sha256"]
            script = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/workspace-integrity.mjs"
            result = subprocess.run(
                [
                    "node", "--input-type=module", "-e",
                    f"import {{ snapshotWorkspace }} from {json.dumps(script.as_uri())};"
                    f"process.stdout.write(snapshotWorkspace({json.dumps(str(root))}).sha256);",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, python_hash)

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
        self.assertIn("/tmp_workspace", task["prompt"])
        self.assertTrue(task["expected_behavior"])
        self.assertGreater(len(task["criteria"]), 0)
        self.assertAlmostEqual(sum(item["weight"] for item in task["criteria"]), 1.0, places=3)

    def test_parses_artifactsbench_profile_without_seed_workspace(self) -> None:
        task = prepare_module.parse_task(REPO_ROOT, self.ARTIFACTSBENCH_TASK_ID)
        self.assertEqual(task["metric_profile"], prepare_module.ARTIFACTSBENCH_PROFILE)
        self.assertIsNone(task["exec_dir"])
        self.assertEqual(len(task["criteria"]), 10)
        self.assertEqual(task["scoring"]["raw_scale"], {"minimum": 0, "maximum": 10, "step": 1})
        self.assertEqual(task["criteria"][8]["evidence_policy"]["required_types"], ["screenshot"])
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
            score_skill_package = batch_root / "packages/score-web-e2e-skill-v4.4.1.zip"
            report_skill_package = batch_root / "packages/report-web-e2e-skill-v1.0.1.zip"
            orchestrate_skill_package = batch_root / "packages/orchestrate-web-e2e-skill-v0.1.1.zip"
            execute_skill_package = batch_root / "packages/execute-web-e2e-skill-v1.8.3.zip"
            run_skill_package = batch_root / "packages/run-web-e2e-skill-v1.0.1.zip"
            skills_manifest_path = batch_root / "packages/skills-manifest.json"
            report_config_path = batch_root / "web-smoke__report-config.yaml"

            self.assertTrue((execution_task / "workspace/.gitkeep").is_file())
            self.assertTrue((execution_task / "PROMPT.md").is_file())
            self.assertEqual(sorted(path.name for path in execution_task.iterdir()), ["PROMPT.md", "workspace"])
            self.assertNotIn("/tmp_workspace", (execution_task / "PROMPT.md").read_text(encoding="utf-8"))
            self.assertFalse((execution_task / "private-scoring").exists())
            self.assertFalse((execution_task / "task_manifest.json").exists())
            self.assertFalse((execution_task / "execution_record.json").exists())
            self.assertTrue((score_task / "private-scoring/task_contract.json").is_file())
            self.assertFalse((score_task / ".agents").exists())
            self.assertTrue(score_skill_package.is_file())
            self.assertTrue(report_skill_package.is_file())
            self.assertTrue(orchestrate_skill_package.is_file())
            self.assertTrue(execute_skill_package.is_file())
            self.assertTrue(run_skill_package.is_file())
            self.assertTrue(skills_manifest_path.is_file())
            self.assertTrue(report_config_path.is_file())
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
            self.assertEqual(manifest["scoring_skill"]["name"], "score-web-e2e")
            self.assertEqual(manifest["scoring_skill"]["version"], "4.4.1")
            self.assertIn(manifest["metric_profile"], manifest["scoring_skill"]["supported_metric_profiles"])
            self.assertEqual(len(manifest["required_skills"]), 5)

            prefix = "web-smoke__codex/"
            with zipfile.ZipFile(execution_package) as archive:
                execution_names = archive.namelist()
                command_info = archive.getinfo(f"{prefix}准备评分工作空间.command")
            with zipfile.ZipFile(scoring_package) as archive:
                scoring_names = archive.namelist()
            with zipfile.ZipFile(score_skill_package) as archive:
                score_skill_names = archive.namelist()
            with zipfile.ZipFile(report_skill_package) as archive:
                report_skill_names = archive.namelist()
            with zipfile.ZipFile(orchestrate_skill_package) as archive:
                orchestrate_skill_names = archive.namelist()
            with zipfile.ZipFile(execute_skill_package) as archive:
                execute_skill_names = archive.namelist()
            with zipfile.ZipFile(run_skill_package) as archive:
                run_skill_names = archive.namelist()
            self.assertTrue(all(name.startswith(prefix) for name in execution_names))
            self.assertIn(f"{prefix}score/", execution_names)
            self.assertTrue(any(name.endswith(f"execution/tasks/{self.TASK_ID}/PROMPT.md") for name in execution_names))
            self.assertFalse(any("private-scoring" in name for name in execution_names))
            self.assertTrue(all(name.startswith("score/") for name in scoring_names))
            self.assertFalse(any(".agents/skills/score-web-e2e" in name for name in scoring_names))
            self.assertFalse(any("/workspace/" in name for name in scoring_names))
            self.assertFalse(any(name.endswith(("PROMPT.md", "execution_record.json", "task_manifest.json")) for name in scoring_names))
            self.assertFalse(any(name.endswith("__report-config.yaml") for name in execution_names))
            self.assertFalse(any(name.endswith("__report-config.yaml") for name in scoring_names))
            self.assertIn("score-web-e2e/SKILL.md", score_skill_names)
            self.assertIn("score-web-e2e/skill-metadata.json", score_skill_names)
            self.assertTrue(any(name.startswith("score-web-e2e/scripts/") for name in score_skill_names))
            self.assertIn("score-web-e2e/references/aesthetic-rubric.json", score_skill_names)
            self.assertIn("score-web-e2e/references/browser-interaction-scoring.md", score_skill_names)
            self.assertIn("score-web-e2e/scripts/workspace-integrity.mjs", score_skill_names)
            self.assertIn("score-web-e2e/scripts/managed_runtime.mjs", score_skill_names)
            self.assertIn("score-web-e2e/scripts/screenshot_receiver.mjs", score_skill_names)
            self.assertIn("report-web-e2e/SKILL.md", report_skill_names)
            self.assertIn("report-web-e2e/skill-metadata.json", report_skill_names)
            self.assertIn("report-web-e2e/scripts/aggregate_web_e2e_results.py", report_skill_names)
            self.assertIn("report-web-e2e/scripts/build_web_e2e_workbook.mjs", report_skill_names)
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") or name.endswith(".DS_Store") for name in report_skill_names))
            self.assertIn("orchestrate-web-e2e/SKILL.md", orchestrate_skill_names)
            self.assertIn("orchestrate-web-e2e/skill-metadata.json", orchestrate_skill_names)
            self.assertIn("orchestrate-web-e2e/scripts/scoring-control.mjs", orchestrate_skill_names)
            self.assertIn("orchestrate-web-e2e/drivers/codex-desktop/package-lock.json", orchestrate_skill_names)
            self.assertFalse(any("node_modules" in name for name in orchestrate_skill_names))
            self.assertIn("execute-web-e2e/SKILL.md", execute_skill_names)
            self.assertIn("execute-web-e2e/skill-metadata.json", execute_skill_names)
            self.assertIn("execute-web-e2e/drivers/workbuddy/batch.mjs", execute_skill_names)
            self.assertIn("execute-web-e2e/drivers/astronstudio/driver.mjs", execute_skill_names)
            self.assertIn("execute-web-e2e/drivers/astronstudio/batch.mjs", execute_skill_names)
            self.assertIn("execute-web-e2e/drivers/astronstudio/package-lock.json", execute_skill_names)
            self.assertIn("execute-web-e2e/scripts/run-astronstudio.sh", execute_skill_names)
            self.assertIn("execute-web-e2e/scripts/run-astronstudio-batch.sh", execute_skill_names)
            self.assertFalse(any("node_modules" in name for name in execute_skill_names))
            self.assertIn("run-web-e2e/SKILL.md", run_skill_names)
            self.assertIn("run-web-e2e/skill-metadata.json", run_skill_names)
            self.assertIn("run-web-e2e/scripts/check_web_e2e_skills.py", run_skill_names)
            self.assertIn("run-web-e2e/scripts/run_web_e2e.py", run_skill_names)
            self.assertIn("run-web-e2e/references/handoff-contract.md", run_skill_names)
            self.assertTrue((command_info.external_attr >> 16) & 0o100)

            report_config = prepare_module.yaml.safe_load(report_config_path.read_text(encoding="utf-8"))
            self.assertEqual(report_config["schema_version"], prepare_module.REPORT_CONFIG_SCHEMA)
            self.assertEqual(report_config["configuration_status"], "ready")
            self.assertEqual(report_config["units"], [{
                "model_id": "gpt-5.5",
                "model_display_name": "gpt-5.5",
                "harness_id": "codex",
                "harness_display_name": "Codex",
                "reasoning_effort": "high",
                "order": 1,
            }])
            batch_manifest = json.loads((batch_root / "batch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                batch_manifest["orchestrate_skill_archive"],
                "packages/orchestrate-web-e2e-skill-v0.1.1.zip",
            )
            self.assertEqual(
                batch_manifest["execute_skill_archive"],
                "packages/execute-web-e2e-skill-v1.8.3.zip",
            )
            self.assertEqual(
                batch_manifest["run_skill_archive"],
                "packages/run-web-e2e-skill-v1.0.1.zip",
            )
            self.assertEqual(batch_manifest["skills_manifest"], "packages/skills-manifest.json")
            skills_manifest = json.loads(skills_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(skills_manifest["schema_version"], prepare_module.SKILLS_MANIFEST_SCHEMA)
            self.assertEqual(
                [item["name"] for item in skills_manifest["skills"]],
                [
                    "score-web-e2e", "report-web-e2e", "orchestrate-web-e2e",
                    "execute-web-e2e", "run-web-e2e",
                ],
            )
            for item in skills_manifest["skills"]:
                archive_path = batch_root / item["archive"]
                self.assertEqual(item["sha256"], prepare_module.sha256_file(archive_path))
                self.assertEqual(
                    item["content_sha256"],
                    prepare_module.sha256_skill_content(REPO_ROOT / "tools/report/skills" / item["name"]),
                )
            self.assertEqual(batch_manifest["required_skills"], manifest["required_skills"])
            self.assertEqual(
                [item["content_sha256"] for item in skills_manifest["skills"]],
                [item["content_sha256"] for item in batch_manifest["required_skills"]],
            )

            contract = json.loads((score_task / "private-scoring/task_contract.json").read_text(encoding="utf-8"))
            self.assertFalse(Path(contract["source"]["task_file"]).is_absolute())
            self.assertEqual(contract["identity"]["task_id"], self.TASK_ID)
            self.assertEqual(contract["identity"]["harness"]["id"], "codex")
            self.assertNotIn("model", contract["identity"])
            self.assertEqual(contract["aesthetic_metric"]["status"], "defined")
            self.assertEqual(contract["aesthetic_metric"]["rubric_id"], "web-aesthetic-v1")
            self.assertEqual(contract["aesthetic_metric"]["rubric_version"], "1.1.0")
            self.assertEqual(contract["aesthetic_metric"]["scoring_mode"], "joint_screenshot_set")
            self.assertEqual(contract["metric_profile"], prepare_module.DETAILED_PROFILE)
            self.assertEqual(contract["schema_version"], "wildclawbench.web-e2e-task-contract/v3")

    def test_builds_artifactsbench_empty_workspace_and_lightweight_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.ARTIFACTSBENCH_TASK_ID))
            task_root = batch_root / "harnesses/codex/execution/tasks" / self.ARTIFACTSBENCH_TASK_ID
            score_root = batch_root / "harnesses/codex/score/tasks" / self.ARTIFACTSBENCH_TASK_ID
            contract = json.loads((score_root / "private-scoring/task_contract.json").read_text(encoding="utf-8"))
            manifest = json.loads((batch_root / "batch_manifest.json").read_text(encoding="utf-8"))
            report_config = prepare_module.yaml.safe_load(
                (batch_root / "web-smoke__report-config.yaml").read_text(encoding="utf-8")
            )
            self.assertTrue((task_root / "workspace/.gitkeep").is_file())
            self.assertEqual(contract["metric_profile"], prepare_module.ARTIFACTSBENCH_PROFILE)
            self.assertEqual(contract["scoring"]["input"], "raw_score")
            self.assertEqual(contract["report_dimensions"], ["overall", "difficulty"])
            self.assertEqual(contract["aesthetic_metric"]["status"], "not_applicable")
            self.assertTrue(all(not item["primary"] and not item["secondary"] for item in contract["criteria"]))
            self.assertEqual(manifest["metric_profile"], prepare_module.ARTIFACTSBENCH_PROFILE)
            self.assertEqual(report_config["metric_profile"], prepare_module.ARTIFACTSBENCH_PROFILE)

    def test_rejects_mixed_metric_profiles_in_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.task_id.append(self.ARTIFACTSBENCH_TASK_ID)
            with self.assertRaisesRegex(ValueError, "不能混合 metric profile"):
                prepare_module.prepare(args)

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

    def test_generates_one_independent_score_and_report_skill_zip_per_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.harness = ["codex", "trae"]
            batch_root = prepare_module.prepare(args)
            manifest = json.loads((batch_root / "batch_manifest.json").read_text(encoding="utf-8"))
            skill_packages = [item for item in manifest["packages"] if item["package_type"] == "score_skill"]
            report_skill_packages = [item for item in manifest["packages"] if item["package_type"] == "report_skill"]
            self.assertEqual(len(skill_packages), 1)
            self.assertEqual(len(report_skill_packages), 1)
            self.assertIsNone(skill_packages[0]["harness"])
            self.assertIsNone(report_skill_packages[0]["harness"])
            self.assertEqual(
                manifest["score_skill_archive"],
                "packages/score-web-e2e-skill-v4.4.1.zip",
            )
            self.assertEqual(
                manifest["report_skill_archive"],
                "packages/report-web-e2e-skill-v1.0.1.zip",
            )
            self.assertEqual(manifest["report_config"], "web-smoke__report-config.yaml")
            self.assertTrue(manifest["report_config_ready"])

    def test_report_config_supports_per_harness_model_and_reasoning_maps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.harness = ["astronstudio", "qwenwork"]
            args.model = "default-model"
            args.model_map = ["qwenwork=qwen3-coder"]
            args.reasoning_effort = "high"
            args.reasoning_effort_map = ["qwenwork=max"]
            batch_root = prepare_module.prepare(args)
            config = prepare_module.yaml.safe_load(
                (batch_root / "web-smoke__report-config.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [(item["model_id"], item["harness_id"], item["reasoning_effort"], item["order"]) for item in config["units"]],
                [
                    ("default-model", "astronstudio", "high", 1),
                    ("qwen3-coder", "qwenwork", "max", 2),
                ],
            )

    def test_report_config_without_model_is_explicit_incomplete_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, self.TASK_ID)
            args.model = ""
            args.reasoning_effort = ""
            batch_root = prepare_module.prepare(args)
            config = prepare_module.yaml.safe_load(
                (batch_root / "web-smoke__report-config.yaml").read_text(encoding="utf-8")
            )
            manifest = json.loads((batch_root / "batch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(config["configuration_status"], "requires_model_mapping")
            self.assertEqual(config["units"][0]["model_id"], "")
            self.assertFalse(manifest["report_config_ready"])

    def test_score_skill_only_builds_direct_archive_without_batch_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = prepare_module.build_parser().parse_args([
                "--score-skill-only",
                "--batch-id", "web-skill-only",
                "--output-dir", tmp,
                "--repo-root", str(REPO_ROOT),
            ])
            result = prepare_module.package_score_skill(args)
            package_path = Path(tmp).resolve() / "score-web-e2e-skill-v4.4.1.zip"
            self.assertEqual(result["path"], package_path)
            self.assertEqual(result["file_count"], 14)
            self.assertEqual(result["sha256"], prepare_module.sha256_file(package_path))
            self.assertEqual(result["version"], "4.4.1")
            self.assertEqual(
                result["content_sha256"],
                prepare_module.sha256_skill_content(REPO_ROOT / "tools/report/skills/score-web-e2e"),
            )
            self.assertFalse((Path(tmp) / "web-skill-only").exists())
            self.assertFalse(any(Path(tmp).glob("**/batch_manifest.json")))
            with zipfile.ZipFile(package_path) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
                self.assertEqual(len(names), 14)
                self.assertIn("score-web-e2e/scripts/serve_static.mjs", names)
                self.assertIn("score-web-e2e/scripts/screenshot_receiver.mjs", names)
                self.assertIn("score-web-e2e/references/browser-interaction-scoring.md", names)

    def test_score_skill_only_rejects_existing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                repo_root=str(REPO_ROOT),
                output_dir=tmp,
                batch_id="web-skill-only",
            )
            prepare_module.package_score_skill(args)
            with self.assertRaisesRegex(FileExistsError, "拒绝覆盖"):
                prepare_module.package_score_skill(args)

    def test_skill_archives_are_identical_across_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first_args = args_for(tmp, self.TASK_ID)
            first_args.batch_id = "web-smoke-a"
            first_root = prepare_module.prepare(first_args)
            second_args = args_for(tmp, self.TASK_ID)
            second_args.batch_id = "web-smoke-b"
            second_root = prepare_module.prepare(second_args)
            first_manifest = json.loads(
                (first_root / "packages/skills-manifest.json").read_text(encoding="utf-8")
            )
            second_manifest = json.loads(
                (second_root / "packages/skills-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [(item["name"], item["version"], item["content_sha256"], item["sha256"])
                 for item in first_manifest["skills"]],
                [(item["name"], item["version"], item["content_sha256"], item["sha256"])
                 for item in second_manifest["skills"]],
            )
            for item in first_manifest["skills"]:
                self.assertEqual(
                    (first_root / item["archive"]).read_bytes(),
                    (second_root / item["archive"]).read_bytes(),
                )

    def test_skill_installation_check_detects_current_missing_version_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            manifest_path = batch_root / "packages/skills-manifest.json"
            installed_root = Path(tmp) / "installed"
            for skill_name in (
                "score-web-e2e", "report-web-e2e", "orchestrate-web-e2e",
                "execute-web-e2e", "run-web-e2e",
            ):
                shutil.copytree(
                    REPO_ROOT / "tools/report/skills" / skill_name,
                    installed_root / skill_name,
                    ignore=shutil.ignore_patterns("__pycache__", "node_modules", "*.pyc", ".DS_Store"),
                )

            current = check_skills_module.inspect_skills(manifest_path, [installed_root])
            self.assertTrue(current["all_current"])
            self.assertEqual(current["install_required"], [])

            run_skill = installed_root / "run-web-e2e"
            shutil.rmtree(run_skill)
            missing = check_skills_module.inspect_skills(manifest_path, [installed_root])
            self.assertEqual(
                next(item["status"] for item in missing["skills"] if item["name"] == "run-web-e2e"),
                "missing",
            )

            shutil.copytree(REPO_ROOT / "tools/report/skills/run-web-e2e", run_skill)
            metadata_path = run_skill / "skill-metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["version"] = "9.9.9"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            version_mismatch = check_skills_module.inspect_skills(manifest_path, [installed_root])
            self.assertEqual(
                next(item["status"] for item in version_mismatch["skills"] if item["name"] == "run-web-e2e"),
                "version_mismatch",
            )

            shutil.copy2(REPO_ROOT / "tools/report/skills/run-web-e2e/skill-metadata.json", metadata_path)
            with (run_skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\n测试内容差异。\n")
            content_mismatch = check_skills_module.inspect_skills(manifest_path, [installed_root])
            self.assertEqual(
                next(item["status"] for item in content_mismatch["skills"] if item["name"] == "run-web-e2e"),
                "content_mismatch",
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
            materialize_execution_receipt(package_root)
            score_root = fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            task_root = score_root / "tasks" / self.TASK_ID
            self.assertTrue((task_root / "workspace/.gitkeep").is_file())
            self.assertTrue((task_root / "private-scoring/task_contract.json").is_file())
            candidate = json.loads((task_root / "private-scoring/candidate_artifact.json").read_text(encoding="utf-8"))
            self.assertEqual(candidate["schema_version"], "wildclawbench.web-e2e-candidate-artifact/v1")
            self.assertEqual(candidate["model"], {"id": "gpt-5.5", "display_name": "gpt-5.5"})
            self.assertEqual(candidate["model_selection"]["actual_model"], "gpt-5.5")
            contract = json.loads((task_root / "private-scoring/task_contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["identity"]["model"]["id"], "gpt-5.5")
            self.assertEqual(candidate["hash_algorithm"], "wildclawbench.workspace-tree-sha256/v1")
            self.assertRegex(candidate["execution_receipt"]["sha256"], r"^[a-f0-9]{64}$")
            self.assertTrue(candidate["checks"]["execution_before_copy"]["valid"])
            self.assertTrue(candidate["checks"]["score_after_copy"]["valid"])
            self.assertFalse((task_root / ".agents").exists())
            with self.assertRaisesRegex(FileExistsError, "拒绝覆盖"):
                fallback_module.prepare_scoring_workspace(package_root, scoring_package)

    def test_python_fallback_accepts_a_preconfigured_current_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester-current-model"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            materialize_execution_receipt(package_root, model_mode="current")

            score_root = fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            candidate = json.loads(
                (score_root / "tasks" / self.TASK_ID / "private-scoring/candidate_artifact.json")
                .read_text(encoding="utf-8")
            )

            self.assertEqual(candidate["model_selection"]["mode"], "current")
            self.assertIsNone(candidate["model_selection"]["requested_model"])
            self.assertEqual(candidate["model_selection"]["actual_model"], "gpt-5.5")

    def test_python_fallback_excludes_execution_runner_control_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            materialize_execution_receipt(package_root)
            control_root = package_root / "execution/tasks/.execute-web-e2e"
            control_root.mkdir()
            (control_root / "automation_state.json").write_text("{}\n", encoding="utf-8")

            prepared = fallback_module.prepare_scoring_workspace(package_root, scoring_package)

            self.assertTrue((prepared / "tasks" / self.TASK_ID / "workspace/.gitkeep").is_file())
            self.assertFalse((prepared / "tasks/.execute-web-e2e").exists())

    def test_python_fallback_rejects_execution_workspace_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            materialize_execution_receipt(package_root)
            workspace = package_root / "execution/tasks" / self.TASK_ID / "workspace"
            (workspace / "late-change.txt").write_text("drift", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "候选产物发生漂移"):
                fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            self.assertFalse(any((package_root / "score").iterdir()))

    def test_python_fallback_rejects_excluded_runtime_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            materialize_execution_receipt(package_root)
            runtime_cache = package_root / "execution/tasks" / self.TASK_ID / "workspace/.vite"
            runtime_cache.mkdir()
            (runtime_cache / "cache.json").write_text("runtime", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "禁止的运行时目录"):
                fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            self.assertFalse(any((package_root / "score").iterdir()))

    def test_candidate_freeze_pipeline_rejects_drift_and_builds_clean_submission(self) -> None:
        def prepare_package(base: Path, batch_id: str) -> tuple[Path, str]:
            args = args_for(str(base), self.ARTIFACTSBENCH_TASK_ID)
            args.batch_id = batch_id
            args.harness = ["workbuddy"]
            args.model = "xopglm52"
            batch_root = prepare_module.prepare(args)
            execution_package = batch_root / f"packages/{batch_id}__workbuddy__execution.zip"
            scoring_package = batch_root / f"packages/{batch_id}__workbuddy__scoring.zip"
            extracted = base / f"extracted-{batch_id}"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / f"{batch_id}__workbuddy"
            materialize_execution_receipt(package_root)
            fallback_module.prepare_scoring_workspace(package_root, scoring_package)
            initialized = subprocess.run(
                ["node", str(SCORING_CONTROL), "init", "--package-root", str(package_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            return package_root, self.ARTIFACTSBENCH_TASK_ID

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            drift_root, task_id = prepare_package(base, "freeze-drift")
            drift_file = drift_root / "score/tasks" / task_id / "workspace/late-change.txt"
            drift_file.write_text("drift", encoding="utf-8")
            rejected = subprocess.run(
                ["node", str(SCORING_CONTROL), "init", "--package-root", str(drift_root)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("候选产物发生漂移", rejected.stderr)
            self.assertEqual(drift_file.read_text(encoding="utf-8"), "drift")

            clean_root, task_id = prepare_package(base, "freeze-clean")
            task_root = clean_root / "score/tasks" / task_id
            contract = task_root / "private-scoring/task_contract.json"
            score_input_path = task_root / "private-scoring/score_input.json"
            initialized_score = subprocess.run(
                [
                    "node", str(INIT_SCORE), "--task-contract", str(contract),
                    "--output", str(score_input_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(initialized_score.returncode, 0, initialized_score.stderr)
            score_input = json.loads(score_input_path.read_text(encoding="utf-8"))
            score_input["browser"] = {"name": "integration-test", "viewport": "1440x900"}
            score_input["scorer"] = {"agent": "test"}
            for criterion in score_input["criteria"]:
                criterion["raw_score"] = 10
                criterion["reason"] = "临时集成测试通过"
                criterion["actions"] = ["读取冻结候选并验证页面"]
                criterion["evidence"] = [
                    {"type": "screenshot", "path": "evidence/page.png"},
                    {"type": "observation", "path": "evidence/actions.md"},
                ]
            score_input_path.write_text(
                json.dumps(score_input, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            evidence = task_root / "private-scoring/evidence"
            evidence.mkdir()
            (evidence / "page.png").write_bytes(b"png")
            (evidence / "actions.md").write_text("integration actions", encoding="utf-8")
            finalized = subprocess.run(
                [
                    "node", str(FINALIZE_SCORE), "--task-contract", str(contract),
                    "--score-input", str(score_input_path),
                    "--output", str(task_root / "private-scoring/task_score.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            submitted = subprocess.run(
                ["node", str(BUILD_SUBMISSION), "--package-root", str(clean_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(submitted.returncode, 0, submitted.stderr)
            submission = json.loads((clean_root / "submission.json").read_text(encoding="utf-8"))
            self.assertTrue(submission["candidate_artifacts"][0]["valid"])
            self.assertEqual(submission["candidate_artifacts"][0]["execution_sha256"], submission["candidate_artifacts"][0]["score_sha256"])

    def test_python_fallback_accepts_system_metadata_and_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_root = prepare_module.prepare(args_for(tmp, self.TASK_ID))
            execution_package = batch_root / "packages/web-smoke__codex__execution.zip"
            scoring_package = batch_root / "packages/web-smoke__codex__scoring.zip"
            extracted = Path(tmp) / "tester"
            with zipfile.ZipFile(execution_package) as archive:
                archive.extractall(extracted)
            package_root = extracted / "web-smoke__codex"
            materialize_execution_receipt(package_root)
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
            materialize_execution_receipt(package_root)
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
