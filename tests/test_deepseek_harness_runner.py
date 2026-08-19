from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

from src.agents.base import AgentTaskSpec
from src.agents.deepseek_harness.transcript import DshSessionFormatError

from src.agents.deepseek_harness.runner import (
    DEFAULT_DSH_API,
    DEFAULT_IMAGE,
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
                    "DEEPSEEK_SEARCH_BASE_URL": "https://search.example/anthropic/v1",
                    "DEEPSEEK_SEARCH_MODEL_ID": "deepseek-search-model",
                    "DEEPSEEK_SEARCH_ENABLED": "false",
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
        self.assertIn("DSH_MAX_TOKENS=4096", command)
        self.assertIn("OPENROUTER_API_KEY=test-key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://maas.example/v2", command)
        self.assertIn("DEEPSEEK_API_KEY=search-key", command)
        self.assertIn(
            "DEEPSEEK_SEARCH_BASE_URL=https://search.example/anthropic/v1",
            command,
        )
        self.assertIn("DEEPSEEK_SEARCH_MODEL_ID=deepseek-search-model", command)
        self.assertIn("DEEPSEEK_SEARCH_ENABLED=false", command)
        self.assertIn("SLACK_TOKEN=slack-secret", command)
        self.assertIn("LOBSTER_TOKEN=lobster-secret", command)
        image_index = command.index("dsh:test")
        self.assertEqual(command[image_index + 1 :], ["-c", "tail -f /dev/null"])

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
        self.assertNotIn("DEEPSEEK_SEARCH_BASE_URL=", joined)
        self.assertNotIn("DEEPSEEK_SEARCH_MODEL_ID=", joined)
        self.assertNotIn("DEEPSEEK_SEARCH_ENABLED=", joined)
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
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    side_effect=lambda *_args, **_kwargs: events.append("skills")
                    or ["03-task2"],
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
                ) as prompt_mock,
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
                on_missing=ANY,
            )
            prompt_mock.assert_called_once_with(
                "dsh-task",
                "/03-task2\n\nRead messages; don't expose $(secrets).",
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

    def test_run_task_attributes_host_exec_directory_failure_to_workspace_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            exec_path = Path(spec.workspace_path) / "exec"
            exec_path.rmdir()
            exec_path.write_text("not a directory", encoding="utf-8")
            agent = self._agent()

            with patch.object(agent, "_start_container") as start_mock:
                execution = agent.run_task(spec)

            self.assertIsNotNone(execution.error)
            start_mock.assert_not_called()
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["failure_stage"], "preparing_workspace")

    def test_run_task_reports_skill_preparation_failure_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    side_effect=RuntimeError("skill preparation failed"),
                ),
                patch.object(agent, "_export_sessions"),
            ):
                execution = agent.run_task(spec)

            self.assertIn("skill preparation failed", execution.error or "")
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["failure_stage"], "preparing_skills")

    def test_run_task_reports_warmup_preparation_failure_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    return_value=["slack"],
                ),
                patch(
                    "src.agents.deepseek_harness.runner.run_warmup",
                    side_effect=RuntimeError("warmup preparation failed"),
                ),
                patch.object(agent, "_export_sessions"),
            ):
                execution = agent.run_task(spec)

            self.assertIn("warmup preparation failed", execution.error or "")
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["failure_stage"], "preparing_warmup")

    def test_run_task_reports_workspace_snapshot_failure_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    return_value=["slack"],
                ),
                patch("src.agents.deepseek_harness.runner.run_warmup"),
                patch(
                    "src.agents.deepseek_harness.runner.snapshot_workspace_state",
                    side_effect=RuntimeError("workspace snapshot failed"),
                ),
                patch.object(agent, "_export_sessions"),
            ):
                execution = agent.run_task(spec)

            self.assertIn("workspace snapshot failed", execution.error or "")
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["failure_stage"], "snapshotting_workspace")

    def test_run_task_records_missing_skills_in_execution_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()

            def install_with_missing(*_args: object, on_missing: object) -> list[str]:
                assert callable(on_missing)
                on_missing("edge-tts")
                return ["slack"]

            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    side_effect=install_with_missing,
                ),
                patch("src.agents.deepseek_harness.runner.run_warmup"),
                patch("src.agents.deepseek_harness.runner.snapshot_workspace_state"),
                patch.object(agent, "_copy_prompt"),
                patch.object(
                    agent,
                    "_run_dsh",
                    return_value=subprocess.CompletedProcess([], 0, "", ""),
                ),
                patch.object(agent, "_export_sessions"),
            ):
                execution = agent.run_task(spec)

            self.assertIsNone(execution.error)
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["missing_skills"], ["edge-tts"])

    def test_run_task_persists_missing_skill_before_later_skill_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()

            def install_with_missing_then_error(*_args: object, on_missing: object) -> list[str]:
                assert callable(on_missing)
                on_missing("edge-tts")
                raise ValueError("invalid YAML frontmatter")

            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    side_effect=install_with_missing_then_error,
                ),
                patch.object(agent, "_export_sessions"),
            ):
                execution = agent.run_task(spec)

            self.assertIn("invalid YAML frontmatter", execution.error or "")
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["missing_skills"], ["edge-tts"])
            events = [
                json.loads(line)
                for line in (spec.output_dir / "runner.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("type") == "runner.skill_missing"
                    and event.get("skills") == ["edge-tts"]
                    for event in events
                )
            )

    def test_run_task_exports_sessions_after_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    return_value=[],
                ),
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
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    return_value=[],
                ),
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

    def test_prepare_workspace_copies_task_tmp_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            task_tmp = workspace / "tmp"
            task_tmp.mkdir(parents=True)
            (task_tmp / "messages.json").write_text("[]", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, "", "")

            with patch(
                "src.agents.deepseek_harness.runner.subprocess.run",
                return_value=completed,
            ) as run_mock:
                self._agent()._prepare_workspace("dsh-task", workspace)

            self.assertEqual(run_mock.call_count, 3)
            self.assertEqual(
                run_mock.call_args_list[1].args[0],
                ["docker", "exec", "dsh-task", "mkdir", "-p", "/tmp_workspace/tmp"],
            )
            self.assertEqual(
                run_mock.call_args_list[2].args[0],
                [
                    "docker",
                    "cp",
                    f"{task_tmp}/.",
                    "dsh-task:/tmp_workspace/tmp/",
                ],
            )


class DeepSeekHarnessArtifactTests(unittest.TestCase):
    FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "deepseek_harness"

    def _agent(self) -> DeepSeekHarnessAgent:
        return DeepSeekHarnessAgent(
            image="dsh:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v2",
        )

    def test_export_sessions_preserves_raw_converts_and_installs_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            commands: list[list[str]] = []

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[:2] == ["docker", "cp"] and command[2].endswith(
                    ":/root/.dsh/sessions/."
                ):
                    shutil.copytree(
                        self.FIXTURE_ROOT,
                        Path(command[3]),
                        dirs_exist_ok=True,
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.deepseek_harness.runner.subprocess.run",
                side_effect=fake_run,
            ):
                self._agent()._export_sessions("dsh-task", output_dir)

            self.assertTrue((output_dir / "dsh_sessions" / "session.jsonl").is_file())
            self.assertTrue(
                (output_dir / "dsh_sessions" / "child" / "session.jsonl").is_file()
            )
            self.assertTrue((output_dir / "chat.jsonl").is_file())
            self.assertTrue((output_dir / "usage.json").is_file())
            self.assertTrue((output_dir / "conversion_manifest.json").is_file())
            self.assertIn(
                [
                    "docker",
                    "exec",
                    "dsh-task",
                    "mkdir",
                    "-p",
                    "/root/.openclaw/agents/main/sessions",
                ],
                commands,
            )
            self.assertIn(
                [
                    "docker",
                    "cp",
                    str(output_dir / "chat.jsonl"),
                    "dsh-task:/root/.openclaw/agents/main/sessions/chat.jsonl",
                ],
                commands,
            )

    def test_collect_usage_reads_conversion_output_and_sets_elapsed_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            shutil.copytree(self.FIXTURE_ROOT, output_dir / "dsh_sessions")
            from src.agents.deepseek_harness.transcript import write_conversion

            write_conversion(output_dir / "dsh_sessions", output_dir)

            usage = self._agent().collect_usage("dsh-task", output_dir, 12.5)

            self.assertEqual(
                usage,
                {
                    "input_tokens": 18,
                    "output_tokens": 7,
                    "cache_read_tokens": 2,
                    "cache_write_tokens": 4,
                    "total_tokens": 31,
                    "cost_usd": 0.0,
                    "request_count": 3,
                    "elapsed_time": 12.5,
                    "cost_status": "unavailable",
                    "cost_source": "none",
                    "cost_scope": "model_tokens_only",
                    "cost_reason": "DSH sessions expose token usage but not provider cost; calculate cost from the model pricing registry when generating the report",
                },
            )

    def test_collect_usage_returns_zero_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            usage = self._agent().collect_usage("dsh-task", Path(temp_dir), 3.456)

        self.assertEqual(usage["request_count"], 0)
        self.assertEqual(usage["total_tokens"], 0)
        self.assertEqual(usage["cost_usd"], 0.0)
        self.assertEqual(usage["cost_status"], "not_applicable")
        self.assertEqual(usage["elapsed_time"], 3.46)

    def test_export_conversion_failure_preserves_raw_session_and_zero_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["docker", "cp"] and command[2].endswith(
                    ":/root/.dsh/sessions/."
                ):
                    destination = Path(command[3])
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "session.jsonl").write_text(
                        "{not-json}\n",
                        encoding="utf-8",
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.deepseek_harness.runner.subprocess.run",
                side_effect=fake_run,
            ):
                with self.assertRaises(DshSessionFormatError):
                    self._agent()._export_sessions("dsh-task", output_dir)

            self.assertEqual(
                (output_dir / "dsh_sessions" / "session.jsonl").read_text(
                    encoding="utf-8"
                ),
                "{not-json}\n",
            )
            usage = json.loads((output_dir / "usage.json").read_text(encoding="utf-8"))
            self.assertEqual(usage["request_count"], 0)
            self.assertEqual(usage["total_tokens"], 0)
            self.assertEqual(usage["cost_status"], "unavailable")

    def test_run_task_surfaces_conversion_failure_when_harness_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            (workspace / "exec").mkdir(parents=True)
            spec = AgentTaskSpec(
                task_id="dsh-task",
                task={},
                workspace_path=str(workspace),
                prompt="Do the task",
                timeout_seconds=30,
                output_dir=root / "output",
                model="openrouter/xopglm52",
            )
            agent = self._agent()
            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_probe_harness_version", return_value="0.1.0-rc.6"),
                patch.object(agent, "_prepare_workspace"),
                patch(
                    "src.agents.deepseek_harness.runner.install_dsh_skills",
                    return_value=[],
                ),
                patch("src.agents.deepseek_harness.runner.run_warmup"),
                patch("src.agents.deepseek_harness.runner.snapshot_workspace_state"),
                patch.object(agent, "_copy_prompt"),
                patch.object(
                    agent,
                    "_run_dsh",
                    return_value=subprocess.CompletedProcess([], 0, "", ""),
                ),
                patch.object(
                    agent,
                    "_export_sessions",
                    side_effect=DshSessionFormatError("invalid session"),
                ),
            ):
                execution = agent.run_task(spec)

            self.assertEqual(
                execution.error,
                "DeepSeek Harness session export failed: invalid session",
            )
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["failure_stage"], "exporting_sessions")


if __name__ == "__main__":
    unittest.main()
