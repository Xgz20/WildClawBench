from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from eval import run_batch


class PendingTaskCountTests(unittest.TestCase):
    def test_all_categories_includes_website_generation(self) -> None:
        self.assertIn("07_Website_Generation", run_batch.ALL_CATEGORIES)

    def test_counts_official_and_extension_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            tasks = [
                {"file_path": str(tasks_dir / "01_Productivity_Flow" / "task_1.md")},
                {"file_path": str(tasks_dir / "02_Code_Intelligence" / "task_2.md")},
                {
                    "file_path": str(
                        tasks_dir
                        / "extension"
                        / "01_Productivity_Flow"
                        / "task_3.md"
                    )
                },
            ]

            with patch.object(run_batch, "TASKS_DIR", tasks_dir):
                self.assertEqual(run_batch._pending_task_counts(tasks), (2, 1))

    def test_log_prints_pending_task_source_breakdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            tasks = [
                {"file_path": str(tasks_dir / "01_Productivity_Flow" / "task_1.md")},
                {
                    "file_path": str(
                        tasks_dir
                        / "extension"
                        / "01_Productivity_Flow"
                        / "task_2.md"
                    )
                },
            ]

            with patch.object(run_batch, "TASKS_DIR", tasks_dir), self.assertLogs(
                run_batch.logger, level="INFO"
            ) as logs:
                run_batch._log_pending_task_counts(tasks)

        self.assertIn(
            "待执行用例数: 2（开源评测集: 1，自建评测集 tasks/extension: 1）",
            "\n".join(logs.output),
        )

    def test_grade_forwards_metric_profile(self) -> None:
        task = {
            "automated_checks": "",
            "rubric_criteria": [{"key": "hero", "weight": 1.0}],
            "metric_profile": "web-site-gen",
        }
        grading = Mock(return_value={"overall_score": 1.0})

        with patch.object(run_batch, "run_grading", grading), patch.object(
            run_batch, "format_scores", return_value=""
        ):
            run_batch.grade_the_task(
                "website", "/missing", Path("/tmp/result"), task, {}
            )

        self.assertEqual(
            grading.call_args.kwargs["metric_profile"], "web-site-gen"
        )

    def test_write_evaluation_scope_records_planned_tasks_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            official = tasks_dir / "07_Website_Generation" / "task_official.md"
            extension = (
                tasks_dir / "extension" / "07_Website_Generation" / "task_extension.md"
            )
            tasks = [
                {"task_id": "task_official", "file_path": str(official)},
                {"task_id": "task_extension", "file_path": str(extension)},
            ]
            output_root = Path(tmp) / "output" / "astroncode"

            with patch.object(run_batch, "TASKS_DIR", tasks_dir):
                run_batch._write_evaluation_scope(
                    output_root,
                    tasks,
                    mode="category",
                    categories=["07_Website_Generation"],
                    modality="pure-text",
                    include_tags={"web-site-gen"},
                    exclude_tags={"skip"},
                    runs=1,
                )

            payload = json.loads(
                (output_root / "evaluation_scope.json").read_text(encoding="utf-8")
            )

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["categories"], ["07_Website_Generation"])
        self.assertEqual(payload["include_tags"], ["web-site-gen"])
        self.assertEqual(payload["planned_task_count"], 2)
        self.assertEqual(
            {(item["category"], item["task_id"]) for item in payload["planned_tasks"]},
            {
                ("07_Website_Generation", "task_official"),
                ("07_Website_Generation", "task_extension"),
            },
        )
        self.assertEqual(
            {item["source"] for item in payload["planned_tasks"]},
            {"official", "extension"},
        )


if __name__ == "__main__":
    unittest.main()
