from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents/skills/report-web-e2e/scripts/aggregate_web_e2e_results.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aggregate_web_e2e_results", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


report_module = load_module()


def task(task_id: str, score: float, difficulty: str, *, execution="completed", evaluation="completed"):
    return {
        "identity": {
            "task_id": task_id,
            "task_name": task_id,
            "difficulty": difficulty,
        },
        "execution": {"status": execution, "duration_seconds": 10},
        "evaluation": {"status": evaluation},
        "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100, "request_count": 2, "cost_usd": 0.1},
        "tools": {"call_count": 4, "format_accuracy": 1.0},
        "metrics": {
            "total_score": score,
            "aesthetic": {"score": None, "max_score": 100, "included_in_total": False, "status": "pending_definition"},
            "primary_dimensions": {
                "content_structure": score,
                "interaction_function": score,
                "visual_layout": score,
            },
            "secondary_dimensions": {"basic_content": score},
        },
    }


def submission(model: str, harness: str, scores: list[float]):
    tasks = [task("task-1", scores[0], "L1"), task("task-2", scores[1], "L2")]
    return {
        "schema_version": report_module.SUBMISSION_SCHEMA,
        "batch_id": "batch-1",
        "source_revision": "abc",
        "unit": {
            "model_id": model,
            "model_display_name": model.upper(),
            "harness_id": harness,
            "harness_display_name": harness.title(),
        },
        "task_ids": ["task-1", "task-2"],
        "tasks": tasks,
    }


def report_config():
    return {
        "schema_version": report_module.REPORT_CONFIG_SCHEMA,
        "batch_id": "batch-1",
        "units": [
            {
                "model_id": "m1", "model_display_name": "模型一",
                "harness_id": "trae", "harness_display_name": "Trae Desktop",
                "reasoning_effort": "max", "order": 1,
            },
            {
                "model_id": "m1", "model_display_name": "模型一",
                "harness_id": "codex", "harness_display_name": "Codex Desktop",
                "reasoning_effort": "high", "order": 2,
            },
        ],
    }


class ReportWebE2ETest(unittest.TestCase):
    def test_loads_zip_and_tar_gz_submissions(self) -> None:
        payload = submission("m1", "codex", [100, 50])
        encoded = json.dumps(payload).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "submission.zip"
            tar_path = root / "submission.tar.gz"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("submission.json", encoded)
            with tarfile.open(tar_path, "w:gz") as archive:
                info = tarfile.TarInfo("submission.json")
                info.size = len(encoded)
                archive.addfile(info, io.BytesIO(encoded))
            loaded_zip = report_module.load_submission(zip_path)
            loaded_tar = report_module.load_submission(tar_path)
        self.assertEqual(loaded_zip["batch_id"], "batch-1")
        self.assertEqual(loaded_tar["unit"]["harness_id"], "codex")

    def test_builds_requested_metrics_and_markdown_sections(self) -> None:
        data = report_module.build_report_data([
            submission("m1", "codex", [100, 50]),
            submission("m1", "trae", [80, 20]),
        ], report_config())
        self.assertEqual(data["units"][0]["total_average_score"], 50.0)
        self.assertEqual(data["units"][0]["unit"], "模型一@Trae Desktop")
        self.assertEqual(data["units"][0]["reasoning_effort"], "max")
        self.assertEqual(data["units"][0]["case_count"], 2)
        self.assertEqual(data["units"][0]["total_tokens"], 200.0)
        self.assertIsNone(data["units"][0]["aesthetic_score"])
        markdown = report_module.render_markdown(data)
        for heading in ("## 结论", "## 总览", "## 难度等级", "## 一级维度", "## 二级维度"):
            self.assertIn(heading, markdown)
        self.assertIn("评测异常数", markdown)
        self.assertIn("页面美观度尚未提供正式指标定义", markdown)

    def test_loads_and_validates_report_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch-1.yaml"
            path.write_text(
                """schema_version: wildclawbench.web-e2e-report-config/v1
batch_id: batch-1
units:
  - model_id: m1
    model_display_name: 模型一
    harness_id: codex
    harness_display_name: Codex
    reasoning_effort: high
    order: 1
""",
                encoding="utf-8",
            )
            config = report_module.load_report_config(path)
        self.assertEqual(config["units"][0]["reasoning_effort"], "high")

    def test_rejects_report_config_unit_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "范围不一致"):
            report_module.build_report_data([submission("m1", "codex", [100, 50])], report_config())

    def test_report_config_supplies_model_when_submission_omits_it(self) -> None:
        item = submission("m1", "codex", [100, 50])
        item["unit"]["model_id"] = None
        item["unit"]["model_display_name"] = None
        for task_item in item["tasks"]:
            task_item["identity"]["model"] = {"id": "", "display_name": ""}
        single_config = report_config()
        single_config["units"] = [single_config["units"][1]]
        data = report_module.build_report_data([item], single_config)
        self.assertEqual(data["units"][0]["model_id"], "m1")
        self.assertEqual(data["units"][0]["model"], "模型一")

    def test_rejects_inconsistent_task_lists(self) -> None:
        first = submission("m1", "codex", [100, 50])
        second = submission("m1", "trae", [80, 20])
        second["task_ids"] = ["task-2", "task-1"]
        with self.assertRaisesRegex(ValueError, "task_ids"):
            report_module.build_report_data([first, second])

    def test_counts_execution_and_evaluation_failures(self) -> None:
        item = submission("m1", "codex", [100, 0])
        item["tasks"][0]["execution"]["status"] = "timeout"
        item["tasks"][1]["evaluation"]["status"] = "evaluation_error"
        data = report_module.build_report_data([item])
        unit = data["units"][0]
        self.assertEqual(unit["timeout_count"], 1)
        self.assertEqual(unit["evaluation_error_count"], 1)
        self.assertEqual(unit["completed_count"], 0)

    def test_not_recorded_execution_is_normally_completed_after_scoring(self) -> None:
        item = submission("m1", "codex", [100, 50])
        for task_item in item["tasks"]:
            task_item["execution"] = {"status": "not_recorded", "duration_seconds": None}
            task_item["usage"] = {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "request_count": None,
                "cost_usd": None,
            }
            task_item["tools"] = {"call_count": None, "format_accuracy": None}
        data = report_module.build_report_data([item])
        unit = data["units"][0]
        self.assertEqual(unit["completed_count"], 2)
        self.assertEqual(unit["completion_rate"], 100.0)
        self.assertEqual(unit["execution_not_recorded_count"], 2)
        self.assertIsNone(unit["total_tokens"])
        self.assertEqual(unit["execution_error_count"], 0)
        self.assertEqual(unit["timeout_count"], 0)
        self.assertIn("执行错误数和超时数只反映显式记录", report_module.render_markdown(data))


if __name__ == "__main__":
    unittest.main()
