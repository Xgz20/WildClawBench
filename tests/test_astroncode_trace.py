from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval import run_batch
from src.agents.base import AgentExecution
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
                "interaction_jsonl",
                "error",
            },
        )
        self.assertEqual(event["type"], "runner.trace_export")
        return {key: event[key] for key in self.trace_export_field_names()}

    @staticmethod
    def trace_export_field_names() -> tuple[str, ...]:
        return (
            "enabled",
            "status",
            "archive",
            "trace_count",
            "interaction_jsonl",
            "error",
        )

    @staticmethod
    def write_trace_archive(path: Path, trace_names: tuple[str, ...]) -> None:
        with tarfile.open(path, "w:gz") as archive:
            if not trace_names:
                root = tarfile.TarInfo("rollout-traces")
                root.type = tarfile.DIRTYPE
                archive.addfile(root)
                return
            for trace_name in trace_names:
                prefix = f"rollout-traces/{trace_name}"
                manifest = json.dumps({"trace_id": trace_name}).encode()
                manifest_info = tarfile.TarInfo(f"{prefix}/manifest.json")
                manifest_info.size = len(manifest)
                archive.addfile(manifest_info, io.BytesIO(manifest))
                trace = json.dumps(
                    {
                        "seq": 1,
                        "wall_time_unix_ms": 1,
                        "payload": {"type": "rollout_started"},
                    }
                ).encode() + b"\n"
                trace_info = tarfile.TarInfo(f"{prefix}/trace.jsonl")
                trace_info.size = len(trace)
                archive.addfile(trace_info, io.BytesIO(trace))

    def collect_usage_with_parsed_usage(
        self,
        agent: AstronCodeAgent,
        task_id: str,
        output_dir: Path,
    ) -> dict:
        parsed_usage = {
            "input_tokens": 5,
            "output_tokens": 4,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 9,
            "cost_usd": 0.5,
            "request_count": 1,
        }
        with patch.object(
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
            usage = agent.collect_usage(task_id, output_dir, 2.0)
        self.assertEqual(usage, {**parsed_usage, "elapsed_time": 2.0})
        return usage

    def run_export_with_real_shell(
        self,
        agent: AstronCodeAgent,
        task_id: str,
        trace_root: Path,
        container_archive: Path,
        output_dir: Path,
        *,
        shell_environment: dict[str, str] | None = None,
    ) -> list[list[str]]:
        real_run = subprocess.run
        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["docker", "exec"]:
                if shell_environment is not None:
                    kwargs["env"] = shell_environment
                return real_run(command[3:], **kwargs)
            if command[:2] == ["docker", "cp"]:
                shutil.copyfile(container_archive, Path(command[-1]))
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected command: {command}")

        with patch.object(
            runner,
            "ASTRONCODE_TRACE_ROOT",
            str(trace_root),
        ), patch.object(
            runner,
            "ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH",
            str(container_archive),
        ), patch(
            "src.agents.astroncode.runner.subprocess.run",
            side_effect=fake_run,
        ):
            agent._collect_rollout_trace_archive(task_id, output_dir)
        return commands

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
                    self.assertNotIn("find ", archive_command)
                    self.assertNotIn("wc -l", archive_command)
                    self.assertIn(
                        "for trace_dir in /tmp/rollout-traces/trace-*",
                        archive_command,
                    )
                    self.assertIn('[ -d "$trace_dir" ]', archive_command)
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
                    self.write_trace_archive(
                        Path(command[-1]),
                        ("trace-one", "trace-two", "trace-three"),
                    )
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
                    runner.ASTRONCODE_INTERACTION_JSONL_NAME,
                },
            )
            expected = {
                "enabled": True,
                "status": "exported",
                "archive": runner.ASTRONCODE_TRACE_ARCHIVE_NAME,
                "trace_count": 3,
                "interaction_jsonl": runner.ASTRONCODE_INTERACTION_JSONL_NAME,
                "error": None,
            }
            self.assertEqual(self.read_trace_export_status(output_dir), expected)
            self.assertEqual(self.read_trace_export_event(output_dir), expected)

    def test_interaction_jsonl_reconstructs_user_model_tool_and_final_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            archive_path = base_dir / "traces.tar.gz"
            output_path = base_dir / runner.ASTRONCODE_INTERACTION_JSONL_NAME
            prefix = "rollout-traces/trace-one"

            with tarfile.open(archive_path, "w:gz") as archive:
                def add_json(name: str, value: object) -> None:
                    content = json.dumps(value).encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))

                add_json(f"{prefix}/manifest.json", {"trace_id": "trace-one"})
                add_json(
                    f"{prefix}/payloads/1.json",
                    {
                        "input": [{"role": "user", "content": "hello"}],
                        "model": "xopglm52",
                    },
                )
                add_json(
                    f"{prefix}/payloads/2.json",
                    {"tool_name": "exec_command", "payload": {"cmd": "echo hi"}},
                )
                add_json(
                    f"{prefix}/payloads/3.json",
                    {
                        "call_id": "call-1",
                        "stdout": "hi\n",
                        "stderr": "",
                        "exit_code": 0,
                        "duration": 1.25,
                    },
                )
                add_json(
                    f"{prefix}/payloads/4.json",
                    {
                        "output_items": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"text": "done"}],
                            }
                        ],
                        "token_usage": {"total_tokens": 3},
                    },
                )
                trace_events = [
                    {
                        "seq": 1,
                        "wall_time_unix_ms": 1,
                        "payload": {"type": "rollout_started"},
                    },
                    {
                        "seq": 2,
                        "wall_time_unix_ms": 2,
                        "thread_id": "thread-1",
                        "payload": {
                            "type": "inference_started",
                            "inference_call_id": "inference-1",
                            "request_payload": {
                                "path": "payloads/1.json",
                                "kind": {"type": "inference_request"},
                            },
                        },
                    },
                    {
                        "seq": 3,
                        "wall_time_unix_ms": 3,
                        "payload": {
                            "type": "tool_call_started",
                            "tool_call_id": "call-1",
                            "invocation_payload": {
                                "path": "payloads/2.json",
                                "kind": {"type": "tool_invocation"},
                            },
                        },
                    },
                    {
                        "seq": 4,
                        "wall_time_unix_ms": 4,
                        "payload": {
                            "type": "tool_call_runtime_ended",
                            "tool_call_id": "call-1",
                            "runtime_payload": {
                                "path": "payloads/3.json",
                                "kind": {"type": "tool_runtime_event"},
                            },
                        },
                    },
                    {
                        "seq": 5,
                        "wall_time_unix_ms": 5,
                        "payload": {
                            "type": "inference_completed",
                            "inference_call_id": "inference-1",
                            "response_id": "response-1",
                            "response_payload": {
                                "path": "payloads/4.json",
                                "kind": {"type": "inference_response"},
                            },
                        },
                    },
                ]
                trace_content = "".join(
                    json.dumps(event) + "\n" for event in trace_events
                ).encode()
                trace_info = tarfile.TarInfo(f"{prefix}/trace.jsonl")
                trace_info.size = len(trace_content)
                archive.addfile(trace_info, io.BytesIO(trace_content))

            runner.AstronCodeAgent._export_agent_interaction_jsonl(
                archive_path,
                output_path,
            )
            records = [json.loads(line) for line in output_path.read_text().splitlines()]
            by_type = {record["record_type"]: record for record in records}
            self.assertEqual(by_type["user_input"]["user_items"][0]["content"], "hello")
            self.assertEqual(
                by_type["model_request"]["raw_payloads"]["request_payload"]["data"]["model"],
                "xopglm52",
            )
            self.assertEqual(
                by_type["tool_call_runtime_ended"]["raw_payloads"]["runtime_payload"]["data"]["stdout"],
                "hi\n",
            )
            self.assertEqual(
                by_type["tool_call_runtime_ended"]["raw_payloads"]["runtime_payload"]["data"]["duration"],
                1.25,
            )
            self.assertEqual(by_type["final_output"]["text"], "done")
            self.assertEqual(output_path.stat().st_mode & 0o777, 0o600)

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
                "interaction_jsonl": None,
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
                self.write_trace_archive(Path(command[-1]), ())
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
            self.assertTrue(
                (output_dir / runner.ASTRONCODE_INTERACTION_JSONL_NAME).is_file()
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

    def test_trace_recording_failures_are_independent_and_non_blocking(self) -> None:
        outcomes = ("disabled", "exported", "failed")
        recorders = ("write_execution_status", "append_agent_log_event")
        for outcome in outcomes:
            for failing_recorder in recorders:
                environment = (
                    {"ASTRONCODE_TRACE_ENABLED": "0"}
                    if outcome == "disabled"
                    else {}
                )
                with self.subTest(
                    outcome=outcome,
                    failing_recorder=failing_recorder,
                ), patch.dict(
                    os.environ,
                    environment,
                    clear=True,
                ), tempfile.TemporaryDirectory() as temp_dir:
                    output_dir = Path(temp_dir)
                    original_status = {
                        "status": "timed_out",
                        "exit_code": 124,
                        "error": "model timed out",
                    }
                    status_path = output_dir / "execution_status.json"
                    status_path.write_text(
                        json.dumps(original_status),
                        encoding="utf-8",
                    )
                    agent = self.make_agent()

                    def fake_run(command, **kwargs):
                        if outcome == "failed":
                            return subprocess.CompletedProcess(
                                command,
                                1,
                                "",
                                "archive unavailable",
                            )
                        if command[:2] == ["docker", "exec"]:
                            return subprocess.CompletedProcess(command, 0, "1", "")
                        self.write_trace_archive(Path(command[-1]), ("trace-one",))
                        return subprocess.CompletedProcess(command, 0, "", "")

                    recorder_patch = patch(
                        f"src.agents.astroncode.runner.{failing_recorder}",
                        side_effect=OSError(f"{failing_recorder} denied"),
                    )
                    with patch(
                        "src.agents.astroncode.runner.subprocess.run",
                        side_effect=fake_run,
                    ), recorder_patch as recorder_mock, self.assertLogs(
                        "src.agents.astroncode.runner",
                        level="WARNING",
                    ):
                        self.collect_usage_with_parsed_usage(
                            agent,
                            f"record-{outcome}",
                            output_dir,
                        )

                    recorder_mock.assert_called_once()
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    for key, value in original_status.items():
                        self.assertEqual(status[key], value)
                    if failing_recorder == "write_execution_status":
                        self.assertNotIn("trace_export", status)
                        event = self.read_trace_export_event(output_dir)
                        self.assertEqual(event["status"], outcome)
                    else:
                        self.assertEqual(status["trace_export"]["status"], outcome)

    def test_execution_status_atomic_failures_preserve_original_bytes(self) -> None:
        class PartialWriteFile:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return self.wrapped.__exit__(exc_type, exc, traceback)

            def __getattr__(self, name):
                return getattr(self.wrapped, name)

            def write(self, content):
                self.wrapped.write(content[: max(1, len(content) // 2)])
                self.wrapped.flush()
                raise OSError("temporary status write failed")

        real_fdopen = os.fdopen
        for failure_boundary in (
            "temporary-write",
            "mode-apply",
            "fsync",
            "replace",
        ):
            with self.subTest(failure_boundary=failure_boundary), patch.dict(
                os.environ,
                {"ASTRONCODE_TRACE_ENABLED": "0"},
                clear=True,
            ), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                status_path = output_dir / "execution_status.json"
                original_bytes = (
                    b'{"status":"timed_out","exit_code":124,'
                    b'"error":"model timed out"}\n'
                )
                status_path.write_bytes(original_bytes)
                agent = self.make_agent()

                if failure_boundary == "temporary-write":
                    def partial_fdopen(file_descriptor, *args, **kwargs):
                        return PartialWriteFile(
                            real_fdopen(file_descriptor, *args, **kwargs)
                        )

                    failure_patch = patch(
                        "src.agents.astroncode.runner.os.fdopen",
                        side_effect=partial_fdopen,
                    )
                elif failure_boundary == "mode-apply":
                    failure_patch = patch(
                        "src.agents.astroncode.runner.os.fchmod",
                        side_effect=PermissionError("status mode apply failed"),
                    )
                elif failure_boundary == "fsync":
                    failure_patch = patch(
                        "src.agents.astroncode.runner.os.fsync",
                        side_effect=OSError("status fsync failed"),
                    )
                else:
                    failure_patch = patch(
                        "src.agents.astroncode.runner.os.replace",
                        side_effect=OSError("status replace failed"),
                    )

                with failure_patch, self.assertLogs(
                    "src.agents.astroncode.runner",
                    level="WARNING",
                ):
                    self.collect_usage_with_parsed_usage(
                        agent,
                        f"atomic-{failure_boundary}",
                        output_dir,
                    )

                self.assertEqual(status_path.read_bytes(), original_bytes)
                self.assertEqual(json.loads(original_bytes)["status"], "timed_out")
                self.assertEqual(
                    list(output_dir.glob(".execution_status.json.*.tmp")),
                    [],
                )

    def test_new_execution_status_matches_path_write_text_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            baseline_path = output_dir / "write-text-baseline.json"
            baseline_path.write_text("{}", encoding="utf-8")
            baseline_mode = stat.S_IMODE(baseline_path.stat().st_mode)

            runner.write_execution_status(output_dir, status="created")

            status_path = output_dir / "execution_status.json"
            self.assertEqual(
                stat.S_IMODE(status_path.stat().st_mode),
                baseline_mode,
            )

    def test_existing_execution_status_preserves_mode_and_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            status_path = output_dir / "execution_status.json"
            status_path.write_text(
                json.dumps({"status": "created", "task_id": "mode-test"}),
                encoding="utf-8",
            )
            status_path.chmod(0o640)
            historical_mtime_ns = 946684800_000_000_000
            os.utime(
                status_path,
                ns=(historical_mtime_ns, historical_mtime_ns),
            )
            original_stat = status_path.stat()

            runner.write_execution_status(output_dir, status="finished")

            updated_stat = status_path.stat()
            self.assertEqual(stat.S_IMODE(updated_stat.st_mode), 0o640)
            self.assertEqual(updated_stat.st_uid, original_stat.st_uid)
            self.assertEqual(updated_stat.st_gid, original_stat.st_gid)
            self.assertNotEqual(updated_stat.st_mtime_ns, historical_mtime_ns)

    def test_execution_status_atomic_success_merges_existing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            status_path = output_dir / "execution_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "preparing_workspace",
                        "task_id": "merge-status",
                        "exit_code": None,
                        "error": None,
                    }
                ),
                encoding="utf-8",
            )

            merged = runner.write_execution_status(
                output_dir,
                status="error",
                error="workspace preparation failed",
            )

            on_disk = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, merged)
            self.assertEqual(on_disk["task_id"], "merge-status")
            self.assertIsNone(on_disk["exit_code"])
            self.assertEqual(on_disk["status"], "error")
            self.assertEqual(on_disk["failure_stage"], "preparing_workspace")
            self.assertEqual(
                list(output_dir.glob(".execution_status.json.*.tmp")),
                [],
            )

    def test_real_shell_exports_all_trace_files_in_one_secure_archive(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            container_dir = base_dir / "container-tmp"
            trace_root = container_dir / "rollout-traces"
            output_dir = base_dir / "output"
            output_dir.mkdir()
            for trace_name in ("trace-one", "trace-two"):
                trace_dir = trace_root / trace_name
                trace_dir.mkdir(parents=True)
                (trace_dir / "manifest.json").write_text(
                    json.dumps({"trace": trace_name}),
                    encoding="utf-8",
                )
                (trace_dir / "trace.jsonl").write_text(
                    json.dumps({"event": trace_name}) + "\n",
                    encoding="utf-8",
                )
            (trace_root / "trace-file").write_text("not a directory", encoding="utf-8")
            nested_trace = trace_root / "not-a-trace" / "trace-nested"
            nested_trace.mkdir(parents=True)
            (trace_root / "trace-link").symlink_to(
                trace_root / "trace-one",
                target_is_directory=True,
            )
            container_archive = container_dir / "astroncode_traces.tar.gz"

            commands = self.run_export_with_real_shell(
                self.make_agent(),
                "real-shell-traces",
                trace_root,
                container_archive,
                output_dir,
            )

            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
            with tarfile.open(archive, "r:gz") as tar_file:
                members = {member.name.rstrip("/") for member in tar_file.getmembers()}
            self.assertIn("rollout-traces", members)
            for trace_name in ("trace-one", "trace-two"):
                self.assertIn(f"rollout-traces/{trace_name}/manifest.json", members)
                self.assertIn(f"rollout-traces/{trace_name}/trace.jsonl", members)
            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                {
                    runner.ASTRONCODE_TRACE_ARCHIVE_NAME,
                    runner.ASTRONCODE_INTERACTION_JSONL_NAME,
                    "execution_status.json",
                    "agent.log",
                },
            )
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.read_trace_export_status(output_dir)["trace_count"], 2)
            self.assertEqual([command[:2] for command in commands].count(["docker", "cp"]), 1)

    def test_real_shell_exports_a_valid_empty_trace_archive(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            container_dir = base_dir / "container-tmp"
            container_dir.mkdir()
            trace_root = container_dir / "rollout-traces"
            output_dir = base_dir / "output"
            output_dir.mkdir()
            container_archive = container_dir / "astroncode_traces.tar.gz"

            self.run_export_with_real_shell(
                self.make_agent(),
                "real-shell-empty",
                trace_root,
                container_archive,
                output_dir,
            )

            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
            with tarfile.open(archive, "r:gz") as tar_file:
                members = {member.name.rstrip("/") for member in tar_file.getmembers()}
            self.assertEqual(members, {"rollout-traces"})
            self.assertEqual(self.read_trace_export_status(output_dir)["trace_count"], 0)
            self.assertTrue(
                (output_dir / runner.ASTRONCODE_INTERACTION_JSONL_NAME).is_file()
            )

    def test_real_shell_tar_failure_does_not_copy_or_export(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            container_dir = base_dir / "container-tmp"
            trace_root = container_dir / "rollout-traces"
            trace_root.mkdir(parents=True)
            fake_bin = base_dir / "bin"
            fake_bin.mkdir()
            fake_tar = fake_bin / "tar"
            fake_tar.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
            fake_tar.chmod(0o700)
            output_dir = base_dir / "output"
            output_dir.mkdir()
            container_archive = container_dir / "astroncode_traces.tar.gz"
            shell_environment = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            }

            with self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                commands = self.run_export_with_real_shell(
                    self.make_agent(),
                    "real-shell-tar-failure",
                    trace_root,
                    container_archive,
                    output_dir,
                    shell_environment=shell_environment,
                )

            self.assertEqual(
                [command[:2] for command in commands].count(["docker", "cp"]),
                0,
            )
            self.assertFalse(
                (output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME).exists()
            )
            self.assertEqual(
                self.read_trace_export_status(output_dir)["status"],
                "failed",
            )

    def test_existing_archive_directory_records_failed_without_recursive_delete(
        self,
    ) -> None:
        for trace_value in (None, "0"):
            environment = {}
            if trace_value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
            with self.subTest(trace_value=trace_value), patch.dict(
                os.environ,
                environment,
                clear=True,
            ), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                archive_target = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
                archive_target.mkdir()
                marker = archive_target / "must-not-be-deleted"
                marker.write_text("preserve", encoding="utf-8")
                with patch(
                    "src.agents.astroncode.runner.subprocess.run"
                ) as run_mock, self.assertLogs(
                    "src.agents.astroncode.runner",
                    level="WARNING",
                ):
                    self.make_agent()._collect_rollout_trace_archive(
                        "directory-archive",
                        output_dir,
                    )

                run_mock.assert_not_called()
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
                status = self.read_trace_export_status(output_dir)
                self.assertEqual(status["status"], "failed")
                self.assertEqual(status["enabled"], trace_value is None)
                self.assertIn("cleanup", status["error"])

    def test_unremovable_existing_archive_records_failed_without_docker(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            archive = output_dir / runner.ASTRONCODE_TRACE_ARCHIVE_NAME
            archive.write_bytes(b"existing")
            with patch.object(
                Path,
                "unlink",
                side_effect=PermissionError("unlink denied"),
            ), patch(
                "src.agents.astroncode.runner.subprocess.run"
            ) as run_mock, self.assertLogs(
                "src.agents.astroncode.runner",
                level="WARNING",
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "unremovable-archive",
                    output_dir,
                )

            run_mock.assert_not_called()
            self.assertEqual(archive.read_bytes(), b"existing")
            status = self.read_trace_export_status(output_dir)
            self.assertEqual(status["status"], "failed")
            self.assertIn("unlink denied", status["error"])

    def test_run_batch_collects_usage_before_cleanup_for_all_execution_outcomes(
        self,
    ) -> None:
        cases = {
            "success": AgentExecution(1.0, None, None, None),
            "agent-error": AgentExecution(1.0, "model failed", None, None),
            "raised-timeout": subprocess.TimeoutExpired(["astroncode"], 30),
        }
        parsed_usage = {
            "input_tokens": 5,
            "output_tokens": 4,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 9,
            "cost_usd": 0.5,
            "request_count": 1,
        }
        task = {
            "task_id": "01_example_task_1",
            "workspace_path": "/nonexistent-workspace",
            "prompt": "test prompt",
            "timeout_seconds": 30,
            "category": "01_Productivity_Flow",
        }
        anomaly_result = {
            "has_validity_failure": False,
            "needs_review": False,
            "items": [],
        }

        for name, execution_or_error in cases.items():
            with self.subTest(name=name), patch.dict(
                os.environ,
                {},
                clear=True,
            ), tempfile.TemporaryDirectory() as temp_dir:
                events: list[str] = []
                agent = self.make_agent()
                if isinstance(execution_or_error, Exception):
                    run_task_patch = patch.object(
                        agent,
                        "run_task",
                        side_effect=execution_or_error,
                    )
                else:
                    run_task_patch = patch.object(
                        agent,
                        "run_task",
                        return_value=execution_or_error,
                    )
                original_collect_usage = agent.collect_usage
                original_save_usage = run_batch.save_usage

                def tracked_collect_usage(**kwargs):
                    events.append("collect_usage")
                    return original_collect_usage(**kwargs)

                def tracked_save_usage(output_dir, result, usage, task_id):
                    events.append("save_usage")
                    return original_save_usage(output_dir, result, usage, task_id)

                def tracked_remove_container(task_id):
                    events.append("remove_container")

                with run_task_patch, patch.object(
                    agent,
                    "collect_usage",
                    side_effect=tracked_collect_usage,
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
                ), patch(
                    "src.agents.astroncode.runner.subprocess.run",
                    side_effect=OSError("trace docker unavailable"),
                ), patch.object(
                    run_batch,
                    "grade_the_task",
                    side_effect=lambda *args, **kwargs: args[4],
                ), patch.object(
                    run_batch,
                    "save_usage",
                    side_effect=tracked_save_usage,
                ), patch.object(
                    run_batch,
                    "collect_task_output",
                ), patch.object(
                    run_batch,
                    "scan_run_dir",
                    return_value=anomaly_result,
                ), patch.object(
                    run_batch,
                    "remove_container",
                    side_effect=tracked_remove_container,
                ), self.assertLogs(
                    "src.agents.astroncode.runner",
                    level="WARNING",
                ):
                    result = run_batch.run_single_task(
                        task,
                        "test-model",
                        agent,
                        Path(temp_dir),
                    )

                self.assertEqual(
                    events,
                    ["collect_usage", "save_usage", "remove_container"],
                )
                self.assertEqual(result["usage"]["total_tokens"], 9)
                usage_files = list(Path(temp_dir).rglob("usage.json"))
                self.assertEqual(len(usage_files), 1)
                status_files = list(Path(temp_dir).rglob("execution_status.json"))
                self.assertEqual(len(status_files), 1)
                status = json.loads(status_files[0].read_text(encoding="utf-8"))
                self.assertEqual(status["trace_export"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
