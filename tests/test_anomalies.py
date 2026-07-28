from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.anomalies import scan_run_dir


class AnomalyDetectionTest(unittest.TestCase):
    def make_run(self, agent_log: str) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        run_dir = Path(temp_dir.name)
        (run_dir / "execution_status.json").write_text(
            json.dumps({"status": "finished", "timed_out": False, "elapsed_time": 30}),
            encoding="utf-8",
        )
        (run_dir / "usage.json").write_text(
            json.dumps({"request_count": 1, "total_tokens": 100}), encoding="utf-8"
        )
        (run_dir / "score.json").write_text(
            json.dumps({"overall_score": 0.5}), encoding="utf-8"
        )
        events = [{"type": "event", "payload": {"index": index}} for index in range(5)]
        (run_dir / "chat.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events), encoding="utf-8"
        )
        (run_dir / "agent.log").write_text(agent_log, encoding="utf-8")
        return temp_dir, run_dir

    def test_task_content_and_tool_output_do_not_trigger_api_failure(self) -> None:
        temp_dir, run_dir = self.make_run(
            'Task: add rate limiting\n'
            '{"error":"rate_limit_exceeded","message":"Too many requests"}\n'
            'The model retried and completed the task.\n'
        )
        try:
            report = scan_run_dir(run_dir)
            self.assertFalse(any(item["id"] == "API_RATE_LIMIT" for item in report["items"]))
        finally:
            temp_dir.cleanup()

    def test_explicit_runtime_error_triggers_api_failure(self) -> None:
        temp_dir, run_dir = self.make_run(
            'level=ERROR agent=build error="HTTP 429 too many requests"\n'
        )
        try:
            report = scan_run_dir(run_dir)
            self.assertTrue(any(item["id"] == "API_RATE_LIMIT" for item in report["items"]))
        finally:
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
