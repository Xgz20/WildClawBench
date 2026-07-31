from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "tools/report/skills/validate-eval-results/scripts/validate_eval_results.py"
)
SPEC = importlib.util.spec_from_file_location("validate_eval_results", SCRIPT)
assert SPEC and SPEC.loader
validate_eval_results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_eval_results)


class ExpectedTasksTest(unittest.TestCase):
    def test_official_and_extension_tasks_are_combined(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tasks = Path(temp)
            official = tasks / "01_Productivity_Flow"
            extension = tasks / "extension/01_Productivity_Flow"
            official.mkdir(parents=True)
            extension.mkdir(parents=True)
            (official / "01_Productivity_Flow_task_1.md").write_text("official")
            (extension / "01_Productivity_Flow_task_001.md").write_text("extension")

            result = validate_eval_results.expected_tasks(tasks)

            self.assertEqual(result["01_Productivity_Flow"], {
                "01_Productivity_Flow_task_1",
                "01_Productivity_Flow_task_001",
            })

    def test_gitignored_local_extension_task_is_excluded(self) -> None:
        repo_tasks = Path(__file__).resolve().parents[1] / "tasks"

        result = validate_eval_results.expected_tasks(repo_tasks)

        self.assertNotIn(
            "04_Search_Retrieval_task_101_csv_gdp_regions",
            result["04_Search_Retrieval"],
        )


class ScanRoundIntegrationTest(unittest.TestCase):
    def _write_run(self, unit_dir: Path, model: str) -> None:
        task_id = "01_Productivity_Flow_task_1"
        run_dir = unit_dir / "01_Productivity_Flow" / task_id / f"{model}_run"
        run_dir.mkdir(parents=True)
        (run_dir / "execution_status.json").write_text(json.dumps({
            "status": "finished",
            "model": model,
            "timeout_seconds": 300,
            "timed_out": False,
        }), encoding="utf-8")
        (run_dir / "usage.json").write_text(json.dumps({
            "request_count": 1,
            "total_tokens": 10,
        }), encoding="utf-8")
        (run_dir / "score.json").write_text(
            json.dumps({"overall_score": 1.0}), encoding="utf-8"
        )
        (run_dir / "chat.jsonl").write_text(json.dumps({
            "message": {
                "role": "toolResult",
                "toolName": "web_search",
                "toolCallId": "call-1",
                "details": {
                    "status": "error",
                    "error": "SearXNG base URL is not configured. Set SEARXNG_BASE_URL",
                },
            },
        }) + "\n", encoding="utf-8")
        (unit_dir / f"summary_all_{model}.json").write_text(json.dumps({
            "task_count": 1,
            "global_avg": 1.0,
        }), encoding="utf-8")

    def test_filtered_extensions_and_common_environment_signal_do_not_add_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tasks = root / "tasks"
            official = tasks / "01_Productivity_Flow"
            extension = tasks / "extension" / "01_Productivity_Flow"
            official.mkdir(parents=True)
            extension.mkdir(parents=True)
            (official / "01_Productivity_Flow_task_1.md").write_text(
                "---\nid: 01_Productivity_Flow_task_1\nmodality: pure-text\n---\n",
                encoding="utf-8",
            )
            (extension / "01_Productivity_Flow_task_001.md").write_text(
                "---\nid: 01_Productivity_Flow_task_001\nmodality: pure-text\n"
                "tags:\n  - custom\n---\n",
                encoding="utf-8",
            )

            results = root / "round"
            for model in ("model-a", "model-b"):
                unit_dir = results / model / "astronclaw"
                unit_dir.mkdir(parents=True)
                (unit_dir / "run.log").write_text(
                    "Category: 01_Productivity_Flow, 2 tasks (official + extension)\n"
                    "Exclude-tag filter (none of ['custom']): 1/2 tasks kept in "
                    "01_Productivity_Flow\n",
                    encoding="utf-8",
                )
                self._write_run(unit_dir, model)

            report = validate_eval_results.scan_round(results, tasks)
            ids = [item["id"] for item in report["findings"]]

            self.assertNotIn("TASK_MISSING", ids)
            self.assertNotIn("COMMON_MODE_ENV_FAILURE", ids)
            signals = [
                item for item in report["findings"]
                if item["id"] == "COMMON_MODE_ENV_SIGNAL"
            ]
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["severity"], "warning")
            self.assertEqual(signals[0]["task_id"], "01_Productivity_Flow_task_1")


if __name__ == "__main__":
    unittest.main()
