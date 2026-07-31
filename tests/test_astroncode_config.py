from __future__ import annotations

import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode.runner import AstronCodeAgent


DEFAULT_MODELS_BASE_URL = (
    "https://astroncode-api-prod.xf-yun.com/"
    "api/v1/astroncode_webserver/config-v1"
)


class AstronCodeConfigTests(unittest.TestCase):
    def make_agent(
        self,
        api_key: str = "openrouter-fallback-key",
        base_url: str = "https://openrouter.example/api/v1",
    ) -> AstronCodeAgent:
        return AstronCodeAgent(
            openrouter_api_key=api_key,
            openrouter_base_url=base_url,
        )

    def parse_config(
        self,
        agent: AstronCodeAgent,
        model: str,
        *,
        reasoning_effort: str | None = None,
        wire_api: str | None = None,
        redact_secrets: bool = False,
    ) -> dict:
        provider = agent._provider_for_model(model)
        rendered = agent._render_codex_config(
            model=model,
            reasoning_effort=reasoning_effort,
            wire_api=wire_api,
            provider_api_key=agent._resolve_provider_api_key(provider),
            redact_secrets=redact_secrets,
        )
        return tomllib.loads(rendered)

    def test_provider_auto_detection_uses_three_routes(self) -> None:
        with patch.dict(os.environ, {"ASTRONCODE_MODEL_PROVIDER": ""}, clear=False):
            agent = self.make_agent()
            for model in (
                "openrouter/xminimaxm25",
                "openrouter/xopglm52",
                "openrouter/xsparkx2agent",
                "openrouter/astronclaw-auto",
            ):
                with self.subTest(model=model):
                    self.assertEqual(agent._provider_for_model(model), "astron-spark")
            self.assertEqual(
                agent._provider_for_model("openrouter/gpt-5.5"), "one-iflytek"
            )
            self.assertEqual(
                agent._provider_for_model("openrouter/claude-4"), "openrouter"
            )

    def test_provider_override_accepts_only_supported_values(self) -> None:
        for provider in ("astron-spark", "one-iflytek", "openrouter"):
            with self.subTest(provider=provider), patch.dict(
                os.environ,
                {"ASTRONCODE_MODEL_PROVIDER": provider},
                clear=False,
            ):
                agent = self.make_agent()
                self.assertEqual(
                    agent._provider_for_model("openrouter/unknown"), provider
                )

        with patch.dict(
            os.environ,
            {"ASTRONCODE_MODEL_PROVIDER": "unsupported"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                ValueError, "astron-spark.*one-iflytek.*openrouter"
            ):
                self.make_agent()

    def test_runtime_configuration_is_snapshotted_at_construction(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASTRONCODE_MODEL_PROVIDER": " ASTRON-SPARK ",
                "ASTRON_API_KEY": "initial-astron-key",
                "ASTRON_SPARK_API_KEY": "initial-legacy-key",
                "ONE_IFLYTEK_API_KEY": "initial-one-key",
                "ONE_IFLYTEK_BASE_URL": "https://initial.one/v1",
                "ASTRON_MODELS_BASE_URL": "https://initial.catalog/config-v1",
                "OPENROUTER_API_KEY": "environment-openrouter-key",
                "OPENROUTER_BASE_URL": "https://environment-openrouter/v1",
            },
            clear=False,
        ):
            agent = self.make_agent(
                api_key="constructor-openrouter-key",
                base_url="https://constructor-openrouter/v1",
            )

        with patch.dict(
            os.environ,
            {
                "ASTRONCODE_MODEL_PROVIDER": "openrouter",
                "ASTRON_API_KEY": "changed-astron-key",
                "ASTRON_SPARK_API_KEY": "changed-legacy-key",
                "ONE_IFLYTEK_API_KEY": "changed-one-key",
                "ONE_IFLYTEK_BASE_URL": "https://changed.one/v1",
                "ASTRON_MODELS_BASE_URL": "https://changed.catalog/config-v1",
            },
            clear=False,
        ):
            self.assertEqual(
                agent._provider_for_model("openrouter/claude-4"), "astron-spark"
            )
            self.assertEqual(
                agent._resolve_provider_api_key("astron-spark"),
                "initial-astron-key",
            )
            self.assertEqual(
                agent._resolve_provider_api_key("one-iflytek"), "initial-one-key"
            )
            self.assertEqual(
                agent._resolve_provider_api_key("openrouter"),
                "constructor-openrouter-key",
            )
            self.assertEqual(
                agent._resolve_one_iflytek_base_url(), "https://initial.one/v1"
            )
            self.assertEqual(
                getattr(agent, "models_base_url", None),
                "https://initial.catalog/config-v1",
            )

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_container_environment_uses_snapshotted_credentials(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "container-id", "")
        with patch.dict(
            os.environ,
            {
                "ASTRONCODE_MODEL_PROVIDER": "",
                "ASTRON_API_KEY": "initial-primary-key",
                "ASTRON_SPARK_API_KEY": "initial-spark-key",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="initial-openrouter-key")

        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "changed-primary-key",
                "ASTRON_SPARK_API_KEY": "changed-spark-key",
                "TASK_SECRET": "task-secret",
                "LOBSTER_SECRET": "lobster-secret",
            },
            clear=False,
        ), tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "exec").mkdir()
            agent._start_container(
                "snapshot-test",
                tmp,
                {"env": "TASK_SECRET"},
                {"env": ["LOBSTER_SECRET"]},
            )

        run_call = run_mock.call_args
        command = run_call.args[0]
        child_environment = run_call.kwargs["env"]
        expected_environment = {
            "OPENROUTER_API_KEY": "initial-openrouter-key",
            "ASTRON_API_KEY": "initial-primary-key",
            "ASTRON_SPARK_API_KEY": "initial-spark-key",
            "TASK_SECRET": "task-secret",
            "LOBSTER_SECRET": "lobster-secret",
        }
        for key, value in expected_environment.items():
            with self.subTest(key=key):
                self.assertIn(key, command)
                self.assertEqual(child_environment[key], value)
                for argument in command:
                    self.assertNotIn(value, argument)
                    self.assertNotIn(f"{key}=", argument)

        self.assertNotIn("changed-primary-key", child_environment.values())
        self.assertNotIn("changed-spark-key", child_environment.values())

    def test_provider_key_precedence_and_fallbacks(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "astron-primary",
                "ASTRON_SPARK_API_KEY": "astron-secondary",
                "ONE_IFLYTEK_API_KEY": "one-primary",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="openrouter-fallback")
            self.assertEqual(
                agent._resolve_provider_api_key("astron-spark"), "astron-primary"
            )
            self.assertEqual(
                agent._resolve_provider_api_key("one-iflytek"), "one-primary"
            )
            self.assertEqual(
                agent._resolve_provider_api_key("openrouter"), "openrouter-fallback"
            )

        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "",
                "ASTRON_SPARK_API_KEY": "astron-secondary",
                "ONE_IFLYTEK_API_KEY": "",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="openrouter-fallback")
            self.assertEqual(
                agent._resolve_provider_api_key("astron-spark"), "astron-secondary"
            )
            self.assertEqual(
                agent._resolve_provider_api_key("one-iflytek"), "openrouter-fallback"
            )

        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "",
                "ASTRON_SPARK_API_KEY": "",
                "ONE_IFLYTEK_API_KEY": "",
            },
            clear=False,
        ):
            agent = self.make_agent(api_key="openrouter-fallback")
            self.assertEqual(
                agent._resolve_provider_api_key("astron-spark"),
                "openrouter-fallback",
            )

    def test_one_iflytek_base_url_precedence(self) -> None:
        cases = (
            (
                "https://one.example/v1",
                "https://fallback.example/api/v1",
                "",
                "https://one.example/v1",
            ),
            (
                "",
                "https://fallback.example/api/v1",
                "",
                "https://fallback.example/api/v1",
            ),
            (
                "",
                "https://environment.example/api/v1",
                "https://constructor.example/api/v1",
                "https://constructor.example/api/v1",
            ),
            ("", "", "", "https://one.iflytek.com/api/llm/console/chat/v1"),
        )
        for dedicated_url, openrouter_url, constructor_url, expected in cases:
            with self.subTest(expected=expected), patch.dict(
                os.environ,
                {
                    "ONE_IFLYTEK_BASE_URL": dedicated_url,
                    "OPENROUTER_BASE_URL": openrouter_url,
                },
                clear=False,
            ):
                agent = self.make_agent(base_url=constructor_url)
                self.assertEqual(agent._resolve_one_iflytek_base_url(), expected)

    def test_astron_spark_config_matches_0_0_13(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ASTRON_API_KEY": "astron-secret",
                "ASTRONCODE_MODEL_PROVIDER": "",
            },
            clear=False,
        ):
            config = self.parse_config(
                self.make_agent(),
                "openrouter/xopglm52",
                reasoning_effort="high",
            )

        self.assertEqual(config["model"], "xopglm52")
        self.assertEqual(config["model_provider"], "astron-spark")
        self.assertEqual(config["model_reasoning_effort"], "high")
        self.assertIs(config["model_supports_reasoning_summaries"], False)
        self.assertIs(config["hide_agent_reasoning"], True)
        provider = config["model_providers"]["astron-spark"]
        self.assertEqual(provider["experimental_bearer_token"], "astron-secret")
        self.assertEqual(provider.get("models_base_url"), DEFAULT_MODELS_BASE_URL)

    def test_one_iflytek_config_uses_responses_contract_and_native_types(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ONE_IFLYTEK_API_KEY": "one-secret",
                "ONE_IFLYTEK_BASE_URL": "https://one.example/v1",
                "ASTRONCODE_MODEL_PROVIDER": "",
            },
            clear=False,
        ):
            config = self.parse_config(
                self.make_agent(),
                "openrouter/gpt-5.5",
                wire_api="chat",
            )

        self.assertEqual(config["model"], "gpt-5.5")
        self.assertEqual(config["model_provider"], "one-iflytek")
        provider = config["model_providers"]["one-iflytek"]
        self.assertEqual(provider["name"], "Codex via iFlytek One")
        self.assertEqual(provider["base_url"], "https://one.example/v1")
        self.assertEqual(provider.get("models_base_url"), DEFAULT_MODELS_BASE_URL)
        self.assertEqual(provider["experimental_bearer_token"], "one-secret")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertIs(provider["requires_openai_auth"], False)
        self.assertIsInstance(provider["requires_openai_auth"], bool)
        self.assertEqual(provider["stream_idle_timeout_ms"], 300000)
        self.assertIsInstance(provider["stream_idle_timeout_ms"], int)

    def test_reasoning_effort_round_trips_as_a_toml_basic_string(self) -> None:
        reasoning_effort = 'high"\n# attempted_toml_injection'
        with patch.dict(
            os.environ,
            {"ASTRONCODE_MODEL_PROVIDER": "", "OPENROUTER_API_KEY": "test-key"},
            clear=False,
        ):
            config = self.parse_config(
                self.make_agent(),
                "openrouter/claude-4",
                reasoning_effort=reasoning_effort,
            )

        self.assertEqual(config["model_reasoning_effort"], reasoning_effort)
        self.assertEqual(config["model"], "claude-4")

    def test_openrouter_config_keeps_environment_reference(self) -> None:
        with patch.dict(os.environ, {"ASTRONCODE_MODEL_PROVIDER": ""}, clear=False):
            config = self.parse_config(self.make_agent(), "openrouter/claude-4")

        self.assertEqual(config["model_provider"], "openrouter")
        provider = config["model_providers"]["openrouter"]
        self.assertEqual(provider["env_key"], "OPENROUTER_API_KEY")
        self.assertEqual(provider.get("models_base_url"), DEFAULT_MODELS_BASE_URL)
        self.assertNotIn("experimental_bearer_token", provider)

    def test_models_base_url_override_applies_to_all_providers(self) -> None:
        models = (
            "openrouter/xopglm52",
            "openrouter/gpt-5.5",
            "openrouter/claude-4",
        )
        with patch.dict(
            os.environ,
            {
                "ASTRON_MODELS_BASE_URL": "https://catalog.example/config-v1",
                "ASTRONCODE_MODEL_PROVIDER": "",
            },
            clear=False,
        ):
            agent = self.make_agent()
            for model in models:
                with self.subTest(model=model):
                    config = self.parse_config(agent, model)
                    provider = config["model_provider"]
                    self.assertEqual(
                        config["model_providers"][provider].get("models_base_url"),
                        "https://catalog.example/config-v1",
                    )

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_config_write_streams_real_token_and_redacts_host_artifact(
        self, run_mock
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
        cases = (
            ("openrouter/xopglm52", "ASTRON_API_KEY", "host-astron-secret"),
            ("openrouter/gpt-5.5", "ONE_IFLYTEK_API_KEY", "host-one-secret"),
        )
        for model, env_key, secret in cases:
            with self.subTest(model=model), patch.dict(
                os.environ,
                {
                    env_key: secret,
                    "ASTRONCODE_MODEL_PROVIDER": "",
                },
                clear=False,
            ), tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                run_mock.reset_mock()
                self.make_agent()._write_codex_config(
                    task_id="redaction-test",
                    model=model,
                    reasoning_effort=None,
                    wire_api="chat",
                    output_dir=output_dir,
                )
                host_config = (output_dir / "config.toml").read_text(
                    encoding="utf-8"
                )
                run_call = run_mock.call_args

            self.assertNotIn(secret, host_config)
            self.assertIn('experimental_bearer_token = "***"', host_config)
            command = run_call.args[0]
            for argument in command:
                self.assertNotIn(secret, argument)
            self.assertEqual(command[:3], ["docker", "exec", "-i"])
            self.assertIn("umask 077", command[-1])
            self.assertIn("chmod 600", command[-1])
            self.assertIn(secret, run_call.kwargs["input"])
            self.assertNotIn(
                'experimental_bearer_token = "***"', run_call.kwargs["input"]
            )
            for key, value in run_call.kwargs.items():
                if key != "input":
                    self.assertNotIn(secret, repr(value))

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_successful_config_write_logs_do_not_leak_credentials(
        self, run_mock
    ) -> None:
        secret = "successful-write-secret-never-log"
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(
            os.environ,
            {
                "ASTRONCODE_MODEL_PROVIDER": "astron-spark",
                "ASTRON_API_KEY": secret,
            },
            clear=False,
        ), tempfile.TemporaryDirectory() as tmp, self.assertLogs(
            "src.agents.astroncode.runner", level="INFO"
        ) as captured:
            self.make_agent()._write_codex_config(
                task_id="log-secrecy-test",
                model="openrouter/xopglm52",
                reasoning_effort=None,
                wire_api=None,
                output_dir=Path(tmp),
            )

        self.assertNotIn(secret, "\n".join(captured.output))

    def test_missing_key_validates_only_active_provider_without_leaking_values(self) -> None:
        cases = (
            (
                "openrouter/xopglm52",
                {
                    "ASTRON_API_KEY": "",
                    "ASTRON_SPARK_API_KEY": "",
                    "OPENROUTER_API_KEY": "",
                    "ONE_IFLYTEK_API_KEY": "unrelated-one-secret",
                },
                (
                    "ASTRON_API_KEY",
                    "ASTRON_SPARK_API_KEY",
                    "OPENROUTER_API_KEY",
                ),
                "unrelated-one-secret",
            ),
            (
                "openrouter/gpt-5.5",
                {
                    "ONE_IFLYTEK_API_KEY": "",
                    "OPENROUTER_API_KEY": "",
                    "ASTRON_API_KEY": "unrelated-astron-secret",
                },
                ("ONE_IFLYTEK_API_KEY", "OPENROUTER_API_KEY"),
                "unrelated-astron-secret",
            ),
            (
                "openrouter/claude-4",
                {
                    "OPENROUTER_API_KEY": "",
                    "ASTRON_API_KEY": "unrelated-astron-secret",
                    "ONE_IFLYTEK_API_KEY": "unrelated-one-secret",
                },
                ("OPENROUTER_API_KEY",),
                "unrelated-astron-secret",
            ),
        )
        for model, environment, accepted_names, unrelated_secret in cases:
            with self.subTest(model=model), patch.dict(
                os.environ,
                {**environment, "ASTRONCODE_MODEL_PROVIDER": ""},
                clear=False,
            ), tempfile.TemporaryDirectory() as tmp:
                agent = self.make_agent(api_key="")
                with self.assertRaises(RuntimeError) as raised:
                    agent._write_codex_config(
                        task_id="missing-key",
                        model=model,
                        reasoning_effort=None,
                        wire_api=None,
                        output_dir=Path(tmp),
                    )

            message = str(raised.exception)
            for accepted_name in accepted_names:
                self.assertIn(accepted_name, message)
            self.assertNotIn(unrelated_secret, message)

    def test_default_image_is_v0_3(self) -> None:
        with patch.dict(os.environ, {"DOCKER_IMAGE_ASTRONCODE": ""}, clear=False):
            self.assertEqual(
                self.make_agent().image,
                "wildclawbench-astroncode-ubuntu:v0.3",
            )


if __name__ == "__main__":
    unittest.main()
