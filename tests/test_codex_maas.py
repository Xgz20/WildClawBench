from __future__ import annotations

import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.codex.runner import CodexAgent


class CodexMaasTests(unittest.TestCase):
    def test_proxy_base_url_is_written_for_maas_candidate(self) -> None:
        agent = CodexAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas-api.example/v1",
        )
        config = tomllib.loads(
            agent._render_codex_config(
                model="openrouter/xopglm52",
                reasoning_effort="high",
                wire_api=None,
                request_base_url="http://127.0.0.1:18080",
            )
        )

        self.assertEqual(
            config["model_providers"]["openrouter"]["base_url"],
            "http://127.0.0.1:18080",
        )
        self.assertNotIn("model_max_output_tokens", config)

    def test_write_config_starts_proxy_with_common_limit(self) -> None:
        agent = CodexAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://maas-api.example/v1",
        )
        completed = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ", {"MAAS_MAX_TOKENS": "3072"}, clear=False
        ), patch(
            "src.agents.codex.runner.start_maas_request_proxy",
            return_value="http://127.0.0.1:18080",
        ) as start_proxy, patch(
            "src.agents.codex.runner.subprocess.run", return_value=completed
        ):
            output_dir = Path(temp_dir)
            agent._write_codex_config(
                task_id="codex-maas",
                model="openrouter/xopglm52",
                reasoning_effort="high",
                wire_api=None,
                output_dir=output_dir,
            )
            config = tomllib.loads(
                (output_dir / "config.toml").read_text(encoding="utf-8")
            )

        start_proxy.assert_called_once_with(
            "codex-maas",
            upstream_base_url="https://maas-api.example/v1",
            max_tokens=3072,
        )
        self.assertEqual(
            config["model_providers"]["openrouter"]["base_url"],
            "http://127.0.0.1:18080",
        )


if __name__ == "__main__":
    unittest.main()
