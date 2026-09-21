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
from src.agents.zcode.runner import (
    DEFAULT_IMAGE,
    DEFAULT_ZCODE_API,
    HOST_TIMEOUT_GRACE_SECONDS,
    ZCodeAgent,
    build_container_command,
    normalize_zcode_model_id,
    resolve_zcode_config,
    start_zcode_container,
)


FIXTURE = Path(__file__).parent / "fixtures" / "zcode" / "trace.jsonl"


class ZCodeConfigurationTests(unittest.TestCase):
    def test_config_precedence_and_model_normalization(self) -> None:
        env = {
            "DOCKER_IMAGE_ZCODE": "zcode:env",
            "OPENROUTER_API_KEY": "env-key",
            "OPENROUTER_BASE_URL": "https://env.example/v1",
            "ZCODE_API": "openai-responses",
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_zcode_config()
        self.assertEqual(config.image, "zcode:env")
        self.assertEqual(config.api, "openai-responses")
        self.assertEqual(config.openrouter_api_key, "env-key")
        self.assertEqual(config.openrouter_base_url, "https://env.example/v1")
        self.assertEqual(normalize_zcode_model_id("openrouter/xopglm52"), "xopglm52")
        with patch.dict(os.environ, {}, clear=True):
            defaults = resolve_zcode_config()
        self.assertEqual(defaults.image, DEFAULT_IMAGE)
        self.assertEqual(defaults.api, DEFAULT_ZCODE_API)

    def test_config_rejects_unknown_api(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported ZCode API"):
            resolve_zcode_config(api="openai-completions")

    def test_container_command_uses_detached_contract(self) -> None:
        config = resolve_zcode_config(
            image="zcode:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v1",
            api="openai-responses",
        )
        with patch(
            "src.agents.zcode.runner.container_resource_args",
            return_value=["--memory", "4g", "--cpus", "2"],
        ):
            command = build_container_command(
                config,
                task_id="zcode-task",
                workspace_exec=Path("/tmp/task workspace/exec"),
                model="openrouter/xopglm52",
                timeout_seconds=300,
                thinking="high",
                task_env_names=("SLACK_TOKEN",),
                environ={"SLACK_TOKEN": "task-secret"},
            )
        self.assertEqual(command[:3], ["docker", "run", "-d"])
        self.assertIn("ZCODE_MODEL_ID=xopglm52", command)
        self.assertIn("ZCODE_API=openai-responses", command)
        self.assertIn("ZCODE_TIMEOUT_SECONDS=300", command)
        self.assertIn("ZCODE_THINKING_REQUESTED=high", command)
        self.assertIn("OPENROUTER_API_KEY=test-key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://maas.example/v1", command)
        self.assertIn("SLACK_TOKEN=task-secret", command)
        self.assertIn(
            f"{Path('/tmp/task workspace/exec').resolve()}:/mnt/wildclaw_src:ro",
            command,
        )
        self.assertEqual(command[-3:], ["zcode:test", "-c", "tail -f /dev/null"])

    def test_start_container_rejects_missing_endpoint_before_docker(self) -> None:
        config = resolve_zcode_config(
            image="zcode:test", openrouter_api_key="", openrouter_base_url=""
        )
        with patch("src.agents.zcode.runner.subprocess.run") as run_mock:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                start_zcode_container(
                    config,
                    task_id="zcode-task",
                    workspace_exec=Path("/work/exec"),
                    model="xopglm52",
                    timeout_seconds=30,
                )
        run_mock.assert_not_called()


class ZCodeLifecycleTests(unittest.TestCase):
    @staticmethod
    def _spec(root: Path) -> AgentTaskSpec:
        workspace = root / "workspace"
        (workspace / "exec").mkdir(parents=True)
        return AgentTaskSpec(
            task_id="zcode-task",
            task={"skills": "slack", "skills_path": str(root / "skills"), "warmup": "echo ready"},
            workspace_path=str(workspace),
            prompt="Complete the task.",
            timeout_seconds=30,
            output_dir=root / "output",
            model="openrouter/xopglm52",
            thinking="high",
        )

    @staticmethod
    def _agent() -> ZCodeAgent:
        return ZCodeAgent(
            image="zcode:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v1",
            api="openai-responses",
        )

    def test_agent_contract_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = self._spec(Path(temp_dir))
            agent = self._agent()
            events: list[str] = []

            def run_zcode(*_args: object) -> subprocess.CompletedProcess[str]:
                events.append("run")
                shutil.copyfile(FIXTURE, spec.output_dir / "zcode_trace.jsonl")
                return subprocess.CompletedProcess([], 0, "", "")

            with (
                patch.object(agent, "_start_container", side_effect=lambda *_args: events.append("start")),
                patch.object(agent, "_probe_harness_version", return_value="3.14.0"),
                patch.object(agent, "_prepare_workspace", side_effect=lambda *_args: events.append("workspace")),
                patch("src.agents.zcode.runner.setup_skills", side_effect=lambda *_args, **_kwargs: events.append("skills")),
                patch("src.agents.zcode.runner.run_warmup", side_effect=lambda *_args, **_kwargs: events.append("warmup")),
                patch("src.agents.zcode.runner.snapshot_workspace_state", side_effect=lambda *_args: events.append("snapshot")),
                patch.object(agent, "_copy_prompt", side_effect=lambda *_args: events.append("prompt")),
                patch.object(agent, "_run_zcode", side_effect=run_zcode),
                patch.object(agent, "_export_artifacts", side_effect=lambda *_args, **_kwargs: events.append("export")),
            ):
                execution = agent.run_task(spec)

            self.assertIsNone(execution.error)
            self.assertFalse(agent.expects_gateway)
            self.assertEqual(
                events,
                ["start", "workspace", "skills", "warmup", "snapshot", "prompt", "run", "export"],
            )
            status = json.loads((spec.output_dir / "execution_status.json").read_text())
            self.assertEqual(status["status"], "finished")
            self.assertEqual(status["harness"], "zcode")
            self.assertEqual(status["harness_version"], "3.14.0")
            self.assertEqual(status["api"], "openai-responses")
            self.assertFalse(status["thinking_forwarded"])

    def test_host_wait_includes_runtime_startup_grace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            proc = MagicMock()
            proc.wait.return_value = 0
            with patch("src.agents.zcode.runner.subprocess.Popen", return_value=proc):
                completed = self._agent()._run_zcode("zcode-task", 30, Path(temp_dir))
        self.assertEqual(completed.returncode, 0)
        proc.wait.assert_called_once_with(timeout=30 + HOST_TIMEOUT_GRACE_SECONDS)


if __name__ == "__main__":
    unittest.main()
