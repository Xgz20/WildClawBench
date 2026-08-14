from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from src.agents.base import AgentTaskSpec

from src.agents.deepseek_harness.runner import (
    DEFAULT_DSH_API,
    DEFAULT_IMAGE,
    DSH_SKILLS_DIR,
    PROMPT_PATH,
    DeepSeekHarnessAgent,
    append_agent_log_event,
    build_container_command,
    normalize_dsh_model_id,
    resolve_dsh_config,
    start_dsh_container,
    write_execution_status,
)


class DeepSeekHarnessConfigurationTests(unittest.TestCase):
    def test_normalize_dsh_model_id_removes_only_openrouter_prefix(self) -> None:
        self.assertEqual(normalize_dsh_model_id("openrouter/xopglm52"), "xopglm52")
        self.assertEqual(
            normalize_dsh_model_id("openrouter/anthropic/model"),
            "anthropic/model",
        )
        self.assertEqual(normalize_dsh_model_id("xopglm52"), "xopglm52")

    def test_resolve_config_prefers_arguments_then_environment_then_defaults(self) -> None:
        env = {
            "DOCKER_IMAGE_DEEPSEEK_HARNESS": "dsh:env",
            "OPENROUTER_API_KEY": "env-key",
            "OPENROUTER_BASE_URL": "https://env.example/v1",
            "DEEPSEEK_API_KEY": "search-key",
            "DSH_API": "openai-responses",
        }
        with patch.dict(os.environ, env, clear=True):
            from_env = resolve_dsh_config()
            explicit = resolve_dsh_config(
                image="dsh:test",
                openrouter_api_key="test-key",
                openrouter_base_url="https://maas.example/v2",
                deepseek_api_key="explicit-search-key",
                api="openai-completions",
            )

        self.assertEqual(from_env.image, "dsh:env")
        self.assertEqual(from_env.api, "openai-responses")
        self.assertEqual(from_env.openrouter_base_url, "https://env.example/v1")
        self.assertEqual(explicit.image, "dsh:test")
        self.assertEqual(explicit.openrouter_api_key, "test-key")
        self.assertEqual(explicit.openrouter_base_url, "https://maas.example/v2")
        self.assertEqual(explicit.deepseek_api_key, "explicit-search-key")
        self.assertEqual(explicit.api, "openai-completions")

        with patch.dict(os.environ, {}, clear=True):
            defaults = resolve_dsh_config()
        self.assertEqual(defaults.image, DEFAULT_IMAGE)
        self.assertEqual(defaults.api, DEFAULT_DSH_API)
        self.assertEqual(defaults.openrouter_base_url, "")

    def test_resolve_config_rejects_unsupported_api(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported DSH API"):
            resolve_dsh_config(api="openai-chat")

    def test_build_container_command_uses_detached_read_only_contract(self) -> None:
        config = resolve_dsh_config(
            image="dsh:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v2",
            deepseek_api_key="search-key",
            api="openai-completions",
        )
        with patch(
            "src.agents.deepseek_harness.runner.container_resource_args",
            return_value=["--memory", "4g", "--cpus", "2"],
        ):
            command = build_container_command(
                config,
                task_id="dsh-task",
                workspace_exec=Path("/tmp/task workspace/exec"),
                model="openrouter/xopglm52",
                thinking="high",
                task_env_names=("SLACK_TOKEN",),
                lobster_env_names=("LOBSTER_TOKEN",),
                environ={
                    "SLACK_TOKEN": "slack-secret",
                    "LOBSTER_TOKEN": "lobster-secret",
                    "HTTP_PROXY_INNER": "http://proxy:8080",
                    "HTTPS_PROXY_INNER": "http://proxy:8443",
                    "NO_PROXY_INNER": "localhost,127.0.0.1",
                },
            )

        self.assertEqual(command[:3], ["docker", "run", "-d"])
        self.assertIn("--entrypoint", command)
        self.assertEqual(command[command.index("--entrypoint") + 1], "/bin/bash")
        self.assertIn("--memory", command)
        self.assertIn("--cpus", command)
        resolved_workspace = Path("/tmp/task workspace/exec").resolve()
        self.assertIn(f"{resolved_workspace}:/mnt/wildclaw_src:ro", command)
        self.assertIn("DSH_MODEL_ID=xopglm52", command)
        self.assertIn("DSH_API=openai-completions", command)
        self.assertIn("DSH_REASONING=high", command)
        self.assertIn("OPENROUTER_API_KEY=test-key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://maas.example/v2", command)
        self.assertIn("DEEPSEEK_API_KEY=search-key", command)
        self.assertIn("SLACK_TOKEN=slack-secret", command)
        self.assertIn("LOBSTER_TOKEN=lobster-secret", command)
        self.assertEqual(command[-3:], ["/bin/bash", "-c", "tail -f /dev/null"])

    def test_build_container_command_omits_empty_optional_values(self) -> None:
        config = resolve_dsh_config(
            image="dsh:test",
            openrouter_api_key="test-key",
            openrouter_base_url="",
            deepseek_api_key="",
        )
        command = build_container_command(
            config,
            task_id="dsh-task",
            workspace_exec=Path("/work/exec"),
            model="xopglm52",
            environ={},
        )
        joined = "\n".join(command)

        self.assertNotIn("OPENROUTER_BASE_URL=", joined)
        self.assertNotIn("DEEPSEEK_API_KEY=", joined)
        self.assertNotIn("DSH_REASONING=", joined)

    def test_start_container_rejects_missing_key_before_docker(self) -> None:
        config = resolve_dsh_config(image="dsh:test", openrouter_api_key="")
        with patch("src.agents.deepseek_harness.runner.subprocess.run") as run_mock:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                start_dsh_container(
                    config,
                    task_id="dsh-task",
                    workspace_exec=Path("/work/exec"),
                    model="xopglm52",
                )
        run_mock.assert_not_called()

    def test_write_execution_status_updates_existing_json_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_execution_status(output_dir, status="starting", harness="deepseek-harness")
            result = write_execution_status(output_dir, status="running", api=DEFAULT_DSH_API)

            self.assertEqual(
                result,
                {
                    "status": "running",
                    "harness": "deepseek-harness",
                    "api": DEFAULT_DSH_API,
                },
            )
            self.assertEqual(
                json.loads((output_dir / "execution_status.json").read_text(encoding="utf-8")),
                result,
            )
            self.assertEqual(list(output_dir.glob(".execution_status.json.*.tmp")), [])

    def test_append_agent_log_event_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            append_agent_log_event(output_dir, {"event": "started", "secret": None})
            append_agent_log_event(output_dir, {"event": "finished", "exit_code": 0})

            rows = [
                json.loads(line)
                for line in (output_dir / "runner.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                rows,
                [
                    {"event": "started", "secret": None},
                    {"event": "finished", "exit_code": 0},
                ],
            )


class DeepSeekHarnessLifecycleTests(unittest.TestCase):
    def _spec(self, root: Path, *, thinking: str | None = "high") -> AgentTaskSpec:
        workspace = root / "workspace"
        (workspace / "exec").mkdir(parents=True)
        return AgentTaskSpec(
            task_id="dsh-task",
            task={
                "env": "SLACK_TOKEN\n",
                "skills": "slack\n",
                "skills_path": str(root / "skills"),
                "warmup": "echo ready",
            },
            workspace_path=str(workspace),
            prompt="Read messages; don't expose $(secrets).",
            timeout_seconds=30,
            output_dir=root / "output",
            model="openrouter/xopglm52",
            thinking=thinking,
            lobster={"env": ["LOBSTER_TOKEN"]},
        )

    def _agent(self, *, key: str = "test-key") -> DeepSeekHarnessAgent:
        return DeepSeekHarnessAgent(
            image="dsh:test",
            openrouter_api_key=key,
            openrouter_base_url="https://maas.example/v2",
            api="openai-completions",
        )

    def test_agent_properties_match_grading_contract(self) -> None:
        agent = self._agent()
        self.assertFalse(agent.expects_gateway)
        self.assertEqual(
            agent.transcript_container_path,
            "/root/.openclaw/agents/main/sessions/chat.jsonl",
        )

    def test_run_task_executes_lifecycle_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            events: list[str] = []

            with (
                patch.object(
                    agent,
                    "_start_container",
                    side_effect=lambda *_args, **_kwargs: events.append("start"),
                ) as start_mock,
                patch.object(
                    agent,
                    "_probe_harness_version",
                    side_effect=lambda *_args: events.append("version") or "0.1.0-rc.6",
                ),
                patch.object(
                    agent,
                    "_prepare_workspace",
                    side_effect=lambda *_args: events.append("workspace"),
                ),
                patch(
                    "src.agents.deepseek_harness.runner.setup_skills",
                    side_effect=lambda *_args, **_kwargs: events.append("skills"),
                ) as skills_mock,
                patch(
                    "src.agents.deepseek_harness.runner.run_warmup",
                    side_effect=lambda *_args, **_kwargs: events.append("warmup"),
                ) as warmup_mock,
                patch(
                    "src.agents.deepseek_harness.runner.snapshot_workspace_state",
                    side_effect=lambda *_args: events.append("snapshot"),
                ),
                patch.object(
                    agent,
                    "_copy_prompt",
                    side_effect=lambda *_args: events.append("prompt"),
                ),
                patch.object(
                    agent,
                    "_run_dsh",
                    side_effect=lambda *_args, **_kwargs: events.append("run")
                    or subprocess.CompletedProcess([], 0, "", ""),
                ),
                patch.object(
                    agent,
                    "_export_sessions",
                    side_effect=lambda *_args: events.append("export"),
                ),
            ):
                execution = agent.run_task(spec)

            self.assertIsNone(execution.error)
            self.assertEqual(
                events,
                [
                    "start",
                    "version",
                    "workspace",
                    "skills",
                    "warmup",
                    "snapshot",
                    "prompt",
                    "run",
                    "export",
                ],
            )
            start_mock.assert_called_once_with(
                "dsh-task",
                Path(spec.workspace_path) / "exec",
                spec,
            )
            skills_mock.assert_called_once_with(
                "dsh-task",
                "slack\n",
                str(Path(temp_dir) / "skills"),
                container_skills_root=DSH_SKILLS_DIR,
            )
            warmup_mock.assert_called_once_with(
                "dsh-task",
                "echo ready",
                detach_background=True,
            )
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "finished")
            self.assertEqual(status["harness"], "deepseek-harness")
            self.assertEqual(status["harness_version"], "0.1.0-rc.6")
            self.assertEqual(status["api"], "openai-completions")
            self.assertEqual(status["model"], "xopglm52")

    def test_run_task_returns_error_before_docker_when_key_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent(key="")
            with patch.object(agent, "_start_container") as start_mock:
                execution = agent.run_task(spec)

            self.assertIn("OPENROUTER_API_KEY", execution.error or "")
            start_mock.assert_not_called()
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "error")
            self.assertEqual(status["failure_stage"], "validating_configuration")

    def test_run_task_exports_sessions_after_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch("src.agents.deepseek_harness.runner.setup_skills"),
                patch("src.agents.deepseek_harness.runner.run_warmup"),
                patch("src.agents.deepseek_harness.runner.snapshot_workspace_state"),
                patch.object(agent, "_copy_prompt"),
                patch.object(
                    agent,
                    "_run_dsh",
                    return_value=subprocess.CompletedProcess([], 7, "", "failed"),
                ),
                patch.object(agent, "_export_sessions") as export_mock,
            ):
                execution = agent.run_task(spec)

            self.assertIn("rc=7", execution.error or "")
            export_mock.assert_called_once_with("dsh-task", spec.output_dir)
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["exit_code"], 7)
            self.assertEqual(status["failure_stage"], "running_harness")

    def test_run_task_reports_timeout_and_exports_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch("src.agents.deepseek_harness.runner.setup_skills"),
                patch("src.agents.deepseek_harness.runner.run_warmup"),
                patch("src.agents.deepseek_harness.runner.snapshot_workspace_state"),
                patch.object(agent, "_copy_prompt"),
                patch.object(
                    agent,
                    "_run_dsh",
                    side_effect=subprocess.TimeoutExpired(["docker", "exec"], 30),
                ),
                patch.object(agent, "_export_sessions") as export_mock,
            ):
                execution = agent.run_task(spec)

            self.assertEqual(execution.error, "DeepSeek Harness run timed out")
            self.assertEqual(execution.elapsed_time, 30.0)
            export_mock.assert_called_once_with("dsh-task", spec.output_dir)
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "timed_out")
            self.assertTrue(status["timed_out"])

    def test_exec_command_reads_prompt_file_without_prompt_text(self) -> None:
        command = self._agent()._build_exec_command()
        self.assertIn(PROMPT_PATH, command)
        self.assertIn("$(cat", command)
        self.assertNotIn("Read messages", command)

    def test_run_dsh_terminates_container_process_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            agent = self._agent()
            proc = MagicMock()
            proc.pid = 1234
            proc.wait.side_effect = [subprocess.TimeoutExpired(["docker", "exec"], 1), 0]

            with (
                patch("src.agents.deepseek_harness.runner.subprocess.Popen", return_value=proc),
                patch.object(agent, "_terminate_dsh_processes") as terminate_mock,
            ):
                with self.assertRaises(subprocess.TimeoutExpired):
                    agent._run_dsh("dsh-task", 1, output_dir)

            terminate_mock.assert_called_once_with("dsh-task")
            proc.kill.assert_called_once_with()
            self.assertEqual(proc.wait.call_args_list, [call(timeout=1), call(timeout=10)])

    def test_copy_prompt_uses_docker_cp_and_removes_host_temp_file(self) -> None:
        agent = self._agent()
        copied_host_paths: list[Path] = []

        def record_copy(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            copied_host_paths.append(Path(command[2]))
            self.assertEqual(command[3], f"dsh-task:{PROMPT_PATH}")
            self.assertEqual(Path(command[2]).read_text(encoding="utf-8"), "prompt text")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch(
            "src.agents.deepseek_harness.runner.subprocess.run",
            side_effect=record_copy,
        ):
            agent._copy_prompt("dsh-task", "prompt text")

        self.assertEqual(len(copied_host_paths), 1)
        self.assertFalse(copied_host_paths[0].exists())


if __name__ == "__main__":
    unittest.main()
