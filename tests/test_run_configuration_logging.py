from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eval import run_batch


class RunConfigurationLoggingTests(unittest.TestCase):
    @staticmethod
    def args() -> SimpleNamespace:
        return SimpleNamespace(
            task=None,
            category="all",
            modality=None,
            tags=["custom"],
            exclude_tags=["ppt", "web-site-gen"],
            agent_backend="deepseek-harness",
            model="openrouter/xopdeepseekv4flash0731",
            thinking="high",
            parallel=2,
            runs=1,
            resume=False,
            rerun_error=False,
            rerun_anomalous=False,
            pass_threshold=0.99,
            dsh_api="openai-responses",
            openclaw_image_model=None,
            lobster_name=None,
            lobster_workspace=None,
            lobster_env="CUSTOM_API_KEY",
            models_config=None,
        )

    @staticmethod
    def backend() -> SimpleNamespace:
        return SimpleNamespace(
            api="openai-responses",
            image="deepseek-harness:test",
            openrouter_base_url=(
                "https://user:password@maas.example/v1?api_key=query-secret#fragment"
            ),
        )

    def test_effective_configuration_is_complete_and_redacted(self) -> None:
        environment = {
            "OPENROUTER_API_KEY": "candidate-secret",
            "ANTHROPIC_API_KEY": "judge-secret",
            "CUSTOM_API_KEY": "task-secret",
            "OPENROUTER_BASE_URL": (
                "https://user:password@maas.example/v1?api_key=query-secret#fragment"
            ),
            "ANTHROPIC_BASE_URL": "https://judge.example/api/chat",
            "JUDGE_MODEL": "anthropic/claude-opus-5",
            "WILDCLAW_DOCKER_MEMORY": "8g",
            "WILDCLAW_DOCKER_CPUS": "2",
            "WILDCLAW_GRADING_TIMEOUT_SECONDS": "725",
            "WILDCLAW_JUDGE_TIMEOUT_SECONDS": "345",
            "MAAS_MAX_TOKENS": "32768",
        }

        with patch.object(run_batch, "TIMEOUT_OVERRIDE", 3600), patch.object(
            run_batch, "TIMEOUT_MULTIPLIER", 1.0
        ):
            config = run_batch._build_run_configuration(
                self.args(),
                self.backend(),
                Path("/tmp/output/deepseek-harness"),
                environ=environment,
            )

        self.assertEqual(config["selection"]["value"], "all")
        self.assertEqual(config["execution"]["parallel"], 2)
        self.assertEqual(config["execution"]["api"], "openai-responses")
        self.assertEqual(config["execution"]["image"], "deepseek-harness:test")
        self.assertEqual(config["timeout"]["override_seconds"], 3600)
        self.assertEqual(config["timeout"]["grading_seconds"], 725.0)
        self.assertEqual(config["timeout"]["judge_seconds"], 345.0)
        self.assertEqual(config["resources"], {"memory": "8g", "cpus": "2"})
        self.assertEqual(config["judge"]["model"], "anthropic/claude-opus-5")
        self.assertEqual(
            config["backend_endpoints"]["openrouter_base_url"],
            "https://maas.example/v1?[REDACTED]#[REDACTED]",
        )
        self.assertEqual(config["credentials"]["OPENROUTER_API_KEY"], "configured")
        self.assertEqual(config["credentials"]["CUSTOM_API_KEY"], "configured")

        serialized = json.dumps(config, ensure_ascii=False)
        for secret in (
            "candidate-secret",
            "judge-secret",
            "task-secret",
            "password",
            "query-secret",
        ):
            self.assertNotIn(secret, serialized)

    def test_run_log_contains_parseable_json_record_without_secrets(self) -> None:
        environment = {
            "OPENROUTER_API_KEY": "candidate-secret",
            "OPENROUTER_BASE_URL": "https://maas.example/v1?token=query-secret",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.log"
            handler = run_batch.attach_file_logging(log_path)
            try:
                with patch.dict(run_batch.os.environ, environment, clear=True):
                    run_batch._log_run_configuration(
                        self.args(),
                        self.backend(),
                        Path("/tmp/output/deepseek-harness"),
                    )
            finally:
                logging.getLogger().removeHandler(handler)
                handler.close()
            rendered = log_path.read_text(encoding="utf-8")

        message = rendered.split("Run configuration:\n", 1)[1]
        payload = json.loads(message)
        self.assertEqual(
            payload["execution"]["model"], "openrouter/xopdeepseekv4flash0731"
        )
        self.assertIn("🔧", rendered)
        self.assertIn('\n  "execution": {\n', rendered)
        self.assertNotIn("candidate-secret", rendered)
        self.assertNotIn("query-secret", rendered)


if __name__ == "__main__":
    unittest.main()
