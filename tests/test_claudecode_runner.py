from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.base import AgentTaskSpec
from src.agents.claudecode.runner import ClaudeCodeAgent, write_execution_status
from src.utils.anomalies import scan_run_dir


class ClaudeCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ClaudeCodeAgent(
            anthropic_api_key="test-key",
            anthropic_base_url="https://anthropic.example/v1",
        )

    def test_default_image_uses_formal_patched_tag(self) -> None:
        with patch.dict(
            os.environ,
            {"DOCKER_IMAGE_CLAUDECODE": "", "CLAUDECODE_DOCKER_IMAGE": ""},
        ):
            agent = ClaudeCodeAgent()

        self.assertEqual(
            agent.image,
            "wildclawbench-claudecode-ubuntu:v0.2-patched",
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
            run.return_value.stdout = "2.1.233\n"
            run.return_value.stderr = ""

            version = self.agent._probe_harness_version("claudecode-version-test")

        self.assertEqual(version, "2.1.233")
        run.assert_called_once_with(
            [
                "docker",
                "exec",
                "claudecode-version-test",
                "node",
                "-p",
                "require('/claude_code/package.json').version",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_maas_model_injects_common_output_limit_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"MAAS_MAX_TOKENS": "3072"}, clear=False
        ), patch("src.agents.claudecode.runner.subprocess.run") as run:
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
