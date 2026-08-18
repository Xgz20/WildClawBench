from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval import run_batch


class BatchSummaryLoggingTests(unittest.TestCase):
    @staticmethod
    def timing() -> dict:
        return {
            "batch_total_seconds": 120.0,
            "task_exec_sum_seconds": 100.0,
            "parallelism": 2,
            "avg_exec_seconds": 50.0,
        }

    def test_batch_completion_log_includes_global_average(self) -> None:
        with self.assertLogs(run_batch.logger, level="INFO") as captured:
            run_batch._log_batch_completion(self.timing(), task_count=2, global_average=0.625)

        rendered = "\n".join(captured.output)
        self.assertIn("跑批完成", rendered)
        self.assertIn("总平均结果=0.6250", rendered)

    def test_batch_completion_log_marks_unavailable_average(self) -> None:
        with self.assertLogs(run_batch.logger, level="INFO") as captured:
            run_batch._log_batch_completion(self.timing(), task_count=2, global_average=None)

        self.assertIn("总平均结果=不可用", "\n".join(captured.output))

    def test_batch_completion_log_keeps_invalid_scores_in_total(self) -> None:
        with self.assertLogs(run_batch.logger, level="INFO") as captured:
            run_batch._log_batch_completion(
                self.timing(),
                task_count=2,
                global_average=0.4,
                valid_global_average=0.8,
                validity_failure_count=1,
                validity_failure_task_count=1,
            )

        rendered = "\n".join(captured.output)
        self.assertIn("总平均结果=0.4000", rendered)
        self.assertIn("有效结果平均=0.8000", rendered)
        self.assertIn("有效性失败=1次/1题", rendered)

    def test_rerun_outcome_logs_success_and_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, self.assertLogs(
            run_batch.logger, level="INFO"
        ) as captured:
            root = Path(temp_dir)
            old_run = root / "old-run"
            new_run = root / "new-run"
            old_run.mkdir()
            new_run.mkdir()
            (old_run / "anomalies.json").write_text(json.dumps({
                "items": [{"id": "JUDGE_SCHEMA_MISMATCH"}],
            }))
            (new_run / "score.json").write_text('{"overall_score": 0.8}')
            (new_run / "judge").mkdir()
            (new_run / "judge/summary.json").write_text(json.dumps({
                "status": "success", "attempt_count": 2, "selected_attempt": 2,
            }))

            record = run_batch._record_rerun_outcome(
                task_id="task_011",
                output_dir=new_run,
                rerun_metadata={
                    "supersedes_run": str(old_run),
                    "trigger": "rerun_error",
                },
                anomalies={
                    "items": [],
                    "has_validity_failure": False,
                    "needs_rerun": False,
                    "needs_review": False,
                },
            )

            self.assertEqual(record["status"], "success")
            self.assertEqual(record["resolved_anomalies"], ["JUDGE_SCHEMA_MISMATCH"])
            self.assertEqual(record["judge_attempt_count"], 2)
            self.assertEqual(record["judge_selected_attempt"], 2)
            self.assertEqual(
                json.loads((new_run / "rerun_result.json").read_text())["status"],
                "success",
            )
            self.assertIn("RERUN SUCCESS", "\n".join(captured.output))

    def test_rerun_outcome_logs_failure_when_validity_issue_remains(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, self.assertLogs(
            run_batch.logger, level="WARNING"
        ) as captured:
            root = Path(temp_dir)
            old_run = root / "old-run"
            new_run = root / "new-run"
            old_run.mkdir()
            new_run.mkdir()
            (old_run / "anomalies.json").write_text(json.dumps({
                "items": [{"id": "JUDGE_SCHEMA_MISMATCH"}],
            }))
            (new_run / "score.json").write_text('{"overall_score": 0.0}')

            record = run_batch._record_rerun_outcome(
                task_id="task_011",
                output_dir=new_run,
                rerun_metadata={"supersedes_run": str(old_run)},
                anomalies={
                    "items": [{"id": "JUDGE_SCHEMA_MISMATCH"}],
                    "has_validity_failure": True,
                    "needs_rerun": True,
                    "needs_review": False,
                },
            )

            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["remaining_anomalies"], ["JUDGE_SCHEMA_MISMATCH"])
            self.assertIn("RERUN FAILED", "\n".join(captured.output))

    def test_generate_global_summary_returns_average(self) -> None:
        summary = {
            "global_avg": 0.625,
            "scored_task_count": 2,
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            run_batch,
            "print_global_summary",
            return_value=summary,
        ):
            average = run_batch._generate_global_summary_safely(
                [{"task_id": "task-1", "scores": {"overall_score": 0.625}}],
                Path(temp_dir),
                "model",
                timing={"batch_total_seconds": 10.0},
            )

        self.assertEqual(average, 0.625)

    def test_generate_global_summary_returns_none_without_scored_tasks(self) -> None:
        summary = {
            "global_avg": 0.0,
            "scored_task_count": 0,
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            run_batch,
            "print_global_summary",
            return_value=summary,
        ):
            average = run_batch._generate_global_summary_safely(
                [{"task_id": "task-1", "scores": {}}],
                Path(temp_dir),
                "model",
                timing={},
            )

        self.assertIsNone(average)

    def test_generate_global_summary_failure_does_not_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            run_batch,
            "print_global_summary",
            side_effect=FileNotFoundError("missing dependency"),
        ), self.assertLogs(run_batch.logger, level="WARNING") as captured:
            average = run_batch._generate_global_summary_safely(
                [{"task_id": "task-1", "scores": {"overall_score": 1.0}}],
                Path(temp_dir),
                "model",
                timing={},
            )

        self.assertIsNone(average)
        self.assertIn("跑批总平均结果生成失败，继续主流程", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
