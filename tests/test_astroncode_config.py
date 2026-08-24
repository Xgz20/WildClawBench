from __future__ import annotations

import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode import runner as astroncode_runner
from src.agents.astroncode.runner import AstronCodeAgent


DEFAULT_MODELS_BASE_URL = (
    "https://astroncode-api-prod.xf-yun.com/"
    "api/v1/astroncode_webserver/config-v1"
)
SEARCH_AGENT_CONFIG_PATH = "/opt/astroncode/search-agent.config.toml"


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

    def config_run_side_effect(
        self,
        *,
        fragment: str = "",
        fragment_returncode: int = 0,
        fragment_stderr: str = "",
        write_returncode: int = 0,
        write_stdout: str = "",
        write_stderr: str = "",
    ):
        def run(command, **kwargs):
            if command[:2] == ["docker", "cp"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ["docker", "exec", "-d"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if (
                command[:2] == ["docker", "exec"]
                and command[-3:-1] == ["python3", "-c"]
            ):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ["docker", "exec", "-i"]:
                return subprocess.CompletedProcess(
                    command,
                    write_returncode,
                    write_stdout,
                    write_stderr,
                )
            if (
                command[:2] == ["docker", "exec"]
                and SEARCH_AGENT_CONFIG_PATH in command[-1]
            ):
                return subprocess.CompletedProcess(
                    command,
                    fragment_returncode,
                    fragment,
                    fragment_stderr,
                )
            self.fail(f"Unexpected subprocess command: {command!r}")

        return run

    def test_maas_proxy_base_url_is_used_only_when_requested(self) -> None:
        agent = self.make_agent(base_url="https://maas-api.example/v1")
        provider = agent._provider_for_model("openrouter/xopglm52")

        proxied = tomllib.loads(
            agent._render_codex_config(
                model="openrouter/xopglm52",
                reasoning_effort="high",
                wire_api=None,
                provider_api_key=agent._resolve_provider_api_key(provider),
                redact_secrets=True,
                request_base_url="http://127.0.0.1:18080",
            )
        )
        direct = self.parse_config(agent, "openrouter/gpt-5.5")

        self.assertEqual(
            proxied["model_providers"]["astron-spark"]["base_url"],
            "http://127.0.0.1:18080",
        )
        self.assertEqual(
            direct["model_providers"]["one-iflytek"]["base_url"],
            "https://maas-api.example/v1",
        )

    def test_maas_max_tokens_mode_defaults_to_native(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_MAAS_MAX_TOKENS_MODE": ""},
            clear=False,
        ):
            agent = self.make_agent(base_url="https://maas-api.example/v1")

        self.assertEqual(agent.maas_max_tokens_mode, "native")

    def test_invalid_maas_max_tokens_mode_fails_fast(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_MAAS_MAX_TOKENS_MODE": "automatic"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "ASTRONCODE_MAAS_MAX_TOKENS_MODE must be one of: native, proxy",
            ):
                self.make_agent(base_url="https://maas-api.example/v1")

    def test_native_maas_mode_does_not_start_compatibility_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ASTRONCODE_MAAS_MAX_TOKENS_MODE": "native",
                "MAAS_MAX_TOKENS": "8192",
            },
            clear=False,
        ), patch(
            "src.agents.astroncode.runner.start_maas_request_proxy"
        ) as start_proxy, patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock:
            run_mock.side_effect = self.config_run_side_effect(fragment_returncode=44)
            output_dir = Path(tmp)
            self.make_agent(base_url="https://maas-api.example/v1")._write_codex_config(
                task_id="native-maas",
                model="openrouter/xopglm52",
                reasoning_effort=None,
                wire_api=None,
                output_dir=output_dir,
            )
            config = tomllib.loads(
                (output_dir / "config.toml").read_text(encoding="utf-8")
            )

        start_proxy.assert_not_called()
        self.assertNotIn("base_url", config["model_providers"]["astron-spark"])

    def test_proxy_maas_mode_starts_compatibility_proxy_with_common_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ASTRONCODE_MAAS_MAX_TOKENS_MODE": "proxy",
                "MAAS_MAX_TOKENS": "",
            },
            clear=False,
        ), patch(
            "src.agents.astroncode.runner.start_maas_request_proxy",
            return_value="http://127.0.0.1:18080",
        ) as start_proxy, patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock:
            run_mock.side_effect = self.config_run_side_effect(fragment_returncode=44)
            output_dir = Path(tmp)
            self.make_agent(base_url="https://maas-api.example/v1")._write_codex_config(
                task_id="proxy-maas",
                model="openrouter/xopglm52",
                reasoning_effort=None,
                wire_api=None,
                output_dir=output_dir,
            )
            config = tomllib.loads(
                (output_dir / "config.toml").read_text(encoding="utf-8")
            )

        start_proxy.assert_called_once_with(
            "proxy-maas",
            upstream_base_url="https://maas-api.example/v1",
            max_tokens=16384,
        )
        self.assertEqual(
            config["model_providers"]["astron-spark"]["base_url"],
            "http://127.0.0.1:18080",
        )

    def config_write_calls(self, run_mock):
        return [
            call
            for call in run_mock.call_args_list
            if call.args[0][:3] == ["docker", "exec", "-i"]
        ]

    def search_agent_config_read_calls(self, run_mock):
        return [
            call
            for call in run_mock.call_args_list
            if call.args[0][:2] == ["docker", "exec"]
            and call.args[0][:3] != ["docker", "exec", "-i"]
            and SEARCH_AGENT_CONFIG_PATH in call.args[0][-1]
        ]

    def test_toml_basic_string_round_trips_control_characters(self) -> None:
        value = (
            "普通 Unicode "
            + "".join(chr(codepoint) for codepoint in range(0x20))
            + '\x7f"\\'
        )

        rendered = astroncode_runner.toml_basic_string(value)

        try:
            parsed = tomllib.loads(f"value = {rendered}")
        except tomllib.TOMLDecodeError as error:
            self.fail(f"rendered basic string is invalid TOML: {error}")
        self.assertEqual(parsed["value"], value)
        for escape in (r"\b", r"\t", r"\n", r"\f", r"\r"):
            with self.subTest(escape=escape):
                self.assertIn(escape, rendered)
        for codepoint in (*range(0x08), 0x0B, *range(0x0E, 0x20), 0x7F):
            with self.subTest(codepoint=codepoint):
                self.assertIn(f"\\u{codepoint:04X}", rendered)
        self.assertIn("普通 Unicode ", rendered)

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
        fragment = (
            "[mcp_servers.search]\n"
            'command = "search-agent"\n'
        )
        run_mock.side_effect = self.config_run_side_effect(fragment=fragment)
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
                write_calls = self.config_write_calls(run_mock)
                self.assertEqual(len(write_calls), 1)
                run_call = write_calls[0]

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
    def test_valid_search_agent_fragment_is_redacted_from_host_config(
        self, run_mock
    ) -> None:
        special_server_name = 'web-\b\f\x00\x7f"\\\nagent'
        encoded_special_server_name = r'web-\b\f\u0000\u007F\"\\\nagent'
        fragment = (
            "# fragment-comment-secret\n"
            "[mcp_servers.search]\n"
            'command = "/private/bin/search-command"\n'
            'args = ["--token", "fragment-args-secret"]\n'
            "[mcp_servers.search.env]\n"
            'SEARCH_API_KEY = "fragment-env-secret"\n'
            "\n"
            f'[mcp_servers."{encoded_special_server_name}"]\n'
            'command = "/private/bin/special-command"\n\n\n'
        )
        normalized_fragment = fragment.rstrip("\n") + "\n"
        run_mock.side_effect = self.config_run_side_effect(fragment=fragment)

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            self.make_agent()._write_codex_config(
                task_id="search-agent-config",
                model="openrouter/xopglm52",
                reasoning_effort=None,
                wire_api=None,
                output_dir=output_dir,
            )
            host_config = (output_dir / "config.toml").read_text(encoding="utf-8")

        read_calls = self.search_agent_config_read_calls(run_mock)
        write_calls = self.config_write_calls(run_mock)
        self.assertEqual(len(read_calls), 1)
        self.assertEqual(len(write_calls), 1)
        container_config = write_calls[0].kwargs["input"]
        parsed_container = tomllib.loads(container_config)
        self.assertEqual(
            set(parsed_container["mcp_servers"]),
            {"search", special_server_name},
        )
        self.assertEqual(
            parsed_container["mcp_servers"]["search"]["env"]["SEARCH_API_KEY"],
            "fragment-env-secret",
        )
        self.assertTrue(container_config.endswith("\n\n" + normalized_fragment))

        try:
            parsed_host = tomllib.loads(host_config)
        except tomllib.TOMLDecodeError as error:
            self.fail(f"host config is invalid TOML: {error}")
        self.assertEqual(
            parsed_host["mcp_servers"],
            {"search": {}, special_server_name: {}},
        )
        for leaked_value in (
            "fragment-env-secret",
            "fragment-args-secret",
            "fragment-comment-secret",
            "/private/bin/search-command",
            "/private/bin/special-command",
        ):
            with self.subTest(leaked_value=leaked_value):
                self.assertNotIn(leaked_value, host_config)

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_missing_search_agent_fragment_preserves_legacy_config(
        self, run_mock
    ) -> None:
        run_mock.side_effect = self.config_run_side_effect(fragment_returncode=44)

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            self.make_agent()._write_codex_config(
                task_id="legacy-config",
                model="openrouter/xopglm52",
                reasoning_effort=None,
                wire_api=None,
                output_dir=output_dir,
            )
            host_config = (output_dir / "config.toml").read_text(encoding="utf-8")

        self.assertNotIn("mcp_servers", tomllib.loads(host_config))
        write_calls = self.config_write_calls(run_mock)
        self.assertEqual(len(write_calls), 1)
        self.assertNotIn(
            "mcp_servers",
            tomllib.loads(write_calls[0].kwargs["input"]),
        )

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_invalid_search_agent_fragments_fail_before_any_config_write(
        self, run_mock
    ) -> None:
        secret = "invalid-mcp-structure-secret"
        cases = {
            "empty": "",
            "invalid syntax": "mcp_servers = [\n",
            "extra top-level key": (
                "[mcp_servers.search]\n"
                'command = "search-agent"\n'
                "[unexpected]\n"
                "enabled = true\n"
            ),
            "wrong top-level key": "[search]\nenabled = true\n",
            "mcp_servers string": 'mcp_servers = "search-agent"\n',
            "empty mcp_servers table": "[mcp_servers]\n",
            "inline server string": (
                'mcp_servers = { search = "not-a-table" }\n'
                f"# {secret}\n"
            ),
            "inline server array": (
                'mcp_servers = { search = ["bad"] }\n'
                f"# {secret}\n"
            ),
            "scalar in mcp_servers table": (
                "[mcp_servers]\n"
                "enabled = true\n"
                f"# {secret}\n"
            ),
        }
        for name, fragment in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                run_mock.reset_mock()
                run_mock.side_effect = self.config_run_side_effect(fragment=fragment)

                with self.assertRaises(RuntimeError) as raised:
                    self.make_agent()._write_codex_config(
                        task_id="invalid-search-config",
                        model="openrouter/xopglm52",
                        reasoning_effort=None,
                        wire_api=None,
                        output_dir=output_dir,
                    )

                self.assertFalse((output_dir / "config.toml").exists())
                self.assertEqual(self.config_write_calls(run_mock), [])
                self.assertEqual(
                    len(self.search_agent_config_read_calls(run_mock)),
                    1,
                )
                self.assertEqual(run_mock.call_count, 1)
                if fragment:
                    self.assertNotIn(fragment, str(raised.exception))
                self.assertNotIn(secret, str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_search_agent_fragment_read_failure_does_not_leak_output(
        self, run_mock
    ) -> None:
        secret = "fake-search-agent-secret"
        run_mock.side_effect = self.config_run_side_effect(
            fragment=secret,
            fragment_returncode=5,
            fragment_stderr=f"read failed: {secret}",
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with self.assertRaises(RuntimeError) as raised:
                self.make_agent()._write_codex_config(
                    task_id="search-config-read-failure",
                    model="openrouter/xopglm52",
                    reasoning_effort=None,
                    wire_api=None,
                    output_dir=output_dir,
                )

            self.assertFalse((output_dir / "config.toml").exists())

        message = str(raised.exception)
        self.assertIn(SEARCH_AGENT_CONFIG_PATH, message)
        self.assertIn("read", message)
        self.assertIn("rc=5", message)
        self.assertNotIn(secret, message)
        self.assertEqual(self.config_write_calls(run_mock), [])

    def test_search_agent_config_path_is_fixed(self) -> None:
        self.assertEqual(
            getattr(astroncode_runner, "ASTRONCODE_SEARCH_AGENT_CONFIG_PATH", None),
            SEARCH_AGENT_CONFIG_PATH,
        )

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_merged_config_keeps_bearer_token_only_in_container_stdin(
        self, run_mock
    ) -> None:
        secret = "merged-provider-secret"
        fragment = "[mcp_servers.search]\ncommand = \"search-agent\"\n"
        run_mock.side_effect = self.config_run_side_effect(
            fragment=fragment,
            write_returncode=5,
            write_stdout=f"write output: {secret}",
            write_stderr=f"write error: {secret}",
        )

        with patch.dict(
            os.environ,
            {
                "ASTRONCODE_MODEL_PROVIDER": "astron-spark",
                "ASTRON_API_KEY": secret,
            },
            clear=False,
        ), tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with self.assertRaises(RuntimeError) as raised:
                self.make_agent()._write_codex_config(
                    task_id="merged-secret-isolation",
                    model="openrouter/xopglm52",
                    reasoning_effort=None,
                    wire_api=None,
                    output_dir=output_dir,
                )
            host_config = (output_dir / "config.toml").read_text(encoding="utf-8")

        write_calls = self.config_write_calls(run_mock)
        self.assertEqual(len(write_calls), 1)
        container_config = write_calls[0].kwargs["input"]
        parsed_container_config = tomllib.loads(container_config)
        self.assertEqual(
            parsed_container_config["model_providers"]["astron-spark"][
                "experimental_bearer_token"
            ],
            secret,
        )
        self.assertIn("search", parsed_container_config["mcp_servers"])
        self.assertNotIn(secret, host_config)
        self.assertNotIn(secret, str(raised.exception))
        for call in run_mock.call_args_list:
            for argument in call.args[0]:
                self.assertNotIn(secret, argument)
            for key, value in call.kwargs.items():
                if key != "input":
                    self.assertNotIn(secret, repr(value))

    @patch("src.agents.astroncode.runner.subprocess.run")
    def test_successful_config_write_logs_do_not_leak_credentials(
        self, run_mock
    ) -> None:
        secret = "successful-write-secret-never-log"
        run_mock.side_effect = self.config_run_side_effect(
            fragment='[mcp_servers.search]\ncommand = "search-agent"\n'
        )
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

    def test_default_image_is_v0_4(self) -> None:
        with patch.dict(os.environ, {"DOCKER_IMAGE_ASTRONCODE": ""}, clear=False):
            self.assertEqual(
                self.make_agent().image,
                "wildclawbench-astroncode-ubuntu:v0.4",
            )


if __name__ == "__main__":
    unittest.main()
