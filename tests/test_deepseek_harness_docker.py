from __future__ import annotations

import unittest
from pathlib import Path


DOCKER_ROOT = Path(__file__).parents[1] / "docker" / "deepseek-harness"


class DeepSeekHarnessDockerContractTests(unittest.TestCase):
    def test_dockerfile_pins_node_and_dsh_and_checks_version(self) -> None:
        dockerfile = (DOCKER_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(dockerfile, r"FROM\s+node:24(?:[-\w.]*)")
        self.assertIn("ARG DSH_VERSION=0.1.0-rc.6", dockerfile)
        self.assertIn("npm install -g", dockerfile)
        self.assertIn("@deepseek-ai/dsh@${DSH_VERSION}", dockerfile)
        self.assertIn("dsh --version", dockerfile)

    def test_dockerfile_includes_node_pty_native_build_prerequisites(self) -> None:
        dockerfile = (DOCKER_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(dockerfile, r"apt-get install[^\n]*python3")
        self.assertRegex(dockerfile, r"apt-get install[^\n]*make")
        self.assertRegex(dockerfile, r"apt-get install[^\n]*g\+\+")

    def test_entrypoint_contract_requires_model_and_chat_key_without_disabling_native_search(self) -> None:
        entrypoint = (DOCKER_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn(': "${DSH_MODEL_ID:', entrypoint)
        self.assertIn(': "${OPENROUTER_API_KEY:', entrypoint)
        self.assertIn("DSH_TELEMETRY_DISABLED=1", entrypoint)
        self.assertIn("session-title-llm", entrypoint)
        self.assertIn("disabled: true", entrypoint)
        self.assertIn("compression: none", entrypoint)
        self.assertIn("packChunks: false", entrypoint)
        self.assertIn("web-search-deepseek", entrypoint)
        self.assertIn("DEEPSEEK_API_KEY", entrypoint)
        self.assertIn("search: true", entrypoint)
        self.assertIn("fetch: false", entrypoint)
        self.assertNotIn("sk-", entrypoint)

    def test_entrypoint_applies_patch_before_forwarding_task(self) -> None:
        entrypoint = (DOCKER_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        launch = entrypoint.index("dsh --profile headless")
        patch = entrypoint.index("--patch", launch)
        forwarded_args = entrypoint.index('"$@"', patch)
        self.assertLess(patch, forwarded_args)


if __name__ == "__main__":
    unittest.main()
