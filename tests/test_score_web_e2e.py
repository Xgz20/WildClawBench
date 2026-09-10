from __future__ import annotations

import base64
import json
import hashlib
import os
import shutil
import socket
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
MANAGED_RUNTIME = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/managed_runtime.mjs"

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
    def test_managed_score_records_frozen_candidate_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp)
            task_root = package_root / "score/tasks/task-1"
            (task_root / "workspace").mkdir(parents=True)
            (task_root / "workspace/index.html").write_text("frozen", encoding="utf-8")
            frozen = BuildSubmissionTest.materialize_candidate_integrity(package_root)
            (task_root / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((task_root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
            self.assertEqual(score["provenance"]["candidate_workspace_sha256"], frozen)
            (task_root / "workspace/index.html").write_text("drift", encoding="utf-8")
            result = run_finalize(task_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("候选产物发生漂移", result.stderr)

    def test_managed_scoring_helpers_cannot_write_into_candidate_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp)
            task_root = package_root / "score/tasks/task-1"
            (task_root / "workspace").mkdir(parents=True)
            (task_root / "workspace/index.html").write_text("frozen", encoding="utf-8")
            BuildSubmissionTest.materialize_candidate_integrity(package_root)
            (task_root / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            _, contract, _, score_input = fixtures()
            write_json(task_root / "private-scoring/task_contract.json", contract)
            write_json(task_root / "private-scoring/score_input.json", score_input)

            init_result = subprocess.run(
                [
                    "node", str(INIT),
                    "--task-contract", str(task_root / "private-scoring/task_contract.json"),
                    "--output", str(task_root / "workspace/score_input.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(init_result.returncode, 0)
            self.assertIn("只能写入 private-scoring/score_input.json", init_result.stderr)

            finalize_result = subprocess.run(
                [
                    "node", str(FINALIZE),
                    "--task-contract", str(task_root / "private-scoring/task_contract.json"),
                    "--score-input", str(task_root / "private-scoring/score_input.json"),
                    "--output", str(task_root / "workspace/task_score.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(finalize_result.returncode, 0)
            self.assertIn("只能写入 private-scoring/task_score.json", finalize_result.stderr)
            self.assertFalse((task_root / "workspace/score_input.json").exists())
            self.assertFalse((task_root / "workspace/task_score.json").exists())

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
        self.assertEqual(score["provenance"]["skill_version"], "4.5.0")
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

    @staticmethod
    def materialize_candidate_integrity(
        root: Path,
        task_id: str = "task-1",
        actual_model: str = "gpt-5.5",
        model_display_name: str = "GPT-5.5",
        model_mode: str = "explicit",
        patch_task_score_model: bool = True,
    ) -> str:
        task_root = root / "score/tasks" / task_id
        score_workspace = task_root / "workspace"
        score_workspace.mkdir(parents=True, exist_ok=True)
        if not any(score_workspace.iterdir()):
            (score_workspace / "index.html").write_text("ok", encoding="utf-8")
        execution_workspace = root / "execution/tasks" / task_id / "workspace"
        execution_workspace.parent.mkdir(parents=True, exist_ok=True)
        if execution_workspace.exists():
            shutil.rmtree(execution_workspace)
        shutil.copytree(score_workspace, execution_workspace)

        entries = []
        for filename in sorted(path for path in score_workspace.rglob("*") if path.is_file()):
            relative = filename.relative_to(score_workspace).as_posix()
            file_hash = hashlib.sha256(filename.read_bytes()).hexdigest()
            entries.append((relative, "file", file_hash))
        digest = hashlib.sha256()
        for relative, kind, file_hash in entries:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(kind.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("utf-8"))
            digest.update(b"\n")
        frozen = digest.hexdigest()

        write_json(task_root / "private-scoring/candidate_artifact.json", {
            "schema_version": "wildclawbench.web-e2e-candidate-artifact/v1",
            "hash_algorithm": "wildclawbench.workspace-tree-sha256/v1",
            "batch_id": "batch-1",
            "task_id": task_id,
            "harness_id": "codex",
            "model": {"id": actual_model, "display_name": model_display_name},
            "model_selection": {
                "mode": model_mode,
                "requested_model": actual_model if model_mode == "explicit" else None,
                "actual_model": actual_model,
                "method": "test-readback",
            },
            "expected_sha256": frozen,
            "attempt_id": f"attempt-{task_id}",
            "runtime_directory_policy": {
                "schema_version": "wildclawbench.web-e2e-runtime-directory-policy/v1",
                "ignored_directories": [".cache", ".vite", "node_modules"],
                "forbidden_directories": [".git"],
                "scoring_copy": "exclude-ignored-directories",
                "return_archive": "exclude-ignored-directories",
            },
        })
        write_json(root / "execution-receipt.json", {
            "schema_version": "wildclawbench.web-e2e-execution-receipt/v1",
            "batch_id": "batch-1",
            "harness": {"id": "codex"},
            "model": {"id": actual_model, "display_name": model_display_name},
            "runtime_directory_policy": {
                "schema_version": "wildclawbench.web-e2e-runtime-directory-policy/v1",
                "ignored_directories": [".cache", ".vite", "node_modules"],
                "forbidden_directories": [".git"],
                "scoring_copy": "exclude-ignored-directories",
                "return_archive": "exclude-ignored-directories",
            },
            "tasks": [{
                "task_id": task_id,
                "attempt_id": f"attempt-{task_id}",
                "model_selection": {
                    "mode": model_mode,
                    "requested_model": actual_model if model_mode == "explicit" else None,
                    "actual_model": actual_model,
                    "method": "test-readback",
                },
                "workspace": {"final_sha256": frozen},
            }],
            "integrity": {"valid": True},
        })
        receipt_sha256 = hashlib.sha256((root / "execution-receipt.json").read_bytes()).hexdigest()
        candidate = json.loads(
            (task_root / "private-scoring/candidate_artifact.json").read_text(encoding="utf-8")
        )
        candidate["execution_receipt"] = {"sha256": receipt_sha256}
        write_json(task_root / "private-scoring/candidate_artifact.json", candidate)
        score_path = task_root / "private-scoring/task_score.json"
        if score_path.is_file():
            score = json.loads(score_path.read_text(encoding="utf-8"))
            score["provenance"]["candidate_workspace_sha256"] = frozen
            if patch_task_score_model:
                score["identity"]["model"] = {
                    "id": actual_model,
                    "display_name": model_display_name,
                }
            write_json(score_path, score)
        return frozen

    def test_submission_rejects_task_score_missing_execution_readback_model(self) -> None:
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
            self.materialize_candidate_integrity(root, patch_task_score_model=False)
            result = subprocess.run(
                ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("task_score 模型与执行回读不一致", result.stderr)

    def test_managed_finalize_uses_frozen_execution_readback_model(self) -> None:
        values = list(fixtures())
        values[0]["model"] = {"id": "", "display_name": ""}
        values[1]["identity"].pop("model", None)
        values[2]["model"] = {"id": "", "display_name": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            (task_root / "workspace").mkdir(parents=True)
            (task_root / "workspace/index.html").write_text("frozen", encoding="utf-8")
            self.materialize_candidate_integrity(
                root,
                actual_model="xopglm52",
                model_display_name="xopglm52",
            )
            (task_root / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            result = run_finalize(task_root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((task_root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["identity"]["model"], {"id": "xopglm52", "display_name": "xopglm52"})

    def test_artifactsbench_submission_accepts_current_model_and_records_metric_profile(self) -> None:
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
            self.materialize_candidate_integrity(root, model_mode="current")
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
            root_manifest = {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            }
            write_json(root / "manifest.json", root_manifest)
            self.materialize_candidate_integrity(root)
            command = ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")]
            (task_root / "workspace/.env").write_text("SECRET=x", encoding="utf-8")
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("候选产物发生漂移", rejected.stderr)
            (task_root / "workspace/.env").unlink()
            (root / ".env").write_text("SECRET=x", encoding="utf-8")
            rejected_secret = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected_secret.returncode, 0)
            self.assertIn("敏感文件", rejected_secret.stderr)
            (root / ".env").unlink()
            modules = root / "execution/tasks/task-1/workspace/node_modules/pkg"
            modules.mkdir(parents=True)
            (modules / "index.js").write_text("runtime", encoding="utf-8")
            cache = root / "execution/tasks/task-1/workspace/.cache"
            cache.mkdir()
            (cache / "state.json").write_text("{}", encoding="utf-8")
            (task_root / "workspace/node_modules").mkdir()
            rejected_score_modules = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected_score_modules.returncode, 0)
            self.assertIn("未声明为可忽略", rejected_score_modules.stderr)
            (task_root / "workspace/node_modules").rmdir()
            (root / "execution/tasks/task-1/workspace/.git").mkdir()
            rejected_git = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected_git.returncode, 0)
            self.assertIn("禁止目录", rejected_git.stderr)
            (root / "execution/tasks/task-1/workspace/.git").rmdir()
            accepted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            submission = json.loads((root / "submission.json").read_text(encoding="utf-8"))
            self.assertEqual(
                submission["candidate_artifacts"][0]["ignored_runtime_directories"],
                [".cache", "node_modules"],
            )
        self.assertEqual(submission["unit"]["harness_id"], "codex")
        self.assertEqual(submission["task_ids"], ["task-1"])

    def test_rejects_execution_workspace_drift_before_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.materialize_evidence(task_root)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            self.materialize_candidate_integrity(root)
            (root / "execution/tasks/task-1/workspace/index.html").write_text("late drift", encoding="utf-8")
            result = subprocess.run(
                ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("候选产物发生漂移", result.stderr)

    def test_submission_output_cannot_target_candidate_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.materialize_evidence(task_root)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            self.materialize_candidate_integrity(root)
            forbidden_output = task_root / "workspace/submission.json"
            result = subprocess.run(
                ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(forbidden_output)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("只能写入 Harness 根目录", result.stderr)
            self.assertFalse(forbidden_output.exists())

    def test_submission_rejects_non_terminal_screenshot_receiver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.materialize_evidence(task_root)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            frozen = self.materialize_candidate_integrity(root)
            receiver_state = {
                "schema_version": "wildclawbench.web-e2e-screenshot-receiver/v1",
                "task_id": "task-1",
                "candidate_sha256": frozen,
                "receiver_id": "00000000-0000-4000-8000-000000000000",
                "status": "RUNNING",
                "pid": 999999,
                "pgid": 999999,
                "process_started_at_text": "not-running",
                "cwd": ".",
                "filename": "unused.png",
                "format": "png",
                "content_type": "image/png",
                "token_sha256": "0" * 64,
                "upload_url": "http://127.0.0.1:12345/screenshot/temporary-token",
            }
            state_file = task_root / "private-scoring/screenshot-receiver-state.json"
            write_json(state_file, receiver_state)
            command = ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")]
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("截图接收器未进入可信终态", rejected.stderr)

            receiver_state["status"] = "STOPPED"
            write_json(state_file, receiver_state)
            leaked_url = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(leaked_url.returncode, 0)
            self.assertIn("截图接收器未进入可信终态", leaked_url.stderr)

            receiver_state["upload_url"] = None
            write_json(state_file, receiver_state)
            accepted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_submission_revalidates_completed_receiver_output(self) -> None:
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.materialize_evidence(task_root)
            screenshot = task_root / "private-scoring/evidence/a.png"
            screenshot.write_bytes(png)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            frozen = self.materialize_candidate_integrity(root)
            write_json(task_root / "private-scoring/screenshot-receiver-state.json", {
                "schema_version": "wildclawbench.web-e2e-screenshot-receiver/v1",
                "task_id": "task-1",
                "candidate_sha256": frozen,
                "receiver_id": "00000000-0000-4000-8000-000000000000",
                "status": "COMPLETED",
                "pid": 999999,
                "pgid": 999999,
                "process_started_at_text": "not-running",
                "cwd": ".",
                "filename": "a.png",
                "format": "png",
                "content_type": "image/png",
                "token_sha256": "0" * 64,
                "upload_url": None,
                "output": {
                    "path": "private-scoring/evidence/a.png",
                    "bytes": len(png),
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "format": "png",
                    "content_type": "image/png",
                },
            })
            command = ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")]
            accepted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            (root / "submission.json").unlink()

            screenshot.write_bytes(png + b"tampered")
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("截图接收器证据文件校验失败", rejected.stderr)


class ManagedRuntimeTest(unittest.TestCase):
    @staticmethod
    def prepare_port_conflict_task(root: Path, source: str = "server.listen(9099);\n") -> tuple[Path, Path]:
        task_root = root / "score/tasks/task-1"
        workspace = task_root / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "server.js").write_text(source, encoding="utf-8")
        BuildSubmissionTest.materialize_candidate_integrity(root)
        prepared = subprocess.run(
            ["node", str(MANAGED_RUNTIME), "prepare", "--task-root", str(task_root)],
            capture_output=True,
            text=True,
        )
        if prepared.returncode != 0:
            raise AssertionError(prepared.stderr)
        logs = task_root / "private-scoring/runtime-logs"
        logs.mkdir()
        (logs / "site.stderr.log").write_text(
            "Error: listen EADDRINUSE: address already in use 127.0.0.1:9099\n",
            encoding="utf-8",
        )
        state_file = task_root / "private-scoring/runtime-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["service"] = {
            "status": "START_FAILED_STOPPED",
            "command": ["node", "server.js"],
            "expected_url": "http://127.0.0.1:9099/",
            "stderr": "private-scoring/runtime-logs/site.stderr.log",
        }
        write_json(state_file, state)
        return task_root, workspace

    @staticmethod
    def run_port_override(task_root: Path, filename: str = "server.js", from_port: str = "9099", to_port: str = "9100"):
        return subprocess.run(
            [
                "node", str(MANAGED_RUNTIME), "port-override",
                "--task-root", str(task_root),
                "--file", filename,
                "--from-port", from_port,
                "--to-port", to_port,
                "--evidence", "private-scoring/runtime-logs/site.stderr.log",
            ],
            capture_output=True,
            text=True,
        )

    def test_runtime_copy_can_change_without_modifying_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            workspace = task_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "index.html").write_text("frozen", encoding="utf-8")
            BuildSubmissionTest.materialize_candidate_integrity(root)
            before = (workspace / "index.html").read_bytes()
            prepared = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "prepare", "--task-root", str(task_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            runtime_file = task_root / "private-scoring/runtime-workspace/index.html"
            runtime_file.write_text("runtime build output", encoding="utf-8")
            self.assertEqual((workspace / "index.html").read_bytes(), before)
            cleaned = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "clean", "--task-root", str(task_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            self.assertFalse((task_root / "private-scoring/runtime-workspace").exists())
            self.assertEqual((workspace / "index.html").read_bytes(), before)

    def test_port_override_requires_managed_conflict_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root, _ = self.prepare_port_conflict_task(root)
            state_file = task_root / "private-scoring/runtime-state.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["service"]["status"] = "STOPPED"
            write_json(state_file, state)
            rejected_state = self.run_port_override(task_root)
            self.assertNotEqual(rejected_state.returncode, 0)
            self.assertIn("只有受管启动因端口冲突失败", rejected_state.stderr)

            state["service"]["status"] = "START_FAILED_STOPPED"
            write_json(state_file, state)
            (task_root / "private-scoring/runtime-logs/site.stderr.log").write_text(
                "generic startup failure on 9099\n",
                encoding="utf-8",
            )
            rejected_log = self.run_port_override(task_root)
            self.assertNotEqual(rejected_log.returncode, 0)
            self.assertIn("不能证明端口 9099 冲突", rejected_log.stderr)
            self.assertEqual(
                (task_root / "private-scoring/runtime-workspace/server.js").read_text(encoding="utf-8"),
                "server.listen(9099);\n",
            )

    def test_port_override_changes_only_runtime_copy_and_records_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root, workspace = self.prepare_port_conflict_task(root)
            candidate_before = (workspace / "server.js").read_bytes()
            rejected_candidate = self.run_port_override(task_root, "../workspace/server.js")
            self.assertNotEqual(rejected_candidate.returncode, 0)
            self.assertIn("runtime-workspace 内的相对路径", rejected_candidate.stderr)

            accepted = self.run_port_override(task_root)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual((workspace / "server.js").read_bytes(), candidate_before)
            self.assertEqual(
                (task_root / "private-scoring/runtime-workspace/server.js").read_text(encoding="utf-8"),
                "server.listen(9100);\n",
            )
            audit = json.loads(
                (task_root / "private-scoring/runtime-port-override.json").read_text(encoding="utf-8")
            )
            self.assertEqual(audit["schema_version"], "wildclawbench.web-e2e-runtime-port-override/v1")
            self.assertEqual(len(audit["overrides"]), 1)
            event = audit["overrides"][0]
            self.assertEqual(event["patch"]["file"], "server.js")
            self.assertEqual(event["patch"]["from_port"], 9099)
            self.assertEqual(event["patch"]["to_port"], 9100)
            self.assertNotEqual(event["patch"]["before_sha256"], event["patch"]["after_sha256"])
            self.assertTrue((task_root / event["conflict"]["evidence_path"]).is_file())

    def test_port_override_rejects_multiple_matches_and_non_numeric_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root, _ = self.prepare_port_conflict_task(root, "const port = 9099; server.listen(9099);\n")
            rejected_matches = self.run_port_override(task_root)
            self.assertNotEqual(rejected_matches.returncode, 0)
            self.assertIn("实际 2 处", rejected_matches.stderr)
            rejected_port = self.run_port_override(task_root, from_port="port-9099")
            self.assertNotEqual(rejected_port.returncode, 0)
            self.assertIn("--from-port 必须是 1..65535 的整数", rejected_port.stderr)
            self.assertFalse((task_root / "private-scoring/runtime-port-override.json").exists())

    def test_real_port_conflict_is_detected_without_stopping_port_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            workspace = task_root / "workspace"
            workspace.mkdir(parents=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                occupied_port = listener.getsockname()[1]
            replacement_port = occupied_port
            while replacement_port == occupied_port:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    replacement_port = listener.getsockname()[1]
            (workspace / "server.js").write_text(
                "const http = require('node:http');\n"
                f"http.createServer((_req, res) => res.end('candidate')).listen({occupied_port}, '127.0.0.1');\n",
                encoding="utf-8",
            )
            BuildSubmissionTest.materialize_candidate_integrity(root)
            prepared = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "prepare", "--task-root", str(task_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            unrelated_root = root / "unrelated"
            unrelated_root.mkdir()
            (unrelated_root / "index.html").write_text("unrelated", encoding="utf-8")
            owner = subprocess.Popen(
                [
                    "node", str(STATIC_SERVER), "--root", str(unrelated_root),
                    "--host", "127.0.0.1", "--port", str(occupied_port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready = owner.stdout.readline().strip()
                self.assertTrue(ready.startswith("PASS:"), ready)
                failed = subprocess.run(
                    [
                        "node", str(MANAGED_RUNTIME), "start", "--task-root", str(task_root),
                        "--url", f"http://127.0.0.1:{occupied_port}/", "--", "node", "server.js",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertNotEqual(failed.returncode, 0)
                state = json.loads(
                    (task_root / "private-scoring/runtime-state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["service"]["status"], "START_FAILED_STOPPED", failed.stderr)
                conflict_log = (task_root / "private-scoring/runtime-logs/site.stderr.log").read_text(encoding="utf-8")
                self.assertIn("EADDRINUSE", conflict_log)
                os.kill(owner.pid, 0)
                overridden = self.run_port_override(
                    task_root,
                    from_port=str(occupied_port),
                    to_port=str(replacement_port),
                )
                self.assertEqual(overridden.returncode, 0, overridden.stderr)
                runtime_source = (task_root / "private-scoring/runtime-workspace/server.js").read_text(encoding="utf-8")
                self.assertIn(f"listen({replacement_port}", runtime_source)
                self.assertNotIn(f"listen({occupied_port}", runtime_source)
                os.kill(owner.pid, 0)
            finally:
                owner.terminate()
                owner.communicate(timeout=5)

    def test_submission_validates_port_override_audit_after_runtime_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root, workspace = self.prepare_port_conflict_task(root)
            (task_root / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            result = run_finalize(task_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            BuildSubmissionTest.materialize_evidence(task_root)
            write_json(root / "manifest.json", {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            candidate_before = (workspace / "server.js").read_bytes()
            overridden = self.run_port_override(task_root)
            self.assertEqual(overridden.returncode, 0, overridden.stderr)
            cleaned = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "clean", "--task-root", str(task_root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            command = ["node", str(SUBMISSION), "--package-root", str(root), "--output", str(root / "submission.json")]
            submitted = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(submitted.returncode, 0, submitted.stderr)
            submission = json.loads((root / "submission.json").read_text(encoding="utf-8"))
            port_audit = submission["candidate_artifacts"][0]["runtime_port_overrides"]
            self.assertEqual(port_audit["count"], 1)
            self.assertEqual((workspace / "server.js").read_bytes(), candidate_before)

            conflict_evidence = task_root / "private-scoring/runtime-logs/port-conflict-001.log"
            conflict_evidence.write_text("tampered", encoding="utf-8")
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("端口冲突证据文件校验失败", rejected.stderr)

    def test_managed_static_service_stops_only_its_recorded_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            workspace = task_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "index.html").write_text("managed", encoding="utf-8")
            BuildSubmissionTest.materialize_candidate_integrity(root)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            started = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "start-static", "--task-root", str(task_root), "--port", str(port)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            state_path = task_root / "private-scoring/runtime-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            pid = int(state["service"]["pid"])
            self.assertEqual(state["service"]["pgid"], pid)
            os.kill(pid, 0)
            stopped = subprocess.run(
                ["node", str(MANAGED_RUNTIME), "stop", "--task-root", str(task_root)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["service"]["status"], "STOPPED")
            self.assertTrue(state["service"]["cleanup"]["exact_identity_verified"])
            self.assertFalse((task_root / "private-scoring/runtime-port-override.json").exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_managed_static_service_supports_workspace_relative_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            workspace = task_root / "workspace"
            (workspace / "dist").mkdir(parents=True)
            (workspace / "index.html").write_text("source root", encoding="utf-8")
            (workspace / "dist/index.html").write_text("published dist", encoding="utf-8")
            BuildSubmissionTest.materialize_candidate_integrity(root)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            started = subprocess.run(
                [
                    "node", str(MANAGED_RUNTIME), "start-static",
                    "--task-root", str(task_root), "--root", "dist", "--port", str(port),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            try:
                self.assertEqual(started.returncode, 0, started.stderr)
                with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    self.assertEqual(response.read().decode("utf-8"), "published dist")
                state = json.loads(
                    (task_root / "private-scoring/runtime-state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["service"]["static_root"], "workspace/dist")
            finally:
                subprocess.run(
                    ["node", str(MANAGED_RUNTIME), "stop", "--task-root", str(task_root)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )

    def test_managed_static_service_rejects_unsafe_or_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            workspace = task_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "index.html").write_text("frozen", encoding="utf-8")
            BuildSubmissionTest.materialize_candidate_integrity(root)
            for unsafe_root, expected in (
                (str(root), "workspace 内的相对目录"),
                ("../outside", "workspace 内的相对目录"),
                ("missing", "静态站点目录不存在"),
            ):
                rejected = subprocess.run(
                    [
                        "node", str(MANAGED_RUNTIME), "start-static",
                        "--task-root", str(task_root), "--root", unsafe_root, "--port", "4173",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn(expected, rejected.stderr)
            self.assertFalse((task_root / "private-scoring/runtime-state.json").exists())


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
