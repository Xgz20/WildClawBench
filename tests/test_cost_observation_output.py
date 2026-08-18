from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from eval import run_batch
from src.utils.grading import print_global_summary, print_summary


def _result_with_unavailable_cost() -> dict:
    return {
        "task_id": "cost-observation-task",
        "scores": {"overall_score": 1.0},
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 15,
            "request_count": 1,
            "cost_usd": 0.0,
            "cost_status": "unavailable",
            "cost_reason": "missing price variables",
        },
    }


class CostObservationOutputTests(unittest.TestCase):
    def test_save_usage_logs_unavailable_instead_of_zero_cost(self) -> None:
        result = _result_with_unavailable_cost()
        usage = result.pop("usage")
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertLogs(run_batch.logger, level="INFO") as captured:
                run_batch.save_usage(Path(temp_dir), result, usage, result["task_id"])
            persisted = json.loads(
                (Path(temp_dir) / "usage.json").read_text(encoding="utf-8")
            )

        self.assertIn("cost:unavailable", "\n".join(captured.output))
        self.assertEqual(persisted["cost_status"], "unavailable")

    def test_category_summary_displays_unavailable_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with redirect_stdout(output):
                print_summary(
                    [_result_with_unavailable_cost()],
                    "04_Search_Retrieval",
                    Path(temp_dir),
                    "model",
                )

        rendered = output.getvalue()
        self.assertIn("unavailable", rendered)
        self.assertNotIn("0.0000$", rendered)

    def test_global_summary_displays_unavailable_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with redirect_stdout(output):
                summary = print_global_summary(
                    [_result_with_unavailable_cost()],
                    Path(temp_dir),
                    "model",
                )

        self.assertIn("Total cost: unavailable", output.getvalue())
        self.assertEqual(summary["global_avg"], 1.0)
        self.assertEqual(summary["scored_task_count"], 1)

    def test_global_summary_includes_invalid_zero_and_exposes_valid_average(self) -> None:
        results = [
            {
                "task_id": "invalid-task",
                "scores": {"overall_score": 0.0},
                "anomalies": {
                    "validity_verdict": "FAIL",
                    "has_validity_failure": True,
                },
            },
            {
                "task_id": "valid-task",
                "scores": {"overall_score": 0.8},
                "anomalies": {"validity_verdict": "PASS"},
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with redirect_stdout(output):
                summary = print_global_summary(
                    results, Path(temp_dir), "model"
                )

        self.assertEqual(summary["global_avg"], 0.4)
        self.assertEqual(summary["valid_global_avg"], 0.8)
        self.assertEqual(summary["validity_failure_run_count"], 1)
        self.assertTrue(summary["invalid_scores_included_in_global_avg"])
        self.assertIn("validity failures included", output.getvalue())


if __name__ == "__main__":
    unittest.main()
