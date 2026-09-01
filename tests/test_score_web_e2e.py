from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/init_score.mjs"
FINALIZE = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/finalize_score.mjs"
SUBMISSION = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/build_submission.mjs"
STATIC_SERVER = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/serve_static.mjs"

AESTHETIC_DIMENSIONS = [
    ("render_integrity", "桌面和窄屏均完整渲染"),
    ("layout_hierarchy", "首屏焦点与间距层级已按检查点判断"),
    ("color_typography", "配色和字号层级已按检查点判断"),
    ("component_state", "组件和状态已按检查点判断"),
    ("responsive", "窄屏表现已按检查点判断"),
    ("tone_fit", "业务调性已按检查点判断"),
]
AESTHETIC_CHECKLIST_IDS = [
    *(f"v-{index:02d}" for index in range(1, 23)),
    *(f"p-{index:02d}" for index in range(1, 11)),
]


def aesthetic_input() -> dict:
    return {
        "status": "completed",
        "error": None,
        "screenshots": [
            {
                "label": "desktop-main", "path": "evidence/aesthetic-desktop-main.png",
                "viewport": {"width": 1440, "height": 900}, "state": "首页", "description": "桌面首屏",
            },
            {
                "label": "desktop-state", "path": "evidence/aesthetic-desktop-state.png",
                "viewport": {"width": 1440, "height": 900}, "state": "交互后", "description": "桌面交互状态",
            },
            {
                "label": "mobile-main", "path": "evidence/aesthetic-mobile-main.png",
                "viewport": {"width": 390, "height": 844}, "state": "窄屏首页", "description": "移动端首屏",
            },
        ],
        "dimensions": [
            {"id": dimension_id, "score": None, "rationale": rationale, "evidence": ["mobile-main" if dimension_id == "responsive" else "desktop-main"]}
            for dimension_id, rationale in AESTHETIC_DIMENSIONS
        ],
        "checklist": [
            {
                "id": checklist_id,
                "status": "MET",
                "rationale": "截图中可见对应视觉表现",
                "evidence": ["mobile-main" if checklist_id in {"v-17", "v-18", "v-19", "p-07", "p-08"} else "desktop-main"],
            }
            for checklist_id in AESTHETIC_CHECKLIST_IDS
        ],
        "strengths": ["整体视觉语言一致"],
        "defects": [{"severity": "minor", "description": "窄屏信息略密", "where": "mobile-main"}],
    }


def fixtures():
    manifest = {
        "batch_id": "batch-1",
        "source_revision": "abc",
        "task_id": "task-1",
        "model": {"id": "gpt-5.5", "display_name": "GPT-5.5"},
        "harness": {"id": "codex", "display_name": "Codex"},
        "source": {"task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"},
    }
    contract = {
        "schema_version": "wildclawbench.web-e2e-task-contract/v2",
        "identity": {
            "batch_id": "batch-1",
            "source_revision": "abc",
            "task_id": "task-1",
            "task_name": "站点任务",
            "difficulty": "L1",
            "harness": {"id": "codex", "display_name": "Codex"},
        },
        "criteria": [
            {"index": 1, "key": "content", "name": "内容", "primary": "content_structure", "secondary": "basic_content", "weight": 0.4},
            {"index": 2, "key": "action", "name": "交互", "primary": "interaction_function", "secondary": "operation_feedback", "weight": 0.6},
        ],
        "aesthetic_metric": {"max_score": 100, "included_in_total": False, "status": "pending_definition"},
        "source": {"task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"},
    }
    execution = {
        "batch_id": "batch-1",
        "task_id": "task-1",
        "model": {"id": "gpt-5.5", "display_name": "GPT-5.5"},
        "harness": {"id": "codex", "display_name": "Codex"},
        "execution": {"status": "completed", "duration_seconds": 30},
        "usage": {"total_tokens": 100, "request_count": 2, "cost_usd": 0.1},
        "tools": {"call_count": 4, "format_accuracy": 1.0},
        "artifacts": {},
    }
    score_input = {
        "evaluation_status": "completed",
        "evaluation_error": None,
        "site_url": "http://127.0.0.1:4173",
        "browser": {"name": "browser", "viewport": "1440x900"},
        "criteria": [
            {"key": "content", "score": 1.0, "reason": "满足", "actions": ["打开首页"], "evidence": [{"type": "screenshot", "path": "evidence/a.png"}]},
            {"key": "action", "score": 0.5, "reason": "部分满足", "actions": ["点击按钮"], "evidence": [{"type": "observation", "path": "evidence/actions.md"}]},
        ],
        "aesthetic": aesthetic_input(),
        "scorer": {"agent": "Codex"},
    }
    return manifest, contract, execution, score_input


def artifactsbench_fixtures():
    manifest, _, execution, _ = fixtures()
    manifest["metric_profile"] = "artifactsbench-web-v1"
    contract = {
        "schema_version": "wildclawbench.web-e2e-task-contract/v3",
        "metric_profile": "artifactsbench-web-v1",
        "scoring": {
            "input": "raw_score",
            "raw_scale": {"minimum": 0, "maximum": 10, "step": 1},
            "normalized_scale": {"minimum": 0, "maximum": 1},
            "normalization": "raw_score / 10",
            "aggregate": "weighted_mean",
        },
        "identity": {
            "batch_id": "batch-1",
            "source_revision": "abc",
            "task_id": "task-1",
            "task_name": "ArtifactsBench 站点任务",
            "difficulty": "L2",
            "harness": {"id": "codex", "display_name": "Codex"},
        },
        "criteria": [
            {
                "index": 1, "key": "content", "name": "内容", "primary": "", "secondary": "", "weight": 0.4,
                "evidence_policy": {"required_types": []},
            },
            {
                "index": 2, "key": "visual", "name": "视觉", "primary": "", "secondary": "", "weight": 0.6,
                "evidence_policy": {"required_types": ["screenshot"]},
            },
        ],
        "aesthetic_metric": {"included_in_total": False, "status": "not_applicable"},
        "source": {"task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"},
    }
    score_input = {
        "metric_profile": "artifactsbench-web-v1",
        "evaluation_status": "completed",
        "evaluation_error": None,
        "site_url": "http://127.0.0.1:4173",
        "browser": {"name": "browser", "viewport": "1440x900"},
        "criteria": [
            {
                "key": "content", "raw_score": 7, "reason": "达到七分锚点", "actions": ["检查内容"],
                "evidence": [{"type": "observation", "path": "evidence/actions.md"}],
            },
            {
                "key": "visual", "raw_score": 9, "reason": "达到九分锚点", "actions": ["检查页面"],
                "evidence": [{"type": "screenshot", "path": "evidence/a.png"}],
            },
        ],
        "scorer": {"agent": "Codex"},
    }
    return manifest, contract, execution, score_input


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def run_finalize(
    root: Path,
    values=None,
    *,
    include_manifest: bool = False,
    include_execution: bool = False,
) -> subprocess.CompletedProcess:
    manifest, contract, execution, score_input = values or fixtures()
    write_json(root / "private-scoring/task_contract.json", contract)
    write_json(root / "private-scoring/score_input.json", score_input)
    command = [
        "node", str(FINALIZE),
        "--task-contract", str(root / "private-scoring/task_contract.json"),
        "--score-input", str(root / "private-scoring/score_input.json"),
        "--output", str(root / "private-scoring/task_score.json"),
    ]
    if include_manifest:
        write_json(root / "task_manifest.json", manifest)
        command.extend(["--manifest", str(root / "task_manifest.json")])
    if include_execution:
        write_json(root / "execution_record.json", execution)
        command.extend(["--execution-record", str(root / "execution_record.json")])
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
    )


class FinalizeWebE2EScoreTest(unittest.TestCase):
    def test_init_cli_materializes_all_contract_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, contract, _, _ = fixtures()
            write_json(root / "contract.json", contract)
            result = subprocess.run(
                ["node", str(INIT), "--task-contract", str(root / "contract.json"), "--output", str(root / "score_input.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            score_input = json.loads((root / "score_input.json").read_text(encoding="utf-8"))
        self.assertEqual([item["key"] for item in score_input["criteria"]], ["content", "action"])
        self.assertEqual([item["score"] for item in score_input["criteria"]], [None, None])
        self.assertEqual(len(score_input["aesthetic"]["dimensions"]), 6)
        self.assertEqual(len(score_input["aesthetic"]["checklist"]), 32)

    def test_calculates_weighted_total_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["total_score"], 70)
        self.assertEqual(score["metrics"]["primary_dimensions"]["content_structure"], 100)
        self.assertEqual(score["metrics"]["primary_dimensions"]["interaction_function"], 50)
        self.assertFalse(score["metrics"]["aesthetic"]["included_in_total"])
        self.assertEqual(score["metrics"]["aesthetic"]["score"], 100)
        self.assertEqual(score["provenance"]["skill_version"], "4.0.0")
        self.assertEqual(score["metrics"]["aesthetic"]["primary_dimensions"]["layout_hierarchy"], 100)
        self.assertEqual(score["metrics"]["aesthetic"]["secondary_dimensions"]["v-01"], "MET")
        self.assertEqual(score["metrics"]["aesthetic"]["secondary_dimension_scores"]["v-01"], 100)
        self.assertEqual(len(score["evaluation"]["aesthetic"]["screenshots"]), 3)
        self.assertEqual(score["execution"]["status"], "not_recorded")
        self.assertIsNone(score["usage"]["total_tokens"])

    def test_artifactsbench_init_uses_raw_scores_without_aesthetic_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, contract, _, _ = artifactsbench_fixtures()
            write_json(root / "contract.json", contract)
            result = subprocess.run(
                ["node", str(INIT), "--task-contract", str(root / "contract.json"), "--output", str(root / "score_input.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            score_input = json.loads((root / "score_input.json").read_text(encoding="utf-8"))
        self.assertEqual(score_input["metric_profile"], "artifactsbench-web-v1")
        self.assertEqual([item["raw_score"] for item in score_input["criteria"]], [None, None])
        self.assertTrue(all("score" not in item for item in score_input["criteria"]))
        self.assertNotIn("aesthetic", score_input)

    def test_artifactsbench_preserves_raw_score_and_derives_normalized_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, artifactsbench_fixtures())
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metric_profile"], "artifactsbench-web-v1")
        self.assertEqual(score["metrics"]["total_score"], 82)
        self.assertEqual(score["evaluation"]["criteria"][0]["raw_score"], 7)
        self.assertEqual(score["evaluation"]["criteria"][0]["score"], 0.7)
        self.assertEqual(score["metrics"]["primary_dimensions"], {})
        self.assertEqual(score["metrics"]["secondary_dimensions"], {})
        self.assertEqual(score["metrics"]["aesthetic"]["status"], "not_applicable")

    def test_artifactsbench_rejects_fractional_raw_score(self) -> None:
        values = list(artifactsbench_fixtures())
        values[3]["criteria"][0]["raw_score"] = 7.5
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须是 0..10 整数", result.stderr)

    def test_artifactsbench_requires_declared_screenshot_evidence(self) -> None:
        values = list(artifactsbench_fixtures())
        values[3]["criteria"][1]["evidence"] = [{"type": "observation", "path": "evidence/actions.md"}]
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必须包含 screenshot 证据", result.stderr)

    def test_legacy_manifest_and_execution_record_arguments_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, include_manifest=True, include_execution=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["execution"]["status"], "completed")
        self.assertEqual(score["usage"]["total_tokens"], 100)

    def test_rejects_legacy_scalar_aesthetic_score(self) -> None:
        values = list(fixtures())
        values[3].pop("aesthetic")
        values[3]["aesthetic_score"] = 88
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不再接受单一 aesthetic_score", result.stderr)

    def test_derives_dimension_and_total_from_guardrails_and_bonus_items(self) -> None:
        values = list(fixtures())
        status_by_id = {
            "v-01": "MET", "v-02": "PARTIAL", "v-03": "UNMET", "v-04": "MET",
            "p-01": "PARTIAL", "p-02": "UNMET",
        }
        for item in values[3]["aesthetic"]["checklist"]:
            if item["id"] in status_by_id:
                item["status"] = status_by_id[item["id"]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["aesthetic"]["primary_dimensions"]["render_integrity"], 62.5)
        self.assertEqual(score["metrics"]["aesthetic"]["primary_dimensions"]["layout_hierarchy"], 75)
        self.assertEqual(score["metrics"]["aesthetic"]["score"], 88.13)
        layout = next(item for item in score["evaluation"]["aesthetic"]["dimensions"] if item["id"] == "layout_hierarchy")
        self.assertEqual(layout["score_sum"], 450)
        self.assertEqual(layout["max_score"], 600)
        self.assertEqual(layout["applicable_checklist_count"], 6)

    def test_maps_aesthetic_checklist_statuses_to_scores(self) -> None:
        values = list(fixtures())
        status_by_id = {"v-01": "PARTIAL", "v-02": "UNMET", "v-03": "NA"}
        for item in values[3]["aesthetic"]["checklist"]:
            if item["id"] in status_by_id:
                item["status"] = status_by_id[item["id"]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        scores = score["metrics"]["aesthetic"]["secondary_dimension_scores"]
        self.assertEqual(scores["v-01"], 50)
        self.assertEqual(scores["v-02"], 0)
        self.assertIsNone(scores["v-03"])
        self.assertEqual(score["metrics"]["aesthetic"]["primary_dimensions"]["render_integrity"], 50)
        checklist = {item["id"]: item for item in score["evaluation"]["aesthetic"]["checklist"]}
        self.assertEqual(checklist["v-01"]["score"], 50)

    def test_rejects_dimension_when_all_checkpoints_are_na(self) -> None:
        values = list(fixtures())
        for item in values[3]["aesthetic"]["checklist"]:
            if item["id"] in {"v-01", "v-02", "v-03", "v-04"}:
                item["status"] = "NA"
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不能全部为 NA", result.stderr)

    def test_rejects_manually_entered_aesthetic_dimension_score(self) -> None:
        values = list(fixtures())
        values[3]["aesthetic"]["dimensions"][0]["score"] = 88
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("自动计算", result.stderr)

    def test_error_status_forces_total_and_dimensions_to_zero(self) -> None:
        values = list(fixtures())
        values[2]["execution"]["status"] = "timeout"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values, include_execution=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["total_score"], 0)
        self.assertEqual(set(score["metrics"]["primary_dimensions"].values()), {0})

    def test_evaluation_error_allows_unjudged_criteria_and_forces_zero(self) -> None:
        values = list(fixtures())
        values[3]["evaluation_status"] = "evaluation_error"
        values[3]["evaluation_error"] = "浏览器工具不可用"
        for criterion in values[3]["criteria"]:
            criterion.update({"score": None, "reason": "", "actions": [], "evidence": []})
        values[3]["aesthetic"]["screenshots"] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["total_score"], 0)
        self.assertEqual([item["score"] for item in score["evaluation"]["criteria"]], [None, None])
        self.assertEqual(score["metrics"]["aesthetic"]["status"], "evaluation_error")
        self.assertIsNone(score["metrics"]["aesthetic"]["score"])

    def test_function_evaluation_error_keeps_completed_aesthetic_result(self) -> None:
        values = list(fixtures())
        values[3]["evaluation_status"] = "evaluation_error"
        values[3]["evaluation_error"] = "功能检查异常"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["total_score"], 0)
        self.assertEqual(score["metrics"]["aesthetic"]["status"], "completed")
        self.assertEqual(score["metrics"]["aesthetic"]["score"], 100)


class BuildSubmissionTest(unittest.TestCase):
    @staticmethod
    def materialize_evidence(task_root: Path) -> None:
        evidence = task_root / "private-scoring/evidence"
        evidence.mkdir(exist_ok=True)
        (evidence / "a.png").write_bytes(b"png")
        (evidence / "actions.md").write_text("actions", encoding="utf-8")
        for name in ("aesthetic-desktop-main.png", "aesthetic-desktop-state.png", "aesthetic-mobile-main.png"):
            (evidence / name).write_bytes(b"png")

    def test_allows_report_config_to_supply_missing_model_id(self) -> None:
        values = list(fixtures())
        values[0]["model"] = {"id": "", "display_name": ""}
        values[2]["model"] = {"id": "", "display_name": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.materialize_evidence(task_root)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            result = subprocess.run(
                ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            submission = json.loads((root / "submission.json").read_text(encoding="utf-8"))
        self.assertIsNone(submission["unit"]["model_id"])
        self.assertEqual(submission["unit"]["harness_id"], "codex")

    def test_artifactsbench_submission_records_metric_profile(self) -> None:
        values = artifactsbench_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = task_root / "private-scoring/evidence"
            evidence.mkdir()
            (evidence / "a.png").write_bytes(b"png")
            (evidence / "actions.md").write_text("actions", encoding="utf-8")
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "metric_profile": "artifactsbench-web-v1",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            result = subprocess.run(
                ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            submission = json.loads((root / "submission.json").read_text(encoding="utf-8"))
        self.assertEqual(submission["metric_profile"], "artifactsbench-web-v1")

    def test_rejects_secrets_and_builds_submission_after_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            finalize_result = run_finalize(task_root)
            self.assertEqual(finalize_result.returncode, 0, finalize_result.stderr)
            self.materialize_evidence(task_root)
            (task_root / "workspace").mkdir()
            (task_root / "workspace/index.html").write_text("ok", encoding="utf-8")
            (task_root / "workspace/.env").write_text("SECRET=x", encoding="utf-8")
            root_manifest = {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            }
            write_json(root / "manifest.json", root_manifest)
            command = ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")]
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("敏感文件", rejected.stderr)
            (task_root / "workspace/.env").unlink()
            (root / "execution/tasks/task-1/workspace/node_modules").mkdir(parents=True)
            rejected_modules = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected_modules.returncode, 0)
            self.assertIn("node_modules", rejected_modules.stderr)
            (root / "execution/tasks/task-1/workspace/node_modules").rmdir()
            accepted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            submission = json.loads((root / "submission.json").read_text(encoding="utf-8"))
        self.assertEqual(submission["unit"]["harness_id"], "codex")
        self.assertEqual(submission["task_ids"], ["task-1"])


class StaticSiteServerTest(unittest.TestCase):
    def test_serves_plain_html_without_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<!doctype html><script src="/app.js"></script><main>静态站点</main>',
                encoding="utf-8",
            )
            (root / "app.js").write_text("document.body.dataset.ready = 'yes';", encoding="utf-8")
            process = subprocess.Popen(
                [
                    "node", str(STATIC_SERVER),
                    "--root", str(root),
                    "--host", "127.0.0.1",
                    "--port", "0",
                    "--spa-fallback",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready = process.stdout.readline().strip()
                self.assertTrue(ready.startswith("PASS: http://127.0.0.1:"), ready)
                site_url = ready.removeprefix("PASS: ").split(" ", 1)[0]
                with urlopen(site_url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("静态站点", response.read().decode("utf-8"))
                with urlopen(f"{site_url}app.js", timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(), "text/javascript")
                with urlopen(f"{site_url}nested/route", timeout=5) as response:
                    self.assertIn("静态站点", response.read().decode("utf-8"))
            finally:
                process.terminate()
                process.communicate(timeout=5)

    def test_rejects_non_loopback_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("ok", encoding="utf-8")
            result = subprocess.run(
                [
                    "node", str(STATIC_SERVER),
                    "--root", str(root),
                    "--host", "0.0.0.0",
                    "--port", "4173",
                ],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("只允许监听 127.0.0.1", result.stderr)


if __name__ == "__main__":
    unittest.main()
