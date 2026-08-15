from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils import judge_shim


class JudgeShimTest(unittest.TestCase):
    @patch("src.utils.judge_shim.request.urlopen")
    def test_anthropic_json_request_forces_submit_grading_tool(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "id": "msg_1",
            "model": "claude-test",
            "stop_reason": "tool_use",
            "content": [{
                "type": "tool_use",
                "name": "submit_grading",
                "input": {"scores": {"quality": 0.8}, "notes": "ok"},
            }],
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
        }):
            result = judge_shim._anthropic_create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
                wildclaw_judge_schema="scores_notes",
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["tool_choice"], {"type": "tool", "name": "submit_grading"})
        self.assertEqual(payload["tools"][0]["name"], "submit_grading")
        self.assertEqual(
            json.loads(result.choices[0].message.content),
            {"scores": {"quality": 0.8}, "notes": "ok"},
        )
        self.assertEqual(result.choices[0].finish_reason, "tool_use")
        self.assertEqual(result._raw_response["id"], "msg_1")

    @patch("src.utils.judge_shim.request.urlopen")
    def test_legacy_json_request_preserves_task_defined_schema(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "id": "msg_legacy",
            "model": "claude-test",
            "stop_reason": "end_turn",
            "content": [{
                "type": "text",
                "text": '{"score": 0.8, "reason": "legacy rubric"}',
            }],
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
        }):
            result = judge_shim._anthropic_create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("tools", payload)
        self.assertEqual(
            json.loads(result.choices[0].message.content),
            {"score": 0.8, "reason": "legacy rubric"},
        )

    @patch("src.utils.judge_shim.request.urlopen")
    def test_legacy_call_writes_request_response_model_endpoint_and_usage(
        self, urlopen: Mock
    ) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "id": "msg_audit",
            "model": "claude-returned",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"score": 1, "reason": "ok"}'}],
            "usage": {
                "input_tokens": 12,
                "output_tokens": 4,
                "cache_creation_input_tokens": 5,
                "cache_read_input_tokens": 7,
            },
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            client = judge_shim.OpenAI(api_key="must-not-be-persisted")
            client.chat.completions.create(
                model="anthropic/claude-requested",
                max_tokens=300,
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
            )

            judge_dir = Path(temp)
            request_data = json.loads(
                (judge_dir / "attempt-001/request.json").read_text(encoding="utf-8")
            )
            response_data = json.loads(
                (judge_dir / "attempt-001/response.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (judge_dir / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(request_data["mode"], "legacy")
        self.assertEqual(request_data["model"], "anthropic/claude-requested")
        self.assertEqual(request_data["requested_model"], "claude-requested")
        self.assertEqual(
            request_data["effective_requested_model"], "claude-requested"
        )
        self.assertEqual(request_data["endpoint_type"], "anthropic_messages")
        self.assertEqual(request_data["endpoint"], "https://example.test/v1/messages")
        self.assertEqual(response_data["model"], "claude-returned")
        self.assertEqual(response_data["returned_model"], "claude-returned")
        self.assertEqual(response_data["response_id"], "msg_audit")
        self.assertEqual(response_data["usage"], {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "cache_read_tokens": 7,
            "cache_write_tokens": 5,
            "total_tokens": 28,
        })
        self.assertEqual(summary["status"], "success")
        serialized = json.dumps({"request": request_data, "response": response_data})
        self.assertNotIn("must-not-be-persisted", serialized)

    @patch("src.utils.judge_shim.request.urlopen")
    def test_legacy_call_audits_exception_before_task_can_swallow_it(
        self, urlopen: Mock
    ) -> None:
        urlopen.side_effect = RuntimeError("upstream unavailable")

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            client = judge_shim.OpenAI()
            with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
                client.chat.completions.create(
                    model="anthropic/claude-requested",
                    messages=[{"role": "user", "content": "grade"}],
                    response_format={"type": "json_object"},
                )
            response_data = json.loads(
                (Path(temp) / "attempt-001/response.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (Path(temp) / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(response_data["status"], "failed")
        self.assertIn("upstream unavailable", response_data["error"])
        self.assertEqual(summary["status"], "failed")

    @patch("src.utils.judge_shim.request.urlopen")
    def test_request_is_audited_before_network_call(self, urlopen: Mock) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            def fail_after_inspection(*args, **kwargs):
                request_path = Path(temp) / "attempt-001/request.json"
                response_path = Path(temp) / "attempt-001/response.json"
                self.assertTrue(request_path.exists())
                response_data = json.loads(response_path.read_text(encoding="utf-8"))
                self.assertEqual(response_data["status"], "in_progress")
                raise RuntimeError("upstream unavailable")

            urlopen.side_effect = fail_after_inspection
            with self.assertRaisesRegex(RuntimeError, "upstream unavailable"):
                judge_shim.OpenAI().chat.completions.create(
                    model="anthropic/claude-requested",
                    messages=[{"role": "user", "content": "grade"}],
                    response_format={"type": "json_object"},
                )

    @patch("src.utils.judge_shim.request.urlopen")
    def test_anthropic_model_override_is_recorded_as_effective_requested_model(
        self, urlopen: Mock
    ) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "id": "msg_override",
            "model": "claude-effective",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"score": 1}'}],
            "usage": {},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "ANTHROPIC_MODEL": "claude-effective",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            judge_shim.OpenAI().chat.completions.create(
                model="anthropic/claude-alias",
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
            )
            request_data = json.loads(
                (Path(temp) / "attempt-001/request.json").read_text(encoding="utf-8")
            )

        self.assertEqual(request_data["input_model"], "anthropic/claude-alias")
        self.assertEqual(request_data["requested_model"], "claude-effective")
        self.assertEqual(request_data["effective_requested_model"], "claude-effective")

    def test_legacy_openai_call_is_audited_without_persisting_client_credentials(self) -> None:
        usage = Mock(prompt_tokens=7, completion_tokens=3, total_tokens=10)
        choice = Mock(
            message=Mock(content='{"score": 1, "reason": "ok"}'),
            finish_reason="stop",
        )
        response = Mock(model="returned-model", choices=[choice], usage=usage)
        response.model_dump.return_value = {
            "model": "returned-model",
            "choices": [{"message": {"content": '{"score": 1, "reason": "ok"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
        real_client = Mock()
        real_client.chat.completions.create.return_value = response
        real_openai = Mock()
        real_openai.OpenAI.return_value = real_client

        with tempfile.TemporaryDirectory() as temp, patch.object(
            judge_shim, "_REAL_OPENAI", real_openai
        ), patch.dict("os.environ", {
            "OPENROUTER_BASE_URL": "https://openai.example.test/v2",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            client = judge_shim.OpenAI(
                api_key="must-not-be-persisted",
                base_url="https://openai.example.test/v2",
            )
            client.chat.completions.create(
                model="openai/requested-model",
                max_tokens=100,
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
            )
            request_data = json.loads(
                (Path(temp) / "attempt-001/request.json").read_text(encoding="utf-8")
            )
            response_data = json.loads(
                (Path(temp) / "attempt-001/response.json").read_text(encoding="utf-8")
            )

        self.assertEqual(request_data["endpoint_type"], "openai_chat_completions")
        self.assertEqual(
            request_data["endpoint"], "https://openai.example.test/v2/chat/completions"
        )
        self.assertEqual(response_data["model"], "returned-model")
        self.assertEqual(response_data["usage"]["total_tokens"], 10)
        serialized = json.dumps({"request": request_data, "response": response_data})
        self.assertNotIn("must-not-be-persisted", serialized)

    @patch("src.utils.judge_shim.request.urlopen")
    def test_non_json_anthropic_request_does_not_add_tools(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = b'{"content":[{"type":"text","text":"ok"}],"usage":{}}'
        urlopen.return_value.__enter__.return_value = response
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
        }):
            judge_shim._anthropic_create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "hello"}],
            )
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("tools", payload)

    @patch("src.utils.judge_shim.request.urlopen")
    def test_non_json_legacy_call_is_audited_without_schema_failure(
        self, urlopen: Mock
    ) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "model": "claude-test",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "plain text result"}],
            "usage": {},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            judge_shim.OpenAI().chat.completions.create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "grade"}],
            )
            parsed_data = json.loads(
                (Path(temp) / "attempt-001/parsed.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (Path(temp) / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(parsed_data["schema_status"], "not_requested")
        self.assertEqual(summary["status"], "success")

    @patch("src.utils.judge_shim.request.urlopen")
    def test_legacy_json_prompt_without_response_format_detects_parse_error(
        self, urlopen: Mock
    ) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "model": "claude-test",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "not valid json"}],
            "usage": {},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_AUDIT_DIR": temp,
        }):
            judge_shim.OpenAI().chat.completions.create(
                model="anthropic/claude-test",
                messages=[{
                    "role": "system",
                    "content": "Return ONLY a JSON object with score and reason.",
                }],
            )
            parsed_data = json.loads(
                (Path(temp) / "attempt-001/parsed.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (Path(temp) / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(parsed_data["schema_status"], "parse_error")
        self.assertEqual(summary["status"], "failed")

    def test_json_prompt_markers_cover_legacy_rubric_wording(self) -> None:
        for marker in (
            "Respond strictly in valid JSON with keys score and reason.",
            "Respond with exactly this JSON: {score: number, reason: string}.",
            "请严格使用 JSON 输出 score 和 reason。",
            "请仅返回合法 JSON，不要添加解释。",
        ):
            with self.subTest(marker=marker):
                self.assertTrue(
                    judge_shim._messages_expect_json([
                        {"role": "user", "content": marker}
                    ])
                )


if __name__ == "__main__":
    unittest.main()
