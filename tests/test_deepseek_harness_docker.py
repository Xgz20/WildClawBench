from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


DOCKER_ROOT = Path(__file__).parents[1] / "docker" / "deepseek-harness"
V1_ROOT = DOCKER_ROOT / "v1"
V2_ROOT = DOCKER_ROOT / "v2"
V3_ROOT = DOCKER_ROOT / "v3"


class DeepSeekHarnessDockerContractTests(unittest.TestCase):
    def test_dockerfile_pins_node_and_dsh_and_checks_version(self) -> None:
        dockerfile = (V3_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", dockerfile)
        self.assertIn("ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim", dockerfile)
        self.assertIn("FROM ${NODE_RUNTIME_IMAGE} AS node-runtime", dockerfile)
        self.assertIn("FROM ${EVAL_BASE_IMAGE}", dockerfile)
        self.assertIn("COPY --from=node-runtime /usr/local/bin/node", dockerfile)
        self.assertIn("ARG DSH_VERSION=0.1.2-rc.1", dockerfile)
        self.assertIn("npm install -g", dockerfile)
        self.assertIn("@deepseek-ai/dsh@${DSH_VERSION}", dockerfile)
        self.assertIn("dsh --version", dockerfile)

    def test_version_manifest_preserves_history_and_selects_v3_by_default(self) -> None:
        manifest = json.loads(
            (DOCKER_ROOT / "versions.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["default"], "v0.2")
        self.assertEqual(set(manifest["versions"]), {"v0.0", "v0.1", "v0.2"})
        self.assertEqual(manifest["versions"]["v0.0"]["context"], "v1")
        self.assertEqual(
            manifest["versions"]["v0.0"]["build_args"]["DSH_VERSION"],
            "0.1.0-rc.6",
        )
        self.assertEqual(manifest["versions"]["v0.1"]["context"], "v2")
        self.assertEqual(
            manifest["versions"]["v0.1"]["build_args"]["DSH_VERSION"],
            "0.1.1-rc.2",
        )
        self.assertEqual(manifest["versions"]["v0.2"]["context"], "v3")
        self.assertEqual(
            manifest["versions"]["v0.2"]["build_args"]["DSH_VERSION"],
            "0.1.2-rc.1",
        )
        self.assertTrue((V1_ROOT / "Dockerfile").is_file())
        self.assertTrue((V2_ROOT / "Dockerfile").is_file())
        self.assertTrue((V3_ROOT / "Dockerfile").is_file())
        self.assertFalse((DOCKER_ROOT / "Dockerfile").exists())

    def test_canonical_builder_uses_manifest_and_exports_images(self) -> None:
        build = DOCKER_ROOT / "build.sh"
        source = build.read_text(encoding="utf-8")

        self.assertTrue(os.access(build, os.X_OK))
        self.assertIn("versions.json", source)
        self.assertIn("--version VERSION", source)
        self.assertIn("docker save", source)
        self.assertIn("SKIP_SAVE", source)
        self.assertIn("python3", source)
        self.assertIn("uv run python", source)

    def test_dockerfile_includes_node_pty_native_build_prerequisites(self) -> None:
        dockerfile = (V3_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(dockerfile, r"apt-get install[^\n]*python3")
        self.assertRegex(dockerfile, r"apt-get install[^\n]*make")
        self.assertRegex(dockerfile, r"apt-get install[^\n]*g\+\+")

    def test_entrypoint_contract_supports_optional_native_search(self) -> None:
        entrypoint = (V3_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn(': "${DSH_MODEL_ID:', entrypoint)
        self.assertIn(': "${OPENROUTER_API_KEY:', entrypoint)
        self.assertIn("DSH_TELEMETRY_DISABLED=1", entrypoint)
        self.assertIn("session-title-llm", entrypoint)
        self.assertIn("disabled: true", entrypoint)
        self.assertIn("compression: none", entrypoint)
        self.assertIn("packChunks: false", entrypoint)
        self.assertIn("web-search-deepseek", entrypoint)
        self.assertIn("DEEPSEEK_API_KEY", entrypoint)
        self.assertIn("process.env.DEEPSEEK_SEARCH_BASE_URL || undefined", entrypoint)
        self.assertIn("process.env.DEEPSEEK_SEARCH_MODEL_ID || undefined", entrypoint)
        self.assertIn('DEEPSEEK_SEARCH_ENABLED="${DEEPSEEK_SEARCH_ENABLED:-true}"', entrypoint)
        self.assertIn("DEEPSEEK_SEARCH_ENABLED must be true or false", entrypoint)
        self.assertIn(
            'disabled: !!js "process.env.DEEPSEEK_SEARCH_ENABLED === \'false\'"',
            entrypoint,
        )
        self.assertIn(
            'search: !!js "process.env.DEEPSEEK_SEARCH_ENABLED !== \'false\'"',
            entrypoint,
        )
        self.assertIn("fetch: false", entrypoint)
        self.assertNotIn("sk-", entrypoint)

    def test_entrypoint_declares_requested_reasoning_effort_on_custom_model(self) -> None:
        entrypoint = (V3_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn("reasoning: !!js process.env.DSH_REASONING || undefined", entrypoint)
        self.assertIn("reasoningEfforts: !!js", entrypoint)
        self.assertIn("[process.env.DSH_REASONING]", entrypoint)

    def test_entrypoint_uses_maas_max_tokens_request_field(self) -> None:
        entrypoint = (V3_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn("process.env.DSH_MAX_TOKENS", entrypoint)
        self.assertIn(
            "compat: !!js \"process.env.DSH_MAX_TOKENS && "
            "(process.env.DSH_API || 'openai-completions') === "
            "'openai-completions' ? { maxTokensField: 'max_tokens' } : undefined\"",
            entrypoint,
        )
        self.assertNotIn(
            "compat: !!js \"process.env.DSH_MAX_TOKENS ? "
            "{ maxTokensField: 'max_tokens' } : undefined\"",
            entrypoint,
        )

    def test_entrypoint_selects_api_from_environment_with_chat_default(self) -> None:
        entrypoint = (V3_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        self.assertIn("process.env.DSH_API || 'openai-completions'", entrypoint)

    def test_entrypoint_applies_patch_before_forwarding_task(self) -> None:
        entrypoint = (V3_ROOT / "wcb-dsh").read_text(encoding="utf-8")

        launch = entrypoint.index("dsh --profile headless")
        patch = entrypoint.index("--patch", launch)
        forwarded_args = entrypoint.index('"$@"', patch)
        self.assertLess(patch, forwarded_args)

    def test_readme_documents_formal_backend_image_and_command(self) -> None:
        readme = (DOCKER_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("wildclawbench-deepseek-harness-ubuntu:v0.2", readme)
        self.assertIn("DOCKER_IMAGE_DEEPSEEK_HARNESS", readme)
        self.assertIn("eval/run_batch.py", readme)
        self.assertIn("--agent-backend deepseek-harness", readme)
        self.assertIn("--dsh-api openai-completions", readme)
        self.assertIn("openai-completions", readme)
        self.assertIn("openai-responses", readme)
        self.assertIn("DEEPSEEK_SEARCH_ENABLED=false", readme)


if __name__ == "__main__":
    unittest.main()
