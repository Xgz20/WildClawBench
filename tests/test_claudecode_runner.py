from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.base import AgentTaskSpec
from src.agents.claudecode.runner import ClaudeCodeAgent


class ClaudeCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ClaudeCodeAgent(
            anthropic_api_key="test-key",
            anthropic_base_url="https://anthropic.example/v1",
        )

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


if __name__ == "__main__":
    unittest.main()
