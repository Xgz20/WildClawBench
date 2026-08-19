from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.base import AgentTaskSpec
from src.agents.opencode.runner import OpenCodeAgent


class OpenCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = OpenCodeAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.example/api/v1",
        )

    def test_build_exec_command_maps_thinking_to_variant(self) -> None:
        parameters = inspect.signature(self.agent._build_exec_command).parameters
        self.assertIn("thinking", parameters)

        command = self.agent._build_exec_command(
            model="openrouter/gpt-5.5",
            prompt_path="/tmp/prompt.txt",
            config_content="{}",
            thinking="high",
        )

        self.assertIn("--variant high", command)
        self.assertNotIn(" --thinking", command)

    def test_build_exec_command_omits_empty_variant(self) -> None:
        for thinking in (None, "", "   "):
            with self.subTest(thinking=thinking):
                command = self.agent._build_exec_command(
                    model="openrouter/gpt-5.5",
                    prompt_path="/tmp/prompt.txt",
                    config_content="{}",
                    thinking=thinking,
                )
                self.assertNotIn("--variant", command)

    def test_build_exec_command_shell_quotes_variant(self) -> None:
        command = self.agent._build_exec_command(
            model="openrouter/gpt-5.5",
            prompt_path="/tmp/prompt.txt",
            config_content="{}",
            thinking="high; echo injected",
        )

        self.assertIn("--variant 'high; echo injected'", command)

    def test_maas_model_config_uses_common_output_limit(self) -> None:
        agent = OpenCodeAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas-api.example/v1",
        )
        with patch.dict("os.environ", {"MAAS_MAX_TOKENS": "3072"}, clear=False):
            config = json.loads(
                agent._render_opencode_config(
                    "openrouter/xopglm52", redact_secrets=True
                )
            )

        model = config["provider"]["openrouter"]["models"]["xopglm52"]
        self.assertEqual(model["limit"]["output"], 3072)

    def test_run_task_forwards_thinking_to_prompt_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace_path = temp_path / "workspace"
            output_dir = temp_path / "output"
            workspace_path.mkdir()
            spec = AgentTaskSpec(
                task_id="opencode-thinking-test",
                task={},
                workspace_path=str(workspace_path),
                prompt="test prompt",
                timeout_seconds=30,
                output_dir=output_dir,
                model="openrouter/gpt-5.5",
                thinking="high",
            )

            with (
                patch.object(self.agent, "_start_container"),
                patch.object(
                    self.agent, "_probe_harness_version", return_value="test"
                ),
                patch.object(self.agent, "_prepare_workspace"),
                patch("src.agents.opencode.runner.setup_skills"),
                patch(
                    "src.agents.opencode.runner.load_skill_documents",
                    return_value=[],
                ),
                patch("src.agents.opencode.runner.run_warmup"),
                patch.object(
                    self.agent, "_should_enable_image_helper", return_value=False
                ),
                patch("src.agents.opencode.runner.snapshot_workspace_state"),
                patch.object(
                    self.agent, "_build_task_prompt", return_value="prepared prompt"
                ),
                patch.object(self.agent, "_run_prompt") as run_prompt,
                patch.object(self.agent, "_install_openclaw_transcript_shim"),
            ):
                execution = self.agent.run_task(spec)

            self.assertIsNone(execution.error)
            run_prompt.assert_called_once_with(
                task_id="opencode-thinking-test",
                model="openrouter/gpt-5.5",
                prompt="prepared prompt",
                timeout_seconds=30,
                output_dir=output_dir,
                thinking="high",
            )


if __name__ == "__main__":
    unittest.main()
