from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from eval import run_batch


class PendingTaskCountTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
