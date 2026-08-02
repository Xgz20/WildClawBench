from __future__ import annotations

import json
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

    def read_trace_export_status(self, output_dir: Path) -> dict:
        status = json.loads(
            (output_dir / "execution_status.json").read_text(encoding="utf-8")
        )
        return status["trace_export"]

    def read_trace_export_event(self, output_dir: Path) -> dict:
        event = json.loads(
            (output_dir / "agent.log").read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(
            set(event),
            {
                "timestamp",
                "type",
                "enabled",
                "status",
                "archive",
                "trace_count",
                "error",
            },
        )
        self.assertEqual(event["type"], "runner.trace_export")
        return {key: event[key] for key in self.trace_export_field_names()}

    @staticmethod
    def trace_export_field_names() -> tuple[str, ...]:
        return ("enabled", "status", "archive", "trace_count", "error")

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
                self.make_agent()

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

    def test_task_env_cannot_override_reserved_trace_root(self) -> None:
        reserved_key = "CODEX_ROLLOUT_TRACE_ROOT"
        attacker_path = "/tmp/attacker-task-traces"
        declarations = (
            (reserved_key, {reserved_key: attacker_path}),
            (f"{reserved_key}={attacker_path}", {}),
        )
        for trace_value, (declaration, source_environment) in (
            (trace_value, declaration)
            for trace_value in (None, "0")
            for declaration in declarations
        ):
            environment = dict(source_environment)
            if trace_value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
            with self.subTest(
                trace_value=trace_value,
                declaration=declaration,
            ), patch.dict(
                os.environ,
                environment,
                clear=True,
            ), patch(
                "src.agents.astroncode.runner.subprocess.run"
            ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
                (Path(temp_dir) / "exec").mkdir()
                with self.assertRaisesRegex(ValueError, reserved_key):
                    self.make_agent()._start_container(
                        "task-env-collision-test",
                        temp_dir,
                        {"env": declaration},
                        None,
                    )

                run_mock.assert_not_called()
                self.assertNotIn(attacker_path, repr(run_mock.call_args_list))

    def test_lobster_env_cannot_override_reserved_trace_root(self) -> None:
        reserved_key = "CODEX_ROLLOUT_TRACE_ROOT"
        attacker_path = "/tmp/attacker-lobster-traces"
        declarations = (
            (reserved_key, {reserved_key: attacker_path}),
            (f"{reserved_key}={attacker_path}", {}),
        )
        for trace_value, (declaration, source_environment) in (
            (trace_value, declaration)
            for trace_value in (None, "0")
            for declaration in declarations
        ):
            environment = dict(source_environment)
            if trace_value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
            with self.subTest(
                trace_value=trace_value,
                declaration=declaration,
            ), patch.dict(
                os.environ,
                environment,
                clear=True,
            ), patch(
                "src.agents.astroncode.runner.subprocess.run"
            ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
                (Path(temp_dir) / "exec").mkdir()
                with self.assertRaisesRegex(ValueError, reserved_key):
                    self.make_agent()._start_container(
                        "lobster-env-collision-test",
                        temp_dir,
                        {},
                        {"env": [declaration]},
                    )

                run_mock.assert_not_called()
                self.assertNotIn(attacker_path, repr(run_mock.call_args_list))

    def test_enabled_workspace_preparation_creates_trace_root(self) -> None:
        command = self.prepare_workspace_command(None)

        self.assertIn(runner.ASTRONCODE_TRACE_ROOT, command)

    def test_disabled_workspace_preparation_omits_trace_root(self) -> None:
        command = self.prepare_workspace_command("0")

        self.assertNotIn(runner.ASTRONCODE_TRACE_ROOT, command)

    def test_trace_export_copies_one_archive_and_records_count(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            agent = self.make_agent()

            def fake_run(command, **kwargs):
                self.assertEqual(
                    kwargs["timeout"],
                    runner.ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
                )
                if command[:2] == ["docker", "exec"]:
                    archive_command = command[-1]
                    self.assertIn("-mindepth 1 -maxdepth 1", archive_command)
                    self.assertIn("-type d -name 'trace-*'", archive_command)
                    self.assertIn("tar -C /tmp -czf", archive_command)
                    self.assertIn("rollout-traces", archive_command)
                    return subprocess.CompletedProcess(command, 0, "3", "")
                if command[:2] == ["docker", "cp"]:
                    self.assertEqual(
                        command[2],
                        (
                            "trace-task:"
                            + runner.ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH
                        ),
                    )
                    Path(command[-1]).write_bytes(b"tar-gzip-content")
                    return subprocess.CompletedProcess(command, 0, "", "")
                self.fail(f"unexpected command: {command}")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ) as run_mock:
                agent._collect_rollout_trace_archive("trace-task", output_dir)

            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                {
                    "agent.log",
                    "execution_status.json",
                    runner.ASTRONCODE_TRACE_ARCHIVE_NAME,
                },
            )
            expected = {
                "enabled": True,
                "status": "exported",
                "archive": runner.ASTRONCODE_TRACE_ARCHIVE_NAME,
                "trace_count": 3,
                "error": None,
            }
            self.assertEqual(self.read_trace_export_status(output_dir), expected)
            self.assertEqual(self.read_trace_export_event(output_dir), expected)

    def test_collect_usage_triggers_trace_export_and_preserves_usage(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            agent = self.make_agent()
            parsed_usage = {
                "input_tokens": 11,
                "output_tokens": 7,
                "cache_read_tokens": 3,
                "cache_write_tokens": 2,
                "total_tokens": 18,
                "cost_usd": 1.25,
                "request_count": 4,
            }
            with patch.object(
                agent,
                "_collect_rollout_trace_archive",
            ) as export_mock, patch.object(
                agent,
                "_copy_dir_from_container",
            ), patch.object(
                agent,
                "_find_latest_session",
                return_value=None,
            ), patch.object(
                agent,
                "_extract_usage_from_jsonl",
                return_value=parsed_usage,
            ):
                usage = agent.collect_usage("trace-usage", output_dir, 1.5)

            export_mock.assert_called_once_with("trace-usage", output_dir)
            self.assertEqual(
                usage,
                {**parsed_usage, "elapsed_time": 1.5},
            )

    def test_disabled_trace_records_status_without_calling_docker(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "0"},
            clear=True,
        ), patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            self.make_agent()._collect_rollout_trace_archive(
                "disabled-trace",
                output_dir,
            )

            run_mock.assert_not_called()
            expected = {
                "enabled": False,
                "status": "disabled",
                "archive": None,
                "trace_count": 0,
                "error": None,
            }
            self.assertEqual(self.read_trace_export_status(output_dir), expected)
            self.assertEqual(self.read_trace_export_event(output_dir), expected)
            self.assertFalse(
                (output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME).exists()
            )

    def test_empty_trace_root_still_exports_archive(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "0", "")
                Path(command[-1]).write_bytes(b"empty-root-archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "empty-trace",
                    output_dir,
                )

            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "exported")
            self.assertEqual(status["trace_count"], 0)
            self.assertTrue(
                (output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME).is_file()
            )

    def test_trace_exec_failure_is_non_blocking_and_removes_partial_archive(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
            archive.write_bytes(b"stale-partial")
            failure = subprocess.CompletedProcess(
                [],
                1,
                "",
                "disk full " + "x" * 2000,
            )
            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                return_value=failure,
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "failed-trace",
                    output_dir,
                )

            self.assertFalse(archive.exists())
            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "failed")
            self.assertIn("archive command failed", status["error"])
            self.assertLessEqual(len(status["error"]), 1000)

    def test_trace_copy_failure_is_non_blocking_and_removes_partial_archive(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "1", "")
                archive.write_bytes(b"partial-copy")
                return subprocess.CompletedProcess(command, 1, "", "copy denied")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "copy-failed-trace",
                    output_dir,
                )

            self.assertFalse(archive.exists())
            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "failed")
            self.assertIn("archive copy failed", status["error"])

    def test_trace_chmod_failure_is_non_blocking_and_removes_archive(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "1", "")
                Path(command[-1]).write_bytes(b"archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ), patch.object(
                Path,
                "chmod",
                side_effect=PermissionError("chmod denied"),
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "chmod-failed-trace",
                    output_dir,
                )

            self.assertFalse(
                (output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME).exists()
            )
            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "failed")
            self.assertIn("chmod denied", status["error"])

    def test_trace_count_parse_failure_is_non_blocking_and_removes_archive(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "not-a-count", "")
                Path(command[-1]).write_bytes(b"archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "parse-failed-trace",
                    output_dir,
                )

            self.assertFalse(
                (output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME).exists()
            )
            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "failed")
            self.assertIn("not-a-count", status["error"])

    def test_trace_timeout_is_non_blocking_and_does_not_change_run_status(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            original_status = {
                "status": "timed_out",
                "exit_code": 124,
                "error": "model timed out",
            }
            (output_dir / "execution_status.json").write_text(
                json.dumps(original_status),
                encoding="utf-8",
            )
            timeout = subprocess.TimeoutExpired(
                ["docker", "exec"],
                runner.ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
            )
            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=timeout,
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "timeout-trace",
                    output_dir,
                )

            status_document = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            for key, value in original_status.items():
                self.assertEqual(status_document[key], value)
            self.assertEqual(status_document["trace_export"]["status"], "failed")

    def test_unexpected_trace_export_exception_does_not_affect_usage(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            agent = self.make_agent()
            parsed_usage = {
                "input_tokens": 5,
                "output_tokens": 4,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 9,
                "cost_usd": 0.5,
                "request_count": 1,
            }
            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=Exception("unexpected docker client failure"),
            ), patch.object(
                agent,
                "_copy_dir_from_container",
            ), patch.object(
                agent,
                "_find_latest_session",
                return_value=None,
            ), patch.object(
                agent,
                "_extract_usage_from_jsonl",
                return_value=parsed_usage,
            ), self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                usage = agent.collect_usage("exception-trace", output_dir, 2.0)

            self.assertEqual(usage, {**parsed_usage, "elapsed_time": 2.0})
            self.assertEqual(
                self.read_trace_export_status(output_dir)["status"],
                "failed",
            )


if __name__ == "__main__":
    unittest.main()
