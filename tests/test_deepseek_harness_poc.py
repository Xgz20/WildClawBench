from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.deepseek_harness_poc import (
    build_docker_command,
    build_run_manifest,
    main,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "deepseek_harness"
REPO_ROOT = Path(__file__).parents[1]


class DeepSeekHarnessPocCliTests(unittest.TestCase):
    def test_script_entrypoint_runs_without_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, "tools/deepseek_harness_poc.py", "--help"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Run or convert a standalone DeepSeek Harness PoC task", completed.stdout)

    def test_convert_command_writes_all_conversion_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "converted"

            exit_code = main(
                [
                    "convert",
                    "--sessions",
                    str(FIXTURE_ROOT),
                    "--output",
                    str(output_dir),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "chat.jsonl").is_file())
            self.assertTrue((output_dir / "usage.json").is_file())
            self.assertTrue((output_dir / "conversion_manifest.json").is_file())

    def test_build_docker_command_mounts_inputs_and_inherits_credentials(self) -> None:
        command = build_docker_command(
            image="wildclawbench-deepseek-harness-poc:test",
            workspace=Path("/work/example"),
            sessions_dir=Path("/out/sessions"),
            model="deepseek/deepseek-chat-v3.1",
            prompt="Finish the task",
            container_name="wcb-dsh-test",
            reasoning="high",
            api="openai-responses",
        )

        self.assertEqual(command[:3], ["docker", "run", "--name"])
        self.assertIn("wcb-dsh-test", command)
        self.assertIn("/work/example:/tmp_workspace", command)
        self.assertIn("/out/sessions:/root/.dsh/sessions", command)
        self.assertIn("DSH_MODEL_ID=deepseek/deepseek-chat-v3.1", command)
        self.assertIn("DSH_REASONING=high", command)
        self.assertIn("DSH_API=openai-responses", command)
        self.assertIn("OPENROUTER_API_KEY", command)
        self.assertIn("DEEPSEEK_API_KEY", command)
        self.assertEqual(command[-2:], ["wildclawbench-deepseek-harness-poc:test", "Finish the task"])

    def test_run_returns_dsh_exit_code_converts_sessions_and_redacts_secrets(self) -> None:
        secret = "test-openrouter-secret-value"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            output_dir = root / "output"
            workspace.mkdir()
            shutil.copytree(FIXTURE_ROOT, output_dir / "sessions")
            completed = subprocess.CompletedProcess(
                args=["docker", "run"],
                returncode=7,
                stdout=f"request failed for {secret}\n",
                stderr=f"credential={secret}\n",
            )
            cleanup = subprocess.CompletedProcess(
                args=["docker", "rm"], returncode=0, stdout="", stderr=""
            )

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": secret}, clear=False):
                with patch(
                    "tools.deepseek_harness_poc.subprocess.run",
                    side_effect=[completed, cleanup],
                ) as run_mock:
                    exit_code = main(
                        [
                            "run",
                            "--image",
                            "dsh:test",
                            "--workspace",
                            str(workspace),
                            "--model",
                            "deepseek/model",
                            "--output",
                            str(output_dir),
                            "--prompt",
                            "Do the task",
                            "--timeout",
                            "30",
                            "--container-name",
                            "wcb-dsh-fixed",
                        ]
                    )

            self.assertEqual(exit_code, 7)
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(
                run_mock.call_args_list[1].args[0],
                ["docker", "rm", "-f", "wcb-dsh-fixed"],
            )
            self.assertTrue((output_dir / "chat.jsonl").is_file())
            self.assertNotIn(secret, (output_dir / "dsh.stdout.log").read_text(encoding="utf-8"))
            self.assertNotIn(secret, (output_dir / "dsh.stderr.log").read_text(encoding="utf-8"))
            manifest_text = (output_dir / "run_manifest.json").read_text(encoding="utf-8")
            self.assertNotIn(secret, manifest_text)
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["timeout_seconds"], 30.0)
            self.assertEqual(manifest["exit_code"], 7)
            self.assertEqual(
                manifest["credential_env_names"],
                ["OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"],
            )

    def test_run_timeout_returns_124_and_cleans_up_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            timeout = subprocess.TimeoutExpired(
                cmd=["docker", "run"], timeout=1, output="partial", stderr="timed out"
            )
            cleanup = subprocess.CompletedProcess(
                args=["docker", "rm"], returncode=0, stdout="", stderr=""
            )

            with patch(
                "tools.deepseek_harness_poc.subprocess.run",
                side_effect=[timeout, cleanup],
            ) as run_mock:
                exit_code = main(
                    [
                        "run",
                        "--image",
                        "dsh:test",
                        "--workspace",
                        str(workspace),
                        "--model",
                        "deepseek/model",
                        "--output",
                        str(root / "output"),
                        "--prompt",
                        "Do the task",
                        "--timeout",
                        "1",
                        "--container-name",
                        "wcb-dsh-timeout",
                    ]
                )

            self.assertEqual(exit_code, 124)
            self.assertEqual(run_mock.call_count, 2)
            manifest = json.loads(
                (root / "output" / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["timed_out"])

    def test_build_run_manifest_contains_names_not_secret_values(self) -> None:
        manifest = build_run_manifest(
            image="dsh:test",
            workspace=Path("/work"),
            sessions_dir=Path("/output/sessions"),
            model="deepseek/model",
            prompt="Do the task",
            container_name="wcb-dsh-test",
            timeout_seconds=60.0,
            exit_code=0,
            timed_out=False,
            api="openai-completions",
        )

        serialized = json.dumps(manifest)
        self.assertNotIn("OPENROUTER_API_KEY=", serialized)
        self.assertNotIn("DEEPSEEK_API_KEY=", serialized)
        self.assertNotIn("Do the task", serialized)
        self.assertIn("OPENROUTER_API_KEY", manifest["credential_env_names"])
        self.assertIn("prompt_sha256", manifest)
        self.assertEqual(manifest["api"], "openai-completions")


if __name__ == "__main__":
    unittest.main()
