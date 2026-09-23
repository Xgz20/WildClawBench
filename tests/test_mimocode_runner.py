from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.base import AgentTaskSpec
from src.agents.mimocode.runner import (
    DEFAULT_IMAGE,
    DEFAULT_MIMOCODE_API,
    HOST_TIMEOUT_GRACE_SECONDS,
    MiMoCodeAgent,
    build_container_command,
    normalize_mimocode_model_id,
    resolve_mimocode_config,
    start_mimocode_container,
)


class MiMoCodeRunnerTests(unittest.TestCase):
    def test_config_and_model_normalization(self) -> None:
        env = {
            "DOCKER_IMAGE_MIMOCODE": "mimo:test",
            "OPENROUTER_API_KEY": "key",
            "OPENROUTER_BASE_URL": "https://example/v1",
            "MIMOCODE_API": "anthropic-messages",
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_mimocode_config()
        self.assertEqual(config.image, "mimo:test")
        self.assertEqual(config.api, "anthropic-messages")
        self.assertEqual(normalize_mimocode_model_id("openrouter/xopglm52"), "xopglm52")
        with patch.dict(os.environ, {}, clear=True):
            defaults = resolve_mimocode_config()
        self.assertEqual(defaults.image, DEFAULT_IMAGE)
        self.assertEqual(defaults.api, DEFAULT_MIMOCODE_API)

    def test_container_command_contains_protocol_and_credentials(self) -> None:
        config = resolve_mimocode_config(
            image="mimo:test",
            openrouter_api_key="key",
            openrouter_base_url="https://example/v1",
            api="openai-responses",
        )
        with patch(
            "src.agents.mimocode.runner.container_resource_args", return_value=[]
        ):
            command = build_container_command(
                config,
                task_id="mimo-task",
                workspace_exec=Path("/tmp/exec"),
                model="openrouter/xopglm52",
                timeout_seconds=300,
                thinking="high",
            )
        self.assertIn("MIMOCODE_MODEL_ID=xopglm52", command)
        self.assertIn("MIMOCODE_API=openai-responses", command)
        self.assertIn("OPENROUTER_API_KEY=key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://example/v1", command)
        self.assertEqual(command[:3], ["docker", "run", "-d"])

    def test_start_container_rejects_missing_endpoint(self) -> None:
        config = resolve_mimocode_config(
            image="mimo:test", openrouter_api_key="", openrouter_base_url=""
        )
        with patch("src.agents.mimocode.runner.subprocess.run") as run_mock:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                start_mimocode_container(
                    config,
                    task_id="mimo-task",
                    workspace_exec=Path("/tmp/exec"),
                    model="xopglm52",
                    timeout_seconds=30,
                )
        run_mock.assert_not_called()

    def test_lifecycle_success_timeout_and_native_error(self):
        fixture = Path(__file__).parent / "fixtures/mimocode/trace.jsonl"
        for rc, native_error, expected in [
            (0, False, "finished"),
            (124, False, "timed_out"),
            (137, False, "error"),
            (1, False, "error"),
            (0, True, "error"),
        ]:
            with (
                self.subTest(rc=rc, native_error=native_error),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                agent = MiMoCodeAgent(
                    openrouter_api_key="test-key",
                    openrouter_base_url="https://example/v1",
                )
                spec = AgentTaskSpec(
                    task_id="mimo-test",
                    task={},
                    workspace_path=str(root / "workspace"),
                    prompt="Test",
                    timeout_seconds=30,
                    output_dir=root / "output",
                    model="openrouter/test-model",
                )

                def run(*_args):
                    dest = spec.output_dir / "mimocode_trace.jsonl"
                    shutil.copyfile(fixture, dest)
                    if native_error:
                        with dest.open("a") as stream:
                            stream.write(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "sessionID": "session-1",
                                        "error": {"message": "401 Unauthorized"},
                                    }
                                )
                                + "\n"
                            )
                    return subprocess.CompletedProcess([], rc, "", "")

                with ExitStack() as stack:
                    for name in (
                        "_start_container",
                        "_prepare_workspace",
                        "_copy_prompt",
                    ):
                        stack.enter_context(patch.object(agent, name))
                    stack.enter_context(
                        patch.object(
                            agent, "_probe_harness_version", return_value="0.1.14"
                        )
                    )
                    stack.enter_context(
                        patch.object(agent, "_run_mimocode", side_effect=run)
                    )
                    export = stack.enter_context(
                        patch.object(agent, "_export_artifacts")
                    )
                    for name in (
                        "setup_skills",
                        "run_warmup",
                        "snapshot_workspace_state",
                    ):
                        stack.enter_context(patch("src.agents.mimocode.runner." + name))
                    agent.run_task(spec)
                status = json.loads(
                    (spec.output_dir / "execution_status.json").read_text()
                )
                self.assertEqual(status["status"], expected)
                self.assertEqual(status["timed_out"], rc == 124)
                self.assertEqual(status["harness_version"], "0.1.14")
                self.assertEqual(export.call_args.kwargs["exit_code"], rc)

    def test_native_stdout_is_not_modified_by_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            agent = MiMoCodeAgent(
                openrouter_api_key="test-key", openrouter_base_url="https://example/v1"
            )
            proc = MagicMock()
            proc.wait.return_value = 0
            root = Path(temporary)
            with patch(
                "src.agents.mimocode.runner.subprocess.Popen", return_value=proc
            ):
                agent._run_mimocode("mimo-test", 20, root)
            self.assertEqual((root / "mimocode_trace.jsonl").read_text(), "")
            proc.wait.assert_called_once_with(timeout=20 + HOST_TIMEOUT_GRACE_SECONDS)

    def test_native_database_uses_sqlite_backup_not_raw_wal_copy(self):
        with patch(
            "src.agents.mimocode.runner.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run:
            MiMoCodeAgent._collect_native_database("mimo-test", Path("/tmp/output"))
        backup = run.call_args_list[0].args[0]
        self.assertIn("src.backup(dst)", backup[-1])
        self.assertIn("?mode=ro", backup[-1])
        copied = run.call_args_list[1].args[0]
        self.assertEqual(copied[-1], "/tmp/output/mimocode.db")
        self.assertNotIn("config", copied[-2])


if __name__ == "__main__":
    unittest.main()
