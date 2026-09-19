from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.base import AgentTaskSpec
from src.agents.minimax_code.runner import (
    DEFAULT_IMAGE,
    DEFAULT_MCODE_API,
    HOST_TIMEOUT_GRACE_SECONDS,
    MiniMaxCodeAgent,
    build_container_command,
    normalize_mcode_model_id,
    resolve_mcode_config,
    start_mcode_container,
)


FIXTURE = Path(__file__).parent / "fixtures" / "minimax_code" / "trace.jsonl"


class MiniMaxCodeConfigurationTests(unittest.TestCase):
    def test_config_precedence_and_model_normalization(self) -> None:
        env = {
            "DOCKER_IMAGE_MINIMAX_CODE": "mcode:env",
            "OPENROUTER_API_KEY": "env-key",
            "OPENROUTER_BASE_URL": "https://env.example/v1",
            "MCODE_API": "openai-responses",
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_mcode_config()

        self.assertEqual(config.image, "mcode:env")
        self.assertEqual(config.api, "openai-responses")
        self.assertEqual(config.openrouter_api_key, "env-key")
        self.assertEqual(config.openrouter_base_url, "https://env.example/v1")
        self.assertEqual(normalize_mcode_model_id("openrouter/xopglm52"), "xopglm52")
        self.assertEqual(normalize_mcode_model_id("vendor/model"), "vendor/model")

        with patch.dict(os.environ, {}, clear=True):
            defaults = resolve_mcode_config()
        self.assertEqual(defaults.image, DEFAULT_IMAGE)
        self.assertEqual(defaults.api, DEFAULT_MCODE_API)

    def test_config_rejects_unknown_api(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported MiniMax Code API"):
            resolve_mcode_config(api="openai-chat")

    def test_container_command_uses_detached_read_only_contract(self) -> None:
        config = resolve_mcode_config(
            image="mcode:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v1",
            api="openai-responses",
        )
        with patch(
            "src.agents.minimax_code.runner.container_resource_args",
            return_value=["--memory", "4g", "--cpus", "2"],
        ):
            command = build_container_command(
                config,
                task_id="mcode-task",
                workspace_exec=Path("/tmp/task workspace/exec"),
                model="openrouter/xopglm52",
                timeout_seconds=300,
                thinking="high",
                task_env_names=("SLACK_TOKEN",),
                environ={
                    "SLACK_TOKEN": "task-secret",
                    "WILDCLAW_MAAS_MAX_TOKENS_ENABLED": "true",
                    "MAAS_MAX_TOKENS": "16384",
                },
            )

        self.assertEqual(command[:3], ["docker", "run", "-d"])
        self.assertIn("MCODE_MODEL_ID=xopglm52", command)
        self.assertIn("MCODE_API=openai-responses", command)
        self.assertIn("MCODE_TIMEOUT_SECONDS=300", command)
        self.assertIn("MCODE_THINKING_REQUESTED=high", command)
        self.assertIn("MCODE_OUTPUT_LIMIT=16384", command)
        self.assertIn("OPENROUTER_API_KEY=test-key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://maas.example/v1", command)
        self.assertIn("SLACK_TOKEN=task-secret", command)
        self.assertIn(
            f"{Path('/tmp/task workspace/exec').resolve()}:/mnt/wildclaw_src:ro",
            command,
        )
        self.assertEqual(command[-3:], ["mcode:test", "-c", "tail -f /dev/null"])

    def test_start_container_rejects_missing_key_before_docker(self) -> None:
        config = resolve_mcode_config(image="mcode:test", openrouter_api_key="")
        with patch("src.agents.minimax_code.runner.subprocess.run") as run_mock:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                start_mcode_container(
                    config,
                    task_id="mcode-task",
                    workspace_exec=Path("/work/exec"),
                    model="xopglm52",
                    timeout_seconds=30,
                )
        run_mock.assert_not_called()


class MiniMaxCodeLifecycleTests(unittest.TestCase):
    @staticmethod
    def _spec(root: Path) -> AgentTaskSpec:
        workspace = root / "workspace"
        (workspace / "exec").mkdir(parents=True)
        return AgentTaskSpec(
            task_id="mcode-task",
            task={"skills": "slack", "skills_path": str(root / "skills"), "warmup": "echo ready"},
            workspace_path=str(workspace),
            prompt="Complete the task.",
            timeout_seconds=30,
            output_dir=root / "output",
            model="openrouter/xopglm52",
            thinking="high",
        )

    @staticmethod
    def _agent() -> MiniMaxCodeAgent:
        return MiniMaxCodeAgent(
            image="mcode:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v1",
            api="openai-responses",
        )

    def test_agent_contract_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            events: list[str] = []

            def run_mcode(*_args: object) -> subprocess.CompletedProcess[str]:
                events.append("run")
                shutil.copyfile(FIXTURE, spec.output_dir / "minimax_code_trace.jsonl")
                return subprocess.CompletedProcess([], 0, "", "")

            with (
                patch.object(agent, "_start_container", side_effect=lambda *_args: events.append("start")),
                patch.object(agent, "_probe_harness_version", return_value="0.4.12"),
                patch.object(agent, "_prepare_workspace", side_effect=lambda *_args: events.append("workspace")),
                patch("src.agents.minimax_code.runner.setup_skills", side_effect=lambda *_args, **_kwargs: events.append("skills")),
                patch("src.agents.minimax_code.runner.run_warmup", side_effect=lambda *_args, **_kwargs: events.append("warmup")),
                patch("src.agents.minimax_code.runner.snapshot_workspace_state", side_effect=lambda *_args: events.append("snapshot")),
                patch.object(agent, "_copy_prompt", side_effect=lambda *_args: events.append("prompt")),
                patch.object(agent, "_run_mcode", side_effect=run_mcode),
                patch.object(agent, "_export_artifacts", side_effect=lambda *_args, **_kwargs: events.append("export")),
            ):
                execution = agent.run_task(spec)

            self.assertIsNone(execution.error)
            self.assertFalse(agent.expects_gateway)
            self.assertEqual(
                agent.transcript_container_path,
                "/root/.openclaw/agents/main/sessions/chat.jsonl",
            )
            self.assertEqual(
                events,
                ["start", "workspace", "skills", "warmup", "snapshot", "prompt", "run", "export"],
            )
            status = json.loads(
                (spec.output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "finished")
            self.assertEqual(status["harness"], "minimax-code")
            self.assertEqual(status["harness_version"], "0.4.12")
            self.assertEqual(status["api"], "openai-responses")
            self.assertEqual(status["thinking_requested"], "high")
            self.assertFalse(status["thinking_forwarded"])

    def test_host_wait_includes_runtime_startup_grace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            proc = MagicMock()
            proc.wait.return_value = 0
            with patch("src.agents.minimax_code.runner.subprocess.Popen", return_value=proc):
                completed = self._agent()._run_mcode("mcode-task", 30, output_dir)

            self.assertEqual(completed.returncode, 0)
            proc.wait.assert_called_once_with(timeout=30 + HOST_TIMEOUT_GRACE_SECONDS)


if __name__ == "__main__":
    unittest.main()
