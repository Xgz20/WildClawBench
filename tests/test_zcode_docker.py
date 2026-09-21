from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


DOCKER_ROOT = Path(__file__).parents[1] / "docker" / "zcode"
V1_ROOT = DOCKER_ROOT / "v1"


class ZCodeDockerContractTests(unittest.TestCase):
    def test_image_uses_codex_v00_base_and_pinned_source(self) -> None:
        dockerfile = (V1_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", dockerfile)
        self.assertIn("ARG NODE_BUILDER_IMAGE=node:24.14.0-bookworm-slim", dockerfile)
        self.assertIn("FROM ${EVAL_BASE_IMAGE}", dockerfile)
        self.assertIn("ARG ZCODE_VERSION=0.1.0", dockerfile)
        self.assertIn("872ad960de7ec172591f7e1952f7849229f94521", dockerfile)
        self.assertIn("build-sea.mjs", dockerfile)
        self.assertIn("zcode --version", dockerfile)

    def test_manifest_and_builder_pin_v00_release(self) -> None:
        manifest = json.loads((DOCKER_ROOT / "versions.json").read_text())
        entry = manifest["versions"]["v0.0"]
        self.assertEqual(manifest["default"], "v0.0")
        self.assertEqual(entry["image"], "wildclawbench-zcode-ubuntu:v0.0")
        self.assertEqual(entry["build_args"]["ZCODE_VERSION"], "0.1.0")
        self.assertEqual(
            entry["build_args"]["EVAL_BASE_IMAGE"],
            "wildclawbench-codex-ubuntu:v0.0",
        )
        build = DOCKER_ROOT / "build.sh"
        self.assertTrue(os.access(build, os.X_OK))
        source = build.read_text()
        self.assertIn("versions.json", source)
        self.assertIn("docker save", source)
        self.assertIn("SKIP_SAVE", source)

    def test_entrypoint_uses_headless_stream_json_without_persisting_secrets(self) -> None:
        entrypoint = V1_ROOT / "wcb-zcode"
        source = entrypoint.read_text()
        self.assertTrue(os.access(entrypoint, os.X_OK))
        self.assertIn("--output-format stream-json", source)
        self.assertIn("--mode yolo", source)
        self.assertIn("openai-responses", source)
        self.assertIn("openai-chat-completions", source)
        self.assertIn("anthropic-messages", source)
        self.assertNotIn("sk-", source)

    def test_readme_documents_backend_and_trace_outputs(self) -> None:
        readme = (DOCKER_ROOT / "README.md").read_text()
        self.assertIn("--agent-backend zcode", readme)
        self.assertIn("--zcode-api openai-responses", readme)
        self.assertIn("zcode_trace.jsonl", readme)
        self.assertIn("chat.jsonl", readme)


if __name__ == "__main__":
    unittest.main()
