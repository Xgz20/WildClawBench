from __future__ import annotations

import os
import subprocess
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode import backend
from src.agents.astroncode.runner import AstronCodeAgent


REPO_ROOT = Path(__file__).resolve().parents[1]


class AstronCodeCliCommandTest(unittest.TestCase):
    def make_agent(self, cli_command: str | None = None) -> AstronCodeAgent:
        return AstronCodeAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.example/api/v1",
            cli_command=cli_command,
        )

    def test_defaults_to_production_cli_command(self) -> None:
        with patch.dict(os.environ, {"ASTRONCODE_CLI_COMMAND": ""}, clear=False):
            self.assertEqual("astron-code", self.make_agent().cli_command)

    def test_reads_test_cli_command_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_CLI_COMMAND": "astron-code-test"},
            clear=False,
        ):
            self.assertEqual("astron-code-test", self.make_agent().cli_command)

    def test_constructor_override_takes_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_CLI_COMMAND": "astron-code-test"},
            clear=False,
        ):
            self.assertEqual(
                "/opt/astron/astron-code-preview",
                self.make_agent("/opt/astron/astron-code-preview").cli_command,
            )

    def test_rejects_cli_command_with_arguments(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ASTRONCODE_CLI_COMMAND must be one executable name or path",
        ):
            self.make_agent("astron-code-test --preview")

    def test_runner_builds_exec_command_with_configured_cli(self) -> None:
        command = self.make_agent("astron-code-test")._build_exec_command(
            "/tmp/prompt.txt"
        )
        self.assertIn("astron-code-test exec", command)
        self.assertNotIn("astron-code exec", command)

    def test_version_probe_uses_configured_cli(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            "astron-code-test 0.0.35-test.1\n",
            "",
        )
        agent = self.make_agent("astron-code-test")
        with patch(
            "src.agents.astroncode.runner.subprocess.run",
            return_value=completed,
        ) as run:
            version = agent._probe_harness_version("astroncode-cli-test")

        self.assertEqual("0.0.35-test.1", version)
        run.assert_called_once_with(
            [
                "docker",
                "exec",
                "astroncode-cli-test",
                "astron-code-test",
                "--version",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_timeout_cleanup_uses_configured_cli_process_name(self) -> None:
        agent = self.make_agent("/opt/astron/astron-code-test")
        with patch(
            "src.agents.astroncode.runner.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run:
            agent._terminate_codex_processes("astroncode-cli-test")

        cleanup_command = run.call_args.args[0][-1]
        self.assertIn("pkill -TERM -f -- 'astron-code-test exec'", cleanup_command)
        self.assertIn("pkill -KILL -f -- 'astron-code-test exec'", cleanup_command)
        self.assertNotIn("'astron-code exec'", cleanup_command)

    def test_legacy_backend_uses_configured_cli(self) -> None:
        bootstrap = backend.build_codex_bootstrap_command(
            cli_command="astron-code-test"
        )
        command = backend.build_codex_exec_command(
            "openrouter/xopglm52",
            cli_command="astron-code-test",
        )

        self.assertIn("command -v astron-code-test", bootstrap)
        self.assertIn("astron-code-test exec", command)
        self.assertNotIn("astron-code exec", command)

    def test_legacy_backend_config_uses_top_level_native_web_search_mode(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_NATIVE_WEB_SEARCH_ENABLED": "0"},
            clear=False,
        ):
            config = tomllib.loads(
                backend.build_codex_config_toml(
                    "https://openrouter.example/api/v1",
                    "openrouter/xopglm52",
                )
            )

        self.assertEqual(config["web_search"], "disabled")
        self.assertNotIn("tools", config)

    def test_env_example_documents_production_default(self) -> None:
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ASTRONCODE_CLI_COMMAND=astron-code\n", env_example)
        self.assertIn("development builds use astron-code-dev", env_example)
        self.assertIn("Test builds can still set astron-code-test", env_example)


if __name__ == "__main__":
    unittest.main()
