from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.anomalies import (
    RULESET_VERSION,
    SCHEMA_VERSION,
    classify_report_outcome,
    scan_run_dir,
)


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

    def test_grading_timeout_is_framework_failure_and_requires_rerun(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "score.json", {
                "overall_score": 0.0,
                "error": (
                    "Command ['docker', 'exec', 'task', 'python3', "
                    "'/tmp/_grade_runner.py'] timed out after 120 seconds"
                ),
            })

            report = scan_run_dir(run_dir)

            item = self.item(report, "GRADING_SCRIPT_ERROR")
            self.assertIsNotNone(item)
            self.assertEqual(item["stage"], "grading")
            self.assertEqual(item["attribution"], "evaluation_framework")
            self.assertEqual(item["validity_impact"], "fail")
            self.assertEqual(item["rerun_action"], "required_after_fix")
            self.assertEqual(report["validity_verdict"], "FAIL")
            self.assertTrue(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_llm_judge_parse_error_is_framework_failure_and_requires_rerun(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "score.json", {
                "overall_score": 0.0,
                "llm_error": "Extra data: line 6 column 1 (char 89)",
            })

            report = scan_run_dir(run_dir)

            item = self.item(report, "GRADING_SCRIPT_ERROR")
            self.assertIsNotNone(item)
            self.assertEqual(item["attribution"], "evaluation_framework")
            self.assertEqual(item["validity_impact"], "fail")
            self.assertEqual(item["evidence"][0]["field"], "llm_error")
            self.assertEqual(report["validity_verdict"], "FAIL")
            self.assertTrue(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_nested_judge_failure_note_is_framework_failure(self) -> None:
        for notes in (
            "judge failed: judge returned no valid JSON",
            "judge_call_failed: upstream response timed out",
        ):
            with self.subTest(notes=notes):
                temp_dir, run_dir = self.make_run()
                try:
                    self.write_json(run_dir / "score.json", {
                        "overall_score": 0.0,
                        "_grading": {"llm_notes": notes},
                    })

                    report = scan_run_dir(run_dir)
                    item = self.item(report, "GRADING_SCRIPT_ERROR")

                    self.assertIsNotNone(item)
                    self.assertEqual(item["validity_impact"], "fail")
                    self.assertEqual(
                        item["evidence"][0]["field"], "_grading.llm_notes"
                    )
                finally:
                    temp_dir.cleanup()

    def test_normal_nested_judge_note_is_not_an_anomaly(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            self.write_json(run_dir / "score.json", {
                "overall_score": 1.0,
                "_grading": {"llm_notes": "All rubric criteria are satisfied."},
            })

            report = scan_run_dir(run_dir)

            self.assertIsNone(self.item(report, "GRADING_SCRIPT_ERROR"))
            self.assertEqual(report["validity_verdict"], "PASS")
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

    def test_framework_stage_failure_suppresses_derived_empty_and_grading_errors(self) -> None:
        temp_dir, run_dir = self.make_run(events=[])
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "failure_stage": "preparing_workspace",
                "error": "warmup failed", "model": "model-x",
            })
            self.write_json(run_dir / "score.json", {
                "overall_score": 0.0,
                "error": "Grading failed: Traceback: No module named PIL",
            })

            report = scan_run_dir(run_dir)
            ids = [item["id"] for item in report["items"]]

            self.assertEqual(ids.count("EXECUTION_ERROR"), 1)
            self.assertNotIn("EMPTY_TRANSCRIPT", ids)
            self.assertNotIn("GRADING_SCRIPT_ERROR", ids)
        finally:
            temp_dir.cleanup()

    def test_astronclaw_timeout_counts_native_tool_calls(self) -> None:
        events = [
            {"type": "message", "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "id": "c1", "name": "exec"}],
            }},
            {"type": "message", "message": {
                "role": "toolResult", "toolCallId": "c1", "toolName": "exec",
                "content": [{"type": "text", "text": "ok"}],
                "details": {"status": "completed"},
            }},
        ]
        temp_dir, run_dir = self.make_run(events=events)
        try:
            self.write_json(run_dir / "execution_status.json", {
                "status": "timed_out", "timed_out": True, "timeout_seconds": 3600,
                "failure_stage": "astronclaw_running", "model": "model-x",
            })

            item = self.item(scan_run_dir(run_dir), "TASK_TIMED_OUT")

            self.assertIn("1 次工具尝试", item["description"])
            self.assertIn("1 次模型交互", item["description"])
        finally:
            temp_dir.cleanup()

    def test_astronclaw_searxng_configuration_error_requires_rerun(self) -> None:
        events = [
            {"type": "message", "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "id": "c1", "name": "web_search"}],
            }},
            {"type": "message", "message": {
                "role": "toolResult", "toolCallId": "c1", "toolName": "web_search",
                "content": [{"type": "text", "text": '{"status":"error"}'}],
                "details": {
                    "status": "error",
                    "error": "SearXNG base URL is not configured. Set SEARXNG_BASE_URL",
                },
                "isError": False,
            }},
        ]
        temp_dir, run_dir = self.make_run(events=events)
        try:
            report = scan_run_dir(run_dir)
            item = self.item(report, "TOOL_SERVICE_NOT_CONFIGURED")
            self.assertIsNotNone(item)
            self.assertEqual(item["attribution"], "evaluation_environment")
            self.assertEqual(item["validity_impact"], "fail")
            self.assertTrue(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_astronclaw_image_model_configuration_error_requires_rerun(self) -> None:
        events = [
            {"type": "message", "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "id": "c1", "name": "image"}],
            }},
            {"type": "message", "message": {
                "role": "toolResult", "toolCallId": "c1", "toolName": "image",
                "content": [{"type": "text", "text": '{"status":"error"}'}],
                "details": {
                    "status": "error",
                    "error": "Model does not support images: wildclaw/model-x (resolved input: text)",
                },
                "isError": False,
            }},
        ]
        temp_dir, run_dir = self.make_run(events=events)
        try:
            report = scan_run_dir(run_dir)
            item = self.item(report, "TOOL_MODEL_CONFIGURATION_ERROR")
            self.assertIsNotNone(item)
            self.assertEqual(item["attribution"], "evaluation_framework")
            self.assertEqual(item["validity_impact"], "fail")
        finally:
            temp_dir.cleanup()

    def test_xunfei_content_policy_rejection_is_model_outcome(self) -> None:
        temp_dir, run_dir = self.make_run()
        try:
            (run_dir / "gateway.log").write_text(
                "2026-07-29 [agent/embedded] embedded run agent end: "
                "runId=1 isError=true model=model-x provider=wildclaw "
                "error=Xunfei request failed code: 10013, msg: 根据相关法律法规，无法提供答案 "
                "rawError=content policy\n",
                encoding="utf-8",
            )

            report = scan_run_dir(run_dir)
            item = self.item(report, "MODEL_CONTENT_POLICY_REJECTION")

            self.assertIsNotNone(item)
            self.assertEqual(item["attribution"], "model")
            self.assertEqual(item["validity_impact"], "none")
            self.assertIsNone(self.item(report, "MODEL_API_ERROR"))
            self.assertFalse(report["needs_rerun"])
        finally:
            temp_dir.cleanup()

    def test_report_outcome_excludes_framework_errors_from_execution_errors(self) -> None:
        self.assertEqual(classify_report_outcome({
            "status": "error", "failure_stage": "astroncode_running",
            "error": "AstronCode run failed (rc=1)",
        }), "execution_error")
        for stage in ("preparing_workspace", "preparing_harness_input",
                      "launching_harness", "harness_launch_failed"):
            self.assertEqual(classify_report_outcome({
                "status": "error", "failure_stage": stage, "error": "launch failed",
            }), "evaluation_anomaly")
        self.assertEqual(classify_report_outcome({
            "status": "timed_out", "timed_out": True, "error": "timed out",
        }), "timeout")
        self.assertEqual(classify_report_outcome({"status": "finished"}, "grading failed"),
                         "evaluation_anomaly")

    def test_report_outcome_prioritizes_structured_model_api_anomaly(self) -> None:
        status = {
            "status": "error",
            "failure_stage": "astroncode_running",
            "error": "AstronCode run failed (rc=1)",
        }
        anomaly_items = [{
            "code": "MODEL_API_RATE_LIMIT",
            "attribution": "external_service",
            "validity_impact": "review",
        }]

        self.assertEqual(
            classify_report_outcome(status, anomaly_items=anomaly_items),
            "evaluation_anomaly",
        )

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

    def test_resume_marks_reliability_rerun_as_replacement(self) -> None:
        from eval.run_batch import _load_resume_result

        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp)
            run_dir = output_root / "01_suite/task_1/model-x_20260728_1200_abc123"
            run_dir.mkdir(parents=True)
            self.write_json(run_dir / "execution_status.json", {
                "status": "error", "failure_stage": "preparing_workspace",
                "error": "workspace preparation failed", "model": "model-x",
            })
            self.write_json(run_dir / "usage.json", {
                "request_count": 1, "total_tokens": 100,
            })
            self.write_json(run_dir / "score.json", {"overall_score": 0.0})
            events = [{"type": "event", "payload": {"index": index}} for index in range(5)]
            (run_dir / "chat.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events), encoding="utf-8"
            )
            task = {"category": "01_suite", "task_id": "task_1"}

            result = _load_resume_result(
                output_root, task, "model-x",
                rerun_error=True, rerun_anomalous=False,
            )

            self.assertIsNone(result)
            self.assertEqual(task["_reliability_rerun"], {
                "supersedes_run": str(run_dir),
                "trigger": "rerun_error",
            })

    def test_resume_marks_missing_score_run_as_replaced(self) -> None:
        from eval.run_batch import _load_resume_result

        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp)
            run_dir = output_root / "01_suite/task_1/model-x_20260728_1200_abc123"
            run_dir.mkdir(parents=True)
            task = {"category": "01_suite", "task_id": "task_1"}

            result = _load_resume_result(
                output_root, task, "model-x",
                rerun_error=False, rerun_anomalous=False,
            )

            self.assertIsNone(result)
            self.assertEqual(task["_reliability_rerun"], {
                "supersedes_run": str(run_dir),
                "trigger": "missing_or_invalid_score",
            })

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
