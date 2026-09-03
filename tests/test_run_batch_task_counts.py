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
                    invocation_id="test-invocation",
                    recorded_at="2026-09-03T17:00:00+08:00",
                )

            payload = json.loads(
                (output_root / "evaluation_scope.json").read_text(encoding="utf-8")
            )
            history_files = list(
                (output_root / "evaluation_scope_history").glob("*.json")
            )
            history = json.loads(history_files[0].read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["scope_semantics"], "accumulated")
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
        for item in payload["planned_tasks"]:
            provenance = item["provenance"]
            self.assertEqual(provenance["provenance_status"], "complete")
            for key in (
                "task_sha256",
                "execution_contract_sha256",
                "scoring_contract_sha256",
            ):
                self.assertRegex(provenance[key], r"^[0-9a-f]{64}$")
        self.assertEqual(len(history_files), 1)
        self.assertEqual(history["scope_semantics"], "invocation")
        self.assertEqual(history["invocation_id"], "test-invocation")
        self.assertEqual(history["recorded_at"], "2026-09-03T17:00:00+08:00")
        self.assertEqual(history["categories"], ["07_Website_Generation"])
        self.assertEqual(history["include_tags"], ["web-site-gen"])
        self.assertEqual(history["pending_task_count"], 2)
        self.assertEqual(history["resumed_task_count"], 0)

    def test_evaluation_scope_accumulates_and_resume_subset_does_not_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            category_dir = tasks_dir / "01_suite"
            first = {
                "task_id": "task_a",
                "category": "01_suite",
                "file_path": str(category_dir / "task_a.md"),
            }
            second = {
                "task_id": "task_b",
                "category": "01_suite",
                "file_path": str(category_dir / "task_b.md"),
            }
            output_root = Path(tmp) / "smoke" / "astroncode"

            with patch.object(run_batch, "TASKS_DIR", tasks_dir):
                run_batch._write_evaluation_scope(
                    output_root,
                    [first, second],
                    mode="category",
                    categories=["01_suite"],
                    modality=None,
                    include_tags=set(),
                    exclude_tags=set(),
                    runs=1,
                    pending_tasks=[first, second],
                )
                before = (output_root / "evaluation_scope.json").read_bytes()
                run_batch._write_evaluation_scope(
                    output_root,
                    [first],
                    mode="task",
                    categories=["01_suite"],
                    modality=None,
                    include_tags=set(),
                    exclude_tags=set(),
                    runs=1,
                    pending_tasks=[],
                )

            after = (output_root / "evaluation_scope.json").read_bytes()
            payload = json.loads(after)
            histories = sorted(
                (output_root / "evaluation_scope_history").glob("*.json")
            )
            latest_history = json.loads(histories[-1].read_text(encoding="utf-8"))

        self.assertEqual(before, after)
        self.assertEqual(payload["planned_task_count"], 2)
        self.assertEqual(
            [item["task_id"] for item in payload["planned_tasks"]],
            ["task_a", "task_b"],
        )
        self.assertEqual(len(histories), 2)
        self.assertEqual(latest_history["planned_task_count"], 1)
        self.assertEqual(latest_history["pending_task_count"], 0)
        self.assertEqual(latest_history["resumed_task_count"], 1)
        self.assertEqual(latest_history["scheduled_run_count"], 0)

    def test_evaluation_scope_refuses_to_overwrite_invalid_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            task = {
                "task_id": "task_a",
                "category": "01_suite",
                "file_path": str(tasks_dir / "01_suite" / "task_a.md"),
            }
            output_root = Path(tmp) / "output"
            output_root.mkdir()
            scope_path = output_root / "evaluation_scope.json"
            scope_path.write_text("{invalid", encoding="utf-8")

            with patch.object(run_batch, "TASKS_DIR", tasks_dir), self.assertRaisesRegex(
                ValueError, "拒绝覆盖"
            ):
                run_batch._write_evaluation_scope(
                    output_root,
                    [task],
                    mode="task",
                    categories=["01_suite"],
                    modality=None,
                    include_tags=set(),
                    exclude_tags=set(),
                    runs=1,
                )

            self.assertEqual(scope_path.read_text(encoding="utf-8"), "{invalid")

    def test_evaluation_scope_upgrades_v1_and_keeps_existing_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = Path(tmp) / "tasks"
            output_root = Path(tmp) / "output"
            output_root.mkdir()
            (output_root / "evaluation_scope.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mode": "task",
                        "planned_task_count": 1,
                        "planned_tasks": [
                            {
                                "category": "01_suite",
                                "task_id": "legacy_task",
                                "source": "extension",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            new_task = {
                "task_id": "new_task",
                "category": "01_suite",
                "file_path": str(tasks_dir / "01_suite" / "new_task.md"),
            }

            with patch.object(run_batch, "TASKS_DIR", tasks_dir):
                run_batch._write_evaluation_scope(
                    output_root,
                    [new_task],
                    mode="task",
                    categories=["01_suite"],
                    modality=None,
                    include_tags=set(),
                    exclude_tags=set(),
                    runs=1,
                )

            payload = json.loads(
                (output_root / "evaluation_scope.json").read_text(encoding="utf-8")
            )

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["planned_task_count"], 2)
        self.assertEqual(
            [item["task_id"] for item in payload["planned_tasks"]],
            ["legacy_task", "new_task"],
        )


if __name__ == "__main__":
    unittest.main()
