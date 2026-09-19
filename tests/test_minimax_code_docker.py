from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


DOCKER_ROOT = Path(__file__).parents[1] / "docker" / "minimax-code"
V1_ROOT = DOCKER_ROOT / "v1"


class MiniMaxCodeDockerContractTests(unittest.TestCase):
    def test_image_uses_codex_v00_base_and_pinned_mcode(self) -> None:
        dockerfile = (V1_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", dockerfile)
        self.assertIn("ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim", dockerfile)
        self.assertIn("FROM ${EVAL_BASE_IMAGE}", dockerfile)
        self.assertIn("ARG MCODE_VERSION=0.4.12", dockerfile)
        self.assertIn('"@minimax-ai/code@${MCODE_VERSION}"', dockerfile)
        self.assertIn("mcode --version", dockerfile)

    def test_manifest_and_builder_pin_v00_release(self) -> None:
        manifest = json.loads((DOCKER_ROOT / "versions.json").read_text(encoding="utf-8"))
        entry = manifest["versions"]["v0.0"]

        self.assertEqual(manifest["default"], "v0.0")
        self.assertEqual(entry["image"], "wildclawbench-minimax-code-ubuntu:v0.0")
        self.assertEqual(entry["context"], "v1")
        self.assertEqual(entry["dockerfile"], "v1/Dockerfile")
        self.assertEqual(entry["build_args"]["MCODE_VERSION"], "0.4.12")
        self.assertEqual(
            entry["build_args"]["EVAL_BASE_IMAGE"],
            "wildclawbench-codex-ubuntu:v0.0",
        )

        build = DOCKER_ROOT / "build.sh"
        source = build.read_text(encoding="utf-8")
        self.assertTrue(os.access(build, os.X_OK))
        self.assertIn("versions.json", source)
        self.assertIn("docker save", source)
        self.assertIn("SKIP_SAVE", source)

    def test_entrypoint_preserves_native_trace_contract_and_keeps_effort_default(self) -> None:
        entrypoint = (V1_ROOT / "wcb-mcode").read_text(encoding="utf-8")

        self.assertTrue(os.access(V1_ROOT / "wcb-mcode", os.X_OK))
        self.assertIn('mcode provider add', entrypoint)
        self.assertIn('--output-format stream-json', entrypoint)
        self.assertIn('--diagnostics-dir /tmp/mcode-diagnostics', entrypoint)
        self.assertIn('--output-last-message /tmp/mcode-last-message.txt', entrypoint)
        self.assertIn('defaultModel:', entrypoint)
        self.assertIn('--output-limit "${MCODE_OUTPUT_LIMIT}"', entrypoint)
        self.assertNotIn('\n  --effort', entrypoint)
        self.assertNotIn("sk-", entrypoint)

    def test_readme_documents_backend_protocols_and_trace_outputs(self) -> None:
        readme = (DOCKER_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("--agent-backend minimax-code", readme)
        self.assertIn("--mcode-api openai-responses", readme)
        self.assertIn("openai-completions", readme)
        self.assertIn("anthropic-messages", readme)
        self.assertIn("minimax_code_trace.jsonl", readme)
        self.assertIn("chat.jsonl", readme)


if __name__ == "__main__":
    unittest.main()
