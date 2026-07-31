from __future__ import annotations

import inspect
import unittest

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


if __name__ == "__main__":
    unittest.main()
