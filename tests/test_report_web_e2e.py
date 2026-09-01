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


def task(
    task_id: str,
    score: float,
    difficulty: str,
    *,
    execution="completed",
    evaluation="completed",
    aesthetic_score: float | None = None,
):
    aesthetic = {
        "score": aesthetic_score,
        "max_score": 100,
        "included_in_total": False,
        "status": "completed" if aesthetic_score is not None else "pending_definition",
        "primary_dimensions": {
            key: aesthetic_score for key in report_module.AESTHETIC_PRIMARY_LABELS
        } if aesthetic_score is not None else {},
        "secondary_dimensions": {
            key: "MET" for key in report_module.AESTHETIC_SECONDARY_LABELS
        } if aesthetic_score is not None else {},
        "secondary_dimension_scores": {
            key: 100 for key in report_module.AESTHETIC_SECONDARY_LABELS
        } if aesthetic_score is not None else {},
    }
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
            "aesthetic": aesthetic,
            "primary_dimensions": {
                "content_structure": score,
                "interaction_function": score,
                "visual_layout": score,
            },
            "secondary_dimensions": {"basic_content": score},
        },
    }


def submission(model: str, harness: str, scores: list[float], aesthetic_scores: list[float] | None = None):
    aesthetic_scores = aesthetic_scores or [None, None]
    tasks = [
        task("task-1", scores[0], "L1", aesthetic_score=aesthetic_scores[0]),
        task("task-2", scores[1], "L2", aesthetic_score=aesthetic_scores[1]),
    ]
    return {
        "schema_version": report_module.SUBMISSION_SCHEMA,
        "batch_id": "batch-1",
        "source_revision": "abc",
        "metric_profile": report_module.DETAILED_PROFILE,
        "unit": {
            "model_id": model,
            "model_display_name": model.upper(),
            "harness_id": harness,
            "harness_display_name": harness.title(),
        },
        "task_ids": ["task-1", "task-2"],
        "tasks": tasks,
    }


def artifactsbench_submission(model: str, harness: str, scores: list[float]):
    item = submission(model, harness, scores)
    item["metric_profile"] = report_module.ARTIFACTSBENCH_PROFILE
    for task_item in item["tasks"]:
        task_item["metric_profile"] = report_module.ARTIFACTSBENCH_PROFILE
        task_item["metrics"]["primary_dimensions"] = {}
        task_item["metrics"]["secondary_dimensions"] = {}
        task_item["metrics"]["aesthetic"] = {
            "score": None,
            "included_in_total": False,
            "status": "not_applicable",
            "primary_dimensions": {},
            "secondary_dimensions": {},
            "secondary_dimension_scores": {},
        }
    return item


def report_config():
    return {
        "schema_version": report_module.REPORT_CONFIG_SCHEMA,
        "batch_id": "batch-1",
        "metric_profile": report_module.DETAILED_PROFILE,
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
        self.assertIn("没有可用的页面美观度结果", markdown)

    def test_artifactsbench_report_only_renders_overall_and_difficulty(self) -> None:
        config = report_config()
        config["metric_profile"] = report_module.ARTIFACTSBENCH_PROFILE
        data = report_module.build_report_data([
            artifactsbench_submission("m1", "codex", [70, 90]),
            artifactsbench_submission("m1", "trae", [60, 80]),
        ], config)
        self.assertEqual(data["metric_profile"], report_module.ARTIFACTSBENCH_PROFILE)
        self.assertEqual(data["labels"]["primary"], {})
        self.assertEqual(data["labels"]["secondary"], {})
        self.assertEqual(data["labels"]["aesthetic_primary"], {})
        self.assertIsNone(data["units"][0]["aesthetic_score"])
        markdown = report_module.render_markdown(data)
        for heading in ("## 结论", "## 总览", "## 难度等级"):
            self.assertIn(heading, markdown)
        for excluded in ("## 一级维度", "## 二级维度", "美观度总分"):
            self.assertNotIn(excluded, markdown)
        self.assertIn("原始 0–10 Criterion", markdown)

    def test_rejects_mixed_metric_profiles(self) -> None:
        with self.assertRaisesRegex(ValueError, "metric_profile 不一致"):
            report_module.build_report_data([
                submission("m1", "codex", [100, 50]),
                artifactsbench_submission("m1", "trae", [80, 20]),
            ])

    def test_rejects_report_config_profile_mismatch(self) -> None:
        config = report_config()
        config["units"] = [config["units"][1]]
        with self.assertRaisesRegex(ValueError, "metric_profile 与回传包不一致"):
            report_module.build_report_data([
                artifactsbench_submission("m1", "codex", [70, 90]),
            ], config)

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

    def test_aggregates_aesthetic_total_primary_and_secondary_metrics(self) -> None:
        item = submission("m1", "codex", [100, 50], [80, 60])
        item["tasks"][1]["metrics"]["aesthetic"]["secondary_dimensions"]["v-01"] = "PARTIAL"
        item["tasks"][1]["metrics"]["aesthetic"]["secondary_dimensions"]["v-02"] = "NA"
        data = report_module.build_report_data([item])
        unit = data["units"][0]
        self.assertEqual(unit["aesthetic_score"], 70.0)
        self.assertEqual(unit["aesthetic_primary_dimensions"]["render_integrity"], 70.0)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["met_count"], 1)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["partial_count"], 1)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["met_rate"], 50.0)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["score_sum"], 150)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["average_score"], 75.0)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["score_rate"], 75.0)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-02"]["na_count"], 1)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-02"]["met_rate"], 100.0)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-02"]["score_rate"], 100.0)
        markdown = report_module.render_markdown(data)
        self.assertIn("### 美观度一级维度", markdown)
        self.assertIn("### 美观度二级维度", markdown)
        self.assertIn("美观度总分", markdown)
        self.assertIn("v-01 完整渲染 平均分", markdown)

    def test_translates_new_secondary_dimensions_and_exposes_primary_groups(self) -> None:
        item = submission("m1", "codex", [100, 50], [80, 60])
        for task_item in item["tasks"]:
            task_item["metrics"]["secondary_dimensions"] = {
                "realtime_auto_progress": 100,
                "rule_settlement": 50,
            }
        data = report_module.build_report_data([item])
        self.assertEqual(data["labels"]["secondary"]["realtime_auto_progress"], "实时自动推进")
        self.assertEqual(data["labels"]["secondary"]["rule_settlement"], "规则结算")
        self.assertEqual(
            data["labels"]["secondary_primary"]["realtime_auto_progress"],
            "interaction_function",
        )
        self.assertEqual(
            data["labels"]["aesthetic_secondary_primary"]["p-01"],
            "layout_hierarchy",
        )
        aesthetic_keys = list(data["labels"]["aesthetic_secondary"])
        self.assertLess(aesthetic_keys.index("p-01"), aesthetic_keys.index("v-09"))
        markdown = report_module.render_markdown(data)
        self.assertIn("实时自动推进", markdown)
        self.assertIn("规则结算", markdown)
        self.assertNotIn("realtime_auto_progress", markdown)
        self.assertNotIn("rule_settlement", markdown)

    def test_excludes_non_completed_aesthetic_payloads(self) -> None:
        item = submission("m1", "codex", [100, 50], [80, 60])
        item["tasks"][1]["metrics"]["aesthetic"]["status"] = "evaluation_error"
        data = report_module.build_report_data([item])
        unit = data["units"][0]
        self.assertEqual(unit["aesthetic_score"], 80.0)
        self.assertEqual(unit["aesthetic_sample_count"], 1)
        self.assertEqual(unit["aesthetic_secondary_dimensions"]["v-01"]["met_count"], 1)
        self.assertIsNone(data["detail_rows"][1]["aesthetic_score"])

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
