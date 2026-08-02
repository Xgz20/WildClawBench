from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode import runner
from src.agents.astroncode.runner import AstronCodeAgent


class AstronCodeTraceTests(unittest.TestCase):
    def make_agent(self) -> AstronCodeAgent:
        return AstronCodeAgent(
            openrouter_api_key="openrouter-key",
            openrouter_base_url="https://openrouter.example/api/v1",
        )

    def start_container_call(self, trace_value: str | None):
        environment = {}
        if trace_value is not None:
            environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
        with patch.dict(os.environ, environment, clear=True), patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
            run_mock.return_value = subprocess.CompletedProcess(
                [], 0, "container-id", ""
            )
            (Path(temp_dir) / "exec").mkdir()
            self.make_agent()._start_container(
                "trace-env-test",
                temp_dir,
                {},
                None,
            )
            return run_mock.call_args

    def prepare_workspace_command(self, trace_value: str | None) -> str:
        environment = {}
        if trace_value is not None:
            environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
        with patch.dict(os.environ, environment, clear=True), patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
            run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
            self.make_agent()._prepare_workspace("trace-root-test", temp_dir)
            return run_mock.call_args_list[0].args[0][-1]

    def test_trace_constants_match_export_contract(self) -> None:
        self.assertEqual(runner.ASTRONCODE_TRACE_ROOT, "/tmp/rollout-traces")
        self.assertEqual(
            runner.ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH,
            "/tmp/astroncode_traces.tar.gz",
        )
        self.assertEqual(
            runner.ASTRONCODE_TRACE_ARCHIVE_NAME,
            "astroncode_traces.tar.gz",
        )
        self.assertEqual(runner.ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS, 300)

    def test_parse_env_flag_uses_default_for_blank_and_accepts_true_values(
        self,
    ) -> None:
        for value in (None, "", "   ", "1", "true", "TRUE", "yes", "YES", "on", "ON"):
            environment = {}
            if value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = value
            with self.subTest(value=value), patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                self.assertIs(
                    runner.parse_env_flag(
                        "ASTRONCODE_TRACE_ENABLED",
                        default=True,
                    ),
                    True,
                )

    def test_parse_env_flag_accepts_false_values(self) -> None:
        for value in ("0", "false", "FALSE", "no", "NO", "off", "OFF"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"ASTRONCODE_TRACE_ENABLED": value},
                clear=True,
            ):
                self.assertIs(
                    runner.parse_env_flag(
                        "ASTRONCODE_TRACE_ENABLED",
                        default=True,
                    ),
                    False,
                )

    def test_invalid_trace_flag_names_setting_and_accepted_values(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "sometimes"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                (
                    "ASTRONCODE_TRACE_ENABLED.*1.*true.*yes.*on.*"
                    "0.*false.*no.*off"
                ),
            ):
                runner.parse_env_flag(
                    "ASTRONCODE_TRACE_ENABLED",
                    default=True,
                )

    def test_construction_snapshots_trace_setting(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "0"},
            clear=True,
        ):
            agent = self.make_agent()

        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "1"},
            clear=True,
        ):
            self.assertIs(agent.trace_enabled, False)

    def test_default_trace_is_injected_without_inline_docker_value(self) -> None:
        run_call = self.start_container_call(None)
        command = run_call.args[0]
        child_environment = run_call.kwargs["env"]

        trace_env_index = command.index("CODEX_ROLLOUT_TRACE_ROOT")
        self.assertEqual(command[trace_env_index - 1], "-e")
        self.assertEqual(
            child_environment["CODEX_ROLLOUT_TRACE_ROOT"],
            runner.ASTRONCODE_TRACE_ROOT,
        )
        for argument in command:
            self.assertNotIn(runner.ASTRONCODE_TRACE_ROOT, argument)
            self.assertNotIn("CODEX_ROLLOUT_TRACE_ROOT=", argument)

    def test_disabled_trace_is_absent_from_docker_environment(self) -> None:
        run_call = self.start_container_call("0")

        self.assertNotIn("CODEX_ROLLOUT_TRACE_ROOT", run_call.args[0])
        self.assertNotIn(
            "CODEX_ROLLOUT_TRACE_ROOT",
            run_call.kwargs["env"],
        )

    def test_enabled_workspace_preparation_creates_trace_root(self) -> None:
        command = self.prepare_workspace_command(None)

        self.assertIn(runner.ASTRONCODE_TRACE_ROOT, command)

    def test_disabled_workspace_preparation_omits_trace_root(self) -> None:
        command = self.prepare_workspace_command("0")

        self.assertNotIn(runner.ASTRONCODE_TRACE_ROOT, command)


if __name__ == "__main__":
    unittest.main()
