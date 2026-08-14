from __future__ import annotations

import unittest
from pathlib import Path


DOCKER_ROOT = Path(__file__).parents[1] / "docker" / "deepseek-harness"


class DeepSeekHarnessDockerContractTests(unittest.TestCase):
    def test_dockerfile_pins_node_and_dsh_and_checks_version(self) -> None:
        dockerfile = (DOCKER_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", dockerfile)
        self.assertIn("ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim", dockerfile)
        self.assertIn("FROM ${NODE_RUNTIME_IMAGE} AS node-runtime", dockerfile)
        self.assertIn("FROM ${EVAL_BASE_IMAGE}", dockerfile)
        self.assertIn("COPY --from=node-runtime /usr/local/bin/node", dockerfile)
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

    def test_entrypoint_declares_requested_reasoning_effort_on_custom_model(self) -> None:
        entrypoint = (DOCKER_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn("reasoning: !!js process.env.DSH_REASONING || undefined", entrypoint)
        self.assertIn("reasoningEfforts: !!js", entrypoint)
        self.assertIn("[process.env.DSH_REASONING]", entrypoint)

    def test_entrypoint_selects_api_from_environment_with_chat_default(self) -> None:
        entrypoint = (DOCKER_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn("process.env.DSH_API || 'openai-completions'", entrypoint)

    def test_entrypoint_applies_patch_before_forwarding_task(self) -> None:
        entrypoint = (DOCKER_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        launch = entrypoint.index("dsh --profile headless")
        patch = entrypoint.index("--patch", launch)
        forwarded_args = entrypoint.index('"$@"', patch)
        self.assertLess(patch, forwarded_args)

    def test_readme_documents_formal_backend_image_and_command(self) -> None:
        readme = (DOCKER_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("wildclawbench-deepseek-harness-ubuntu:v0.0", readme)
        self.assertIn("DOCKER_IMAGE_DEEPSEEK_HARNESS", readme)
        self.assertIn("eval/run_batch.py", readme)
        self.assertIn("--agent-backend deepseek-harness", readme)
        self.assertIn("--dsh-api openai-completions", readme)
        self.assertIn("openai-completions", readme)
        self.assertIn("openai-responses", readme)


if __name__ == "__main__":
    unittest.main()
