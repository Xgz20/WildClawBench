from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.anomalies import RULESET_VERSION, SCHEMA_VERSION, scan_run_dir


class AnomalyDetectionTest(unittest.TestCase):
    def make_run(
        self,
        agent_log: str = "",
        *,
        events: list[dict] | None = None,
    ) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        run_dir = Path(temp_dir.name)
        self.write_json(
            run_dir / "execution_status.json",
            {"status": "finished", "timed_out": False, "elapsed_time": 30,
             "model": "model-x"},
        )
        self.write_json(
            run_dir / "usage.json",
            {"request_count": 1, "total_tokens": 100},
        )
        self.write_json(run_dir / "score.json", {"overall_score": 0.5})
        if events is None:
            events = [{"type": "event", "payload": {"index": index}} for index in range(5)]
        (run_dir / "chat.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events), encoding="utf-8"
        )
        (run_dir / "agent.log").write_text(agent_log, encoding="utf-8")
        return temp_dir, run_dir

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def item(report: dict, rule_id: str) -> dict | None:
        return next((item for item in report["items"] if item["id"] == rule_id), None)

    def test_schema_and_clean_run(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            report = scan_run_dir(run_dir)
            self.assertEqual(report["schema_version"], SCHEMA_VERSION)
            self.assertEqual(report["ruleset_version"], RULESET_VERSION)
            self.assertEqual(report["validity_verdict"], "PASS")
            self.assertFalse(report["has_error"])
        finally:
            temp_dir.cleanup()

    def test_agent_log_api_keywords_never_trigger_model_api_failure(self) -> None:
        temp_dir, run_dir = self.make_run(
            'level=ERROR agent=build error="HTTP 429 too many requests"\n'
            'ERROR: service unavailable from /gmail/messages\n'
        )
        try:
            ids = {item["id"] for item in scan_run_dir(run_dir)["items"]}
            self.assertNotIn("MODEL_API_RATE_LIMIT", ids)
            self.assertNotIn("MODEL_API_SERVER_ERROR", ids)
        finally:
            temp_dir.cleanup()

    def test_tool_output_api_keywords_do_not_trigger_model_api_failure(self) -> None:
        events = [
            {"type": "response_item", "payload": {
                "type": "function_call_output", "output": "GitHub HTTP 429 rate limit"
            }},
            *[{"type": "event", "payload": {"index": index}} for index in range(4)],
        ]
        temp_dir, run_dir = self.make_run(events=events)
        try:
            ids = {item["id"] for item in scan_run_dir(run_dir)["items"]}
            self.assertNotIn("MODEL_API_RATE_LIMIT", ids)
        finally:
            temp_dir.cleanup()

    def test_structured_model_api_rate_limit_requires_review(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            status = json.loads((run_dir / "execution_status.json").read_text(encoding="utf-8"))
            status["model"] = "openrouter/model-x"
            self.write_json(run_dir / "execution_status.json", status)
            (run_dir / "runtime_events.jsonl").write_text(json.dumps({
                "stage": "model_inference",
                "source": "astroncode_adapter",
                "model": "model-x",
                "endpoint_host": "maas.example.test?api_key=sk-abcdefghijk",
                "event_type": "request_failed",
                "http_status": 429,
                "error_type": "rate_limit",
                "recovered": True,
            }) + "\n", encoding="utf-8")
            report = scan_run_dir(run_dir)
            item = self.item(report, "MODEL_API_RATE_LIMIT")
            self.assertIsNotNone(item)
            self.assertEqual(item["attribution"], "external_service")
            self.assertEqual(item["validity_impact"], "review")
            self.assertEqual(report["validity_verdict"], "REVIEW")
            self.assertFalse(report["needs_rerun"])
            self.assertNotIn("sk-abcdefghijk", json.dumps(report))
        finally:
            temp_dir.cleanup()

    def test_non_model_runtime_event_is_excluded(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            (run_dir / "runtime_events.jsonl").write_text(json.dumps({
                "stage": "tool_execution",
                "source": "gmail_mock",
                "event_type": "request_failed",
                "http_status": 500,
            }) + "\n", encoding="utf-8")
            ids = {item["id"] for item in scan_run_dir(run_dir)["items"]}
            self.assertNotIn("MODEL_API_SERVER_ERROR", ids)
        finally:
            temp_dir.cleanup()

    def test_model_error_at_end_of_large_raw_session_is_detected(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            session = run_dir / "astroncode_sessions/2026/07/28/session.jsonl"
            session.parent.mkdir(parents=True)
            error_event = {
                "type": "event_msg",
                "payload": {"type": "error", "message": "HTTP 503 service unavailable"},
            }
            session.write_text(
                ("x" * 4_100_000) + "\n" + json.dumps(error_event) + "\n",
                encoding="utf-8",
            )
            report = scan_run_dir(run_dir)
            item = self.item(report, "MODEL_API_SERVER_ERROR")
            self.assertIsNotNone(item)
            self.assertEqual(item["validity_impact"], "review")
        finally:
            temp_dir.cleanup()

    def test_model_interaction_timeout_is_capability_outcome(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "timed_out", "timed_out": True, "timeout_seconds": 3600,
                "failure_stage": "astroncode_running", "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            item = self.item(report, "TASK_TIMED_OUT")
            self.assertEqual(item["attribution"], "model")
            self.assertEqual(item["validity_impact"], "none")
            self.assertTrue(report["has_model_or_harness_issue"])
            self.assertFalse(report["has_validity_failure"])
            self.assertFalse(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_harness_exit_is_capability_outcome(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "timed_out": False, "failure_stage": "astroncode_running",
                "error": "AstronCode run failed (rc=1)", "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            item = self.item(report, "EXECUTION_ERROR")
            self.assertEqual(item["attribution"], "harness")
            self.assertEqual(item["validity_impact"], "none")
            self.assertFalse(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_legacy_harness_exit_prefix_is_capability_outcome(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "timed_out": False,
                "error": "OpenCode run failed (rc=1): model interaction stopped",
                "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            item = self.item(report, "EXECUTION_ERROR")
            self.assertEqual(item["attribution"], "harness")
            self.assertEqual(item["validity_impact"], "none")
        finally:
            temp_dir.cleanup()

    def test_framework_stage_failure_requires_rerun(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "failure_stage": "preparing_workspace",
                "error": "workspace preparation failed", "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            item = self.item(report, "EXECUTION_ERROR")
            self.assertEqual(item["attribution"], "evaluation_framework")
            self.assertEqual(report["validity_verdict"], "FAIL")
            self.assertTrue(report["has_error"])
            self.assertTrue(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_error_text_without_failure_stage_cannot_prove_environment_failure(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error",
                "error": "model output mentioned: container example not found",
                "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            item = self.item(report, "EXECUTION_ERROR")
            self.assertEqual(item["attribution"], "undetermined")
            self.assertEqual(item["validity_impact"], "review")
            self.assertFalse(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_empty_primary_transcript_falls_back_to_compat_transcript(self) -> None:
        temp_dir, run_dir = self.make_run(events=[])
        try:
            compat = [{"type": "event", "payload": {"index": index}} for index in range(5)]
            (run_dir / "chat_openclaw.jsonl").write_text(
                "\n".join(json.dumps(event) for event in compat), encoding="utf-8"
            )
            self.assertIsNone(self.item(scan_run_dir(run_dir), "EMPTY_TRANSCRIPT"))
        finally:
            temp_dir.cleanup()

    def test_raw_session_without_standard_transcript_is_collection_failure(self) -> None:
        temp_dir, run_dir = self.make_run(events=[])
        try:
            session = run_dir / "astroncode_sessions/2026/07/28/session.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(json.dumps({"type": "session_meta", "payload": {}}), encoding="utf-8")
            report = scan_run_dir(run_dir)
            item = self.item(report, "EMPTY_TRANSCRIPT")
            self.assertEqual(item["attribution"], "evaluation_framework")
            self.assertEqual(item["validity_impact"], "fail")
        finally:
            temp_dir.cleanup()

    def test_missing_score_after_model_timeout_does_not_upgrade_to_framework_failure(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            (run_dir / "score.json").unlink()
            self.write_json(run_dir / "execution_status.json", {
                "status": "timed_out", "timed_out": True, "timeout_seconds": 3600,
                "failure_stage": "astroncode_running", "model": "model-x",
            })
            report = scan_run_dir(run_dir)
            score_item = self.item(report, "SCORE_MISSING")
            self.assertEqual(score_item["attribution"], "model")
            self.assertEqual(score_item["validity_impact"], "none")
            self.assertFalse(report["has_validity_failure"])
        finally:
            temp_dir.cleanup()

    def test_anomaly_description_redacts_credentials(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "failure_stage": "preparing_workspace",
                "error": "api_key=sk-abcdefghijk password=hunter2", "model": "model-x",
            })
            serialized = json.dumps(scan_run_dir(run_dir))
            self.assertNotIn("sk-abcdefghijk", serialized)
            self.assertNotIn("hunter2", serialized)
            self.assertIn("REDACTED", serialized)
        finally:
            temp_dir.cleanup()

    def test_resume_recomputes_old_schema_and_uses_needs_rerun(self) -> None:
        from eval.run_batch import _load_resume_result

        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp)
            run_dir = output_root / "01_suite/task_1/model-x_20260728_1200_abc123"
            run_dir.mkdir(parents=True)
            self.write_json(run_dir / "execution_status.json", {
                "status": "finished", "timed_out": False, "elapsed_time": 30,
                "model": "model-x",
            })
            self.write_json(run_dir / "usage.json", {
                "request_count": 1, "total_tokens": 100,
            })
            self.write_json(run_dir / "score.json", {"overall_score": 0.5})
            events = [{"type": "event", "payload": {"index": index}} for index in range(5)]
            (run_dir / "chat.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events), encoding="utf-8"
            )
            self.write_json(run_dir / "anomalies.json", {
                "is_anomalous": True,
                "has_error": True,
                "items": [{"id": "TASK_TIMED_OUT", "severity": "error"}],
            })

            result = _load_resume_result(
                output_root,
                {"category": "01_suite", "task_id": "task_1"},
                "model-x",
                rerun_error=True,
                rerun_anomalous=False,
            )
            self.assertIsNotNone(result)
            refreshed = json.loads((run_dir / "anomalies.json").read_text(encoding="utf-8"))
            self.assertEqual(refreshed["schema_version"], SCHEMA_VERSION)
            self.assertFalse(refreshed["needs_rerun"])

    def test_harness_adapters_preserve_failure_stage(self) -> None:
        from src.agents.astroncode.runner import write_execution_status as write_astroncode
        from src.agents.codex.runner import write_execution_status as write_codex
        from src.agents.opencode.runner import write_execution_status as write_opencode

        with tempfile.TemporaryDirectory() as temp:
            for index, writer in enumerate((write_astroncode, write_codex, write_opencode)):
                run_dir = Path(temp) / str(index)
                writer(run_dir, status="preparing_workspace")
                status = writer(run_dir, status="error", error="preparation failed")
                self.assertEqual(status["failure_stage"], "preparing_workspace")


if __name__ == "__main__":
    unittest.main()
