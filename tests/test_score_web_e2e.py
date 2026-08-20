from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/init_score.mjs"
FINALIZE = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/finalize_score.mjs"
SUBMISSION = REPO_ROOT / ".agents/skills/score-web-e2e/scripts/build_submission.mjs"


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
        "batch_id": "batch-1",
        "task_id": "task-1",
        "task_name": "站点任务",
        "difficulty": "L1",
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
        "aesthetic_score": None,
        "aesthetic_reason": None,
        "scorer": {"agent": "Codex"},
    }
    return manifest, contract, execution, score_input


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def run_finalize(root: Path, values=None) -> subprocess.CompletedProcess:
    manifest, contract, execution, score_input = values or fixtures()
    write_json(root / "task_manifest.json", manifest)
    write_json(root / "private-scoring/task_contract.json", contract)
    write_json(root / "execution_record.json", execution)
    write_json(root / "private-scoring/score_input.json", score_input)
    return subprocess.run(
        [
            "node", str(FINALIZE),
            "--manifest", str(root / "task_manifest.json"),
            "--task-contract", str(root / "private-scoring/task_contract.json"),
            "--execution-record", str(root / "execution_record.json"),
            "--score-input", str(root / "private-scoring/score_input.json"),
            "--output", str(root / "private-scoring/task_score.json"),
        ],
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

    def test_rejects_aesthetic_score_before_definition(self) -> None:
        values = list(fixtures())
        values[3]["aesthetic_score"] = 88
        with tempfile.TemporaryDirectory() as tmp:
            result = run_finalize(Path(tmp), values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("美观度定义", result.stderr)

    def test_error_status_forces_total_and_dimensions_to_zero(self) -> None:
        values = list(fixtures())
        values[2]["execution"]["status"] = "timeout"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_finalize(root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads((root / "private-scoring/task_score.json").read_text(encoding="utf-8"))
        self.assertEqual(score["metrics"]["total_score"], 0)
        self.assertEqual([item["score"] for item in score["evaluation"]["criteria"]], [None, None])


class BuildSubmissionTest(unittest.TestCase):
    def test_allows_report_config_to_supply_missing_model_id(self) -> None:
        values = list(fixtures())
        values[0]["model"] = {"id": "", "display_name": ""}
        values[2]["model"] = {"id": "", "display_name": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            result = run_finalize(task_root, values)
            self.assertEqual(result.returncode, 0, result.stderr)
            (task_root / "private-scoring/evidence").mkdir(exist_ok=True)
            (task_root / "private-scoring/evidence/a.png").write_bytes(b"png")
            (task_root / "private-scoring/evidence/actions.md").write_text("actions", encoding="utf-8")
            write_json(root / "manifest.json", {
                "batch_id": "batch-1", "source_revision": "abc", "tasks": [{"task_id": "task-1"}],
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

    def test_rejects_secrets_and_builds_submission_after_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "score/tasks/task-1"
            finalize_result = run_finalize(task_root)
            self.assertEqual(finalize_result.returncode, 0, finalize_result.stderr)
            (task_root / "private-scoring/evidence").mkdir(exist_ok=True)
            (task_root / "private-scoring/evidence/a.png").write_bytes(b"png")
            (task_root / "private-scoring/evidence/actions.md").write_text("actions", encoding="utf-8")
            (task_root / "workspace").mkdir()
            (task_root / "workspace/index.html").write_text("ok", encoding="utf-8")
            (task_root / "workspace/.env").write_text("SECRET=x", encoding="utf-8")
            root_manifest = {
                "batch_id": "batch-1",
                "source_revision": "abc",
                "tasks": [{"task_id": "task-1"}],
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


if __name__ == "__main__":
    unittest.main()
