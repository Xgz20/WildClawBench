from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.deepseek_harness.runner import (
    DEFAULT_DSH_API,
    DEFAULT_IMAGE,
    append_agent_log_event,
    build_container_command,
    normalize_dsh_model_id,
    resolve_dsh_config,
    start_dsh_container,
    write_execution_status,
)


class DeepSeekHarnessConfigurationTests(unittest.TestCase):
    def test_normalize_dsh_model_id_removes_only_openrouter_prefix(self) -> None:
        self.assertEqual(normalize_dsh_model_id("openrouter/xopglm52"), "xopglm52")
        self.assertEqual(
            normalize_dsh_model_id("openrouter/anthropic/model"),
            "anthropic/model",
        )
        self.assertEqual(normalize_dsh_model_id("xopglm52"), "xopglm52")

    def test_resolve_config_prefers_arguments_then_environment_then_defaults(self) -> None:
        env = {
            "DOCKER_IMAGE_DEEPSEEK_HARNESS": "dsh:env",
            "OPENROUTER_API_KEY": "env-key",
            "OPENROUTER_BASE_URL": "https://env.example/v1",
            "DEEPSEEK_API_KEY": "search-key",
            "DSH_API": "openai-responses",
        }
        with patch.dict(os.environ, env, clear=True):
            from_env = resolve_dsh_config()
            explicit = resolve_dsh_config(
                image="dsh:test",
                openrouter_api_key="test-key",
                openrouter_base_url="https://maas.example/v2",
                deepseek_api_key="explicit-search-key",
                api="openai-completions",
            )

        self.assertEqual(from_env.image, "dsh:env")
        self.assertEqual(from_env.api, "openai-responses")
        self.assertEqual(from_env.openrouter_base_url, "https://env.example/v1")
        self.assertEqual(explicit.image, "dsh:test")
        self.assertEqual(explicit.openrouter_api_key, "test-key")
        self.assertEqual(explicit.openrouter_base_url, "https://maas.example/v2")
        self.assertEqual(explicit.deepseek_api_key, "explicit-search-key")
        self.assertEqual(explicit.api, "openai-completions")

        with patch.dict(os.environ, {}, clear=True):
            defaults = resolve_dsh_config()
        self.assertEqual(defaults.image, DEFAULT_IMAGE)
        self.assertEqual(defaults.api, DEFAULT_DSH_API)
        self.assertEqual(defaults.openrouter_base_url, "")

    def test_resolve_config_rejects_unsupported_api(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported DSH API"):
            resolve_dsh_config(api="openai-chat")

    def test_build_container_command_uses_detached_read_only_contract(self) -> None:
        config = resolve_dsh_config(
            image="dsh:test",
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas.example/v2",
            deepseek_api_key="search-key",
            api="openai-completions",
        )
        with patch(
            "src.agents.deepseek_harness.runner.container_resource_args",
            return_value=["--memory", "4g", "--cpus", "2"],
        ):
            command = build_container_command(
                config,
                task_id="dsh-task",
                workspace_exec=Path("/tmp/task workspace/exec"),
                model="openrouter/xopglm52",
                thinking="high",
                task_env_names=("SLACK_TOKEN",),
                lobster_env_names=("LOBSTER_TOKEN",),
                environ={
                    "SLACK_TOKEN": "slack-secret",
                    "LOBSTER_TOKEN": "lobster-secret",
                    "HTTP_PROXY_INNER": "http://proxy:8080",
                    "HTTPS_PROXY_INNER": "http://proxy:8443",
                    "NO_PROXY_INNER": "localhost,127.0.0.1",
                },
            )

        self.assertEqual(command[:3], ["docker", "run", "-d"])
        self.assertIn("--entrypoint", command)
        self.assertEqual(command[command.index("--entrypoint") + 1], "/bin/bash")
        self.assertIn("--memory", command)
        self.assertIn("--cpus", command)
        resolved_workspace = Path("/tmp/task workspace/exec").resolve()
        self.assertIn(f"{resolved_workspace}:/mnt/wildclaw_src:ro", command)
        self.assertIn("DSH_MODEL_ID=xopglm52", command)
        self.assertIn("DSH_API=openai-completions", command)
        self.assertIn("DSH_REASONING=high", command)
        self.assertIn("OPENROUTER_API_KEY=test-key", command)
        self.assertIn("OPENROUTER_BASE_URL=https://maas.example/v2", command)
        self.assertIn("DEEPSEEK_API_KEY=search-key", command)
        self.assertIn("SLACK_TOKEN=slack-secret", command)
        self.assertIn("LOBSTER_TOKEN=lobster-secret", command)
        self.assertEqual(command[-3:], ["/bin/bash", "-c", "tail -f /dev/null"])

    def test_build_container_command_omits_empty_optional_values(self) -> None:
        config = resolve_dsh_config(
            image="dsh:test",
            openrouter_api_key="test-key",
            openrouter_base_url="",
            deepseek_api_key="",
        )
        command = build_container_command(
            config,
            task_id="dsh-task",
            workspace_exec=Path("/work/exec"),
            model="xopglm52",
            environ={},
        )
        joined = "\n".join(command)

        self.assertNotIn("OPENROUTER_BASE_URL=", joined)
        self.assertNotIn("DEEPSEEK_API_KEY=", joined)
        self.assertNotIn("DSH_REASONING=", joined)

    def test_start_container_rejects_missing_key_before_docker(self) -> None:
        config = resolve_dsh_config(image="dsh:test", openrouter_api_key="")
        with patch("src.agents.deepseek_harness.runner.subprocess.run") as run_mock:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                start_dsh_container(
                    config,
                    task_id="dsh-task",
                    workspace_exec=Path("/work/exec"),
                    model="xopglm52",
                )
        run_mock.assert_not_called()

    def test_write_execution_status_updates_existing_json_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_execution_status(output_dir, status="starting", harness="deepseek-harness")
            result = write_execution_status(output_dir, status="running", api=DEFAULT_DSH_API)

            self.assertEqual(
                result,
                {
                    "status": "running",
                    "harness": "deepseek-harness",
                    "api": DEFAULT_DSH_API,
                },
            )
            self.assertEqual(
                json.loads((output_dir / "execution_status.json").read_text(encoding="utf-8")),
                result,
            )
            self.assertEqual(list(output_dir.glob(".execution_status.json.*.tmp")), [])

    def test_append_agent_log_event_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            append_agent_log_event(output_dir, {"event": "started", "secret": None})
            append_agent_log_event(output_dir, {"event": "finished", "exit_code": 0})

            rows = [
                json.loads(line)
                for line in (output_dir / "runner.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                rows,
                [
                    {"event": "started", "secret": None},
                    {"event": "finished", "exit_code": 0},
                ],
            )


if __name__ == "__main__":
    unittest.main()
