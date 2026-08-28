from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.base import AgentTaskSpec
from src.agents.claudecode.runner import ClaudeCodeAgent, write_execution_status
from src.utils.anomalies import scan_run_dir
from src.utils.log_format import ColorEmojiFormatter, EmojiFormatter


class ClaudeCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ClaudeCodeAgent(
            anthropic_api_key="test-key",
            anthropic_base_url="https://anthropic.example/v1",
        )

    def test_default_image_uses_official_global_cli_tag(self) -> None:
        with patch.dict(
            os.environ,
            {"DOCKER_IMAGE_CLAUDECODE": "", "CLAUDECODE_DOCKER_IMAGE": ""},
        ):
            agent = ClaudeCodeAgent()

        self.assertEqual(
            agent.image,
            "wildclawbench-claudecode-ubuntu:v0.3",
        )

    def test_image_override_precedence_remains_compatible(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DOCKER_IMAGE_CLAUDECODE": "primary:image",
                "CLAUDECODE_DOCKER_IMAGE": "legacy:image",
            },
        ):
            self.assertEqual(ClaudeCodeAgent().image, "primary:image")
            self.assertEqual(
                ClaudeCodeAgent(image="explicit:image").image,
                "explicit:image",
            )

        with patch.dict(
            os.environ,
            {
                "DOCKER_IMAGE_CLAUDECODE": "",
                "CLAUDECODE_DOCKER_IMAGE": "legacy:image",
            },
        ):
            self.assertEqual(ClaudeCodeAgent().image, "legacy:image")

    def test_build_prompt_command_maps_thinking_to_effort(self) -> None:
        command = self.agent._build_prompt_command(
            prompt="test prompt",
            model="claude-sonnet",
            thinking="high",
        )

        self.assertIn("--effort high", command)
        self.assertNotIn("--thinking", command)
        self.assertIn("command -v claude", command)
        self.assertIn("--output-format stream-json", command)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertIn("tee /claude_code/log/chat.json", command)
        self.assertIn("/claude_code/start.sh", command)

    def test_build_prompt_command_omits_empty_effort(self) -> None:
        for thinking in (None, "", "   "):
            with self.subTest(thinking=thinking):
                command = self.agent._build_prompt_command(
                    prompt="test prompt",
                    model="claude-sonnet",
                    thinking=thinking,
                )
                self.assertNotIn("--effort", command)

    def test_build_prompt_command_shell_quotes_effort(self) -> None:
        command = self.agent._build_prompt_command(
            prompt="test prompt",
            model="claude-sonnet",
            thinking="high; echo injected",
        )

        self.assertIn("--effort 'high; echo injected'", command)

    def test_probe_harness_version_reads_claudecode_package_metadata(self) -> None:
        with patch("src.agents.claudecode.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "2.1.250 (Claude Code)\n"
            run.return_value.stderr = ""

            version = self.agent._probe_harness_version("claudecode-version-test")

        self.assertEqual(version, "2.1.250")
        run.assert_called_once_with(
            [
                "docker",
                "exec",
                "claudecode-version-test",
                "/bin/bash",
                "-lc",
                (
                    "if command -v claude >/dev/null 2>&1; then "
                    "claude --version; "
                    "elif [ -f /claude_code/package.json ]; then "
                    "node -p \"require('/claude_code/package.json').version\"; "
                    "else exit 127; fi"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_maas_model_injects_common_output_limit_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"MAAS_MAX_TOKENS": "3072"}, clear=False
        ), patch("src.agents.claudecode.runner.subprocess.run") as run, self.assertLogs(
            "src.agents.claudecode.runner", level="INFO"
        ) as logs:
            run.return_value = subprocess.CompletedProcess([], 0, "container-id", "")
            agent = ClaudeCodeAgent(
                anthropic_api_key="test-key",
                anthropic_base_url="https://maas-api.example/anthropic",
            )

            agent._start_container("claudecode-maas", temp_dir, "xopglm52")

        command = next(
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:2] == ["docker", "run"]
        )
        self.assertIn("CLAUDE_CODE_MAX_OUTPUT_TOKENS=3072", command)
        self.assertIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", command)
        self.assertIn("DISABLE_AUTOUPDATER=1", command)
        messages = "\n".join(logs.output)
        self.assertIn("Starting ClaudeCode container", messages)
        self.assertIn("Container ID: container-id", messages)

    def test_run_task_forwards_thinking_to_prompt_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace_path = temp_path / "workspace"
            output_dir = temp_path / "output"
            workspace_path.mkdir()
            spec = AgentTaskSpec(
                task_id="claudecode-thinking-test",
                task={},
                workspace_path=str(workspace_path),
                prompt="test prompt",
                timeout_seconds=30,
                output_dir=output_dir,
                model="claude-sonnet",
                thinking="high",
            )

            with (
                patch.object(self.agent, "_start_container"),
                patch.object(self.agent, "_probe_harness_version", return_value="test-version"),
                patch.object(self.agent, "_prepare_workspace"),
                patch("src.agents.claudecode.runner.setup_skills"),
                patch("src.agents.claudecode.runner.run_warmup"),
                patch("src.agents.claudecode.runner.snapshot_workspace_state"),
                patch.object(self.agent, "_run_prompt") as run_prompt,
            ):
                execution = self.agent.run_task(spec)

            self.assertIsNone(execution.error)
            run_prompt.assert_called_once_with(
                "claudecode-thinking-test",
                "test prompt",
                "claude-sonnet",
                30,
                output_dir,
                thinking="high",
            )
            status = json.loads((output_dir / "execution_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "finished")
            self.assertEqual(status["harness"], "claudecode")
            self.assertEqual(status["harness_version"], "test-version")
            self.assertEqual(status["exit_code"], 0)

    def test_run_prompt_streams_output_and_logs_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            process = MagicMock()
            process.pid = 1234
            process.returncode = 0
            process.wait.return_value = 0

            with patch(
                "src.agents.claudecode.runner.subprocess.Popen",
                return_value=process,
            ) as popen, self.assertLogs(
                "src.agents.claudecode.runner", level="INFO"
            ) as logs:
                self.agent._run_prompt(
                    "claudecode-progress-test",
                    "test prompt",
                    "claude-sonnet",
                    30,
                    output_dir,
                    thinking="high",
                )

            command = popen.call_args.args[0]
            self.assertEqual(command[:3], ["docker", "exec", "claudecode-progress-test"])
            self.assertIs(popen.call_args.kwargs["stderr"], subprocess.STDOUT)
            self.assertNotIn("capture_output", popen.call_args.kwargs)
            process.wait.assert_called_once()
            messages = "\n".join(logs.output)
            self.assertIn("Started ClaudeCode process PID=1234", messages)
            self.assertIn("Waiting for ClaudeCode to finish", messages)
            self.assertIn("ClaudeCode finished successfully", messages)
            self.assertIn("ClaudeCode exit code: 0", messages)

    def test_run_prompt_logs_periodic_progress_while_process_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            process = MagicMock()
            process.pid = 5678
            process.returncode = 0
            process.wait.side_effect = [
                subprocess.TimeoutExpired("docker exec", 1),
                0,
            ]

            with patch.dict(
                os.environ,
                {"WILDCLAW_PROGRESS_LOG_INTERVAL_SECONDS": "1"},
            ), patch(
                "src.agents.claudecode.runner.subprocess.Popen",
                return_value=process,
            ), self.assertLogs(
                "src.agents.claudecode.runner", level="INFO"
            ) as logs:
                self.agent._run_prompt(
                    "claudecode-heartbeat-test",
                    "test prompt",
                    "claude-sonnet",
                    30,
                    output_dir,
                )

            messages = "\n".join(logs.output)
            self.assertIn("ClaudeCode still running", messages)
            self.assertIn("agent.log:", messages)
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "claudecode_running")
            self.assertEqual(status["pid"], 5678)

    def test_run_prompt_terminates_process_after_total_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            process = MagicMock()
            process.pid = 9012
            process.wait.side_effect = subprocess.TimeoutExpired("docker exec", 1)

            with patch.dict(
                os.environ,
                {"WILDCLAW_PROGRESS_LOG_INTERVAL_SECONDS": "1"},
            ), patch(
                "src.agents.claudecode.runner.subprocess.Popen",
                return_value=process,
            ), patch(
                "src.agents.claudecode.runner.time.perf_counter",
                side_effect=[100.0, 100.0, 102.0],
            ), patch.object(
                self.agent,
                "_terminate_prompt_process",
            ) as terminate:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.agent._run_prompt(
                        "claudecode-timeout-process-test",
                        "test prompt",
                        "claude-sonnet",
                        1,
                        output_dir,
                    )

            terminate.assert_called_once_with(
                "claudecode-timeout-process-test",
                process,
            )

    def test_progress_log_has_console_highlight_and_file_emoji(self) -> None:
        record = logging.LogRecord(
            name="src.agents.claudecode.runner",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="[task] ClaudeCode still running, elapsed: 30s/3600s",
            args=(),
            exc_info=None,
        )

        file_line = EmojiFormatter().format(record)
        console_line = ColorEmojiFormatter().format(record)

        self.assertIn("⏳", file_line)
        self.assertNotIn("\033[", file_line)
        self.assertIn("⏳", console_line)
        self.assertIn("\033[", console_line)

    def test_collect_usage_exports_transcript_and_counts_model_requests(self) -> None:
        chat_rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        {"type": "user", "message": {"role": "user", "content": "task"}}
                    ]
                },
            },
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        {"type": "user", "message": {"role": "user", "content": "task"}},
                        {
                            "type": "assistant",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": "working"}],
                            },
                        },
                    ]
                },
            },
            {
                "event": "query_end",
                "payload": {
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 5,
                        "cost_details": {"upstream_inference_cost": 0.25},
                    }
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "run"

            def copy_file(_task_id: str, src: str, dest: Path) -> None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.endswith("chat.json"):
                    dest.write_text(
                        "\n".join(json.dumps(row) for row in chat_rows) + "\n",
                        encoding="utf-8",
                    )
                else:
                    dest.write_text("{}", encoding="utf-8")

            with (
                patch.object(self.agent, "_copy_file_from_container", side_effect=copy_file),
                patch.object(self.agent, "_copy_dir_from_container"),
            ):
                usage = self.agent.collect_usage("claudecode-test", output_dir, 12.3)

            self.assertEqual(usage["request_count"], 2)
            self.assertEqual(usage["input_tokens"], 20)
            self.assertEqual(usage["output_tokens"], 5)
            self.assertTrue((output_dir / "chat.jsonl").is_file())
            self.assertGreater((output_dir / "chat.jsonl").stat().st_size, 0)

            write_execution_status(
                output_dir,
                status="finished",
                harness="claudecode",
                model="claude-test",
                timed_out=False,
                elapsed_time=12.3,
            )
            (output_dir / "usage.json").write_text(json.dumps(usage), encoding="utf-8")
            (output_dir / "score.json").write_text(
                json.dumps({"overall_score": 1.0}), encoding="utf-8"
            )
            report = scan_run_dir(output_dir)
            self.assertNotIn("EMPTY_TRANSCRIPT", {item["id"] for item in report["items"]})

    def test_collect_usage_reads_official_stream_json_result(self) -> None:
        chat_rows = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "task"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {"input_tokens": 12, "output_tokens": 4},
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "num_turns": 3,
                "total_cost_usd": 0.42,
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 30,
                    "cache_creation_input_tokens": 10,
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "run"

            def copy_file(_task_id: str, _src: str, dest: Path) -> None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(
                    "\n".join(json.dumps(row) for row in chat_rows) + "\n",
                    encoding="utf-8",
                )

            with (
                patch.object(self.agent, "_copy_file_from_container", side_effect=copy_file),
                patch.object(self.agent, "_copy_dir_from_container"),
            ):
                usage = self.agent.collect_usage("claudecode-official", output_dir, 9.5)

        self.assertEqual(usage["input_tokens"], 120)
        self.assertEqual(usage["output_tokens"], 40)
        self.assertEqual(usage["cache_read_tokens"], 30)
        self.assertEqual(usage["cache_write_tokens"], 10)
        self.assertEqual(usage["total_tokens"], 200)
        self.assertEqual(usage["cost_usd"], 0.42)
        self.assertEqual(usage["request_count"], 1)
        self.assertEqual(usage["usage_source"], "official_result")
        self.assertTrue(usage["usage_complete"])

    def test_chat_usage_deduplicates_assistant_stream_fragments(self) -> None:
        chat_rows = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [{"type": "text", "text": "working"}],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 30,
                        "cache_creation_input_tokens": 4,
                        "cost_details": {"upstream_inference_cost": 0.1},
                    },
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-1",
                            "name": "Bash",
                            "input": {"command": "pwd"},
                        }
                    ],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "cache_read_input_tokens": 30,
                        "cache_creation_input_tokens": 4,
                        "cost_details": {"upstream_inference_cost": 0.1},
                    },
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-2",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 5,
                        "cache_read_input_tokens": 40,
                        "cache_creation_input_tokens": 6,
                        "cost_details": {"upstream_inference_cost": 0.2},
                    },
                },
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            chat_path = Path(temp_dir) / "chat.json"
            chat_path.write_text(
                "\n".join(json.dumps(row) for row in chat_rows) + "\n",
                encoding="utf-8",
            )

            usage = self.agent._extract_usage_from_chat_json(chat_path)

        self.assertEqual(usage["input_tokens"], 32)
        self.assertEqual(usage["output_tokens"], 9)
        self.assertEqual(usage["cache_read_tokens"], 70)
        self.assertEqual(usage["cache_write_tokens"], 10)
        self.assertEqual(usage["total_tokens"], 121)
        self.assertEqual(usage["cost_usd"], 0.3)
        self.assertEqual(usage["request_count"], 2)
        self.assertEqual(usage["usage_source"], "assistant_message_fallback")
        self.assertFalse(usage["usage_complete"])

    def test_request_count_deduplicates_official_assistant_fragments(self) -> None:
        rows = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [{"type": "text", "text": "working"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-1",
                            "name": "Bash",
                            "input": {"command": "pwd"},
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-final",
                    "content": [{"type": "text", "text": "done"}],
                },
            },
            {"type": "result", "num_turns": 26},
        ]

        self.assertEqual(self.agent._request_count_from_rows(rows), 2)

    def test_request_count_prefers_model_usage_request_count(self) -> None:
        rows = [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "id": "assistant-1",
                    "content": [{"type": "text", "text": "done"}],
                },
            },
            {
                "type": "result",
                "num_turns": 26,
                "modelUsage": {
                    "claude-test": {
                        "requestCount": 4,
                    }
                },
            },
        ]

        self.assertEqual(self.agent._request_count_from_rows(rows), 4)

    def test_run_task_records_timeout_status_and_failure_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_path = root / "workspace"
            output_dir = root / "output"
            workspace_path.mkdir()
            spec = AgentTaskSpec(
                task_id="claudecode-timeout-test",
                task={},
                workspace_path=str(workspace_path),
                prompt="test prompt",
                timeout_seconds=30,
                output_dir=output_dir,
                model="claude-sonnet",
            )

            with (
                patch.object(self.agent, "_start_container"),
                patch.object(self.agent, "_probe_harness_version", return_value="test-version"),
                patch.object(self.agent, "_prepare_workspace"),
                patch("src.agents.claudecode.runner.setup_skills"),
                patch("src.agents.claudecode.runner.run_warmup"),
                patch("src.agents.claudecode.runner.snapshot_workspace_state"),
                patch.object(
                    self.agent,
                    "_run_prompt",
                    side_effect=subprocess.TimeoutExpired("claude", 30),
                ),
            ):
                execution = self.agent.run_task(spec)

            self.assertEqual(execution.error, "ClaudeCode run timed out")
            status = json.loads((output_dir / "execution_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "timed_out")
            self.assertTrue(status["timed_out"])
            self.assertEqual(status["failure_stage"], "claudecode_running")

    def test_run_task_records_error_status_and_failure_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_path = root / "workspace"
            output_dir = root / "output"
            workspace_path.mkdir()
            spec = AgentTaskSpec(
                task_id="claudecode-error-test",
                task={},
                workspace_path=str(workspace_path),
                prompt="test prompt",
                timeout_seconds=30,
                output_dir=output_dir,
                model="claude-sonnet",
            )

            with patch.object(
                self.agent,
                "_start_container",
                side_effect=RuntimeError("container failed"),
            ):
                execution = self.agent.run_task(spec)

            self.assertEqual(execution.error, "container failed")
            status = json.loads((output_dir / "execution_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "error")
            self.assertEqual(status["failure_stage"], "starting_container")
            self.assertEqual(status["error"], "container failed")


if __name__ == "__main__":
    unittest.main()
