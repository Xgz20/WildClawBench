from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "docker" / "mimocode"


class MiMoCodeDockerTests(unittest.TestCase):
    def test_manifest_and_dockerfile_pin_cli_and_codex_base(self) -> None:
        manifest = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
        entry = manifest["versions"]["v0.0"]
        self.assertEqual(entry["build_args"]["MIMOCODE_VERSION"], "0.1.14")
        self.assertEqual(
            entry["build_args"]["EVAL_BASE_IMAGE"], "wildclawbench-codex-ubuntu:v0.0"
        )
        dockerfile = (ROOT / "v1" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("@mimo-ai/cli", dockerfile)
        self.assertIn("npm install --global", dockerfile)
        self.assertIn("wildclawbench-codex-ubuntu:v0.0", dockerfile)

    def test_entrypoint_supports_all_protocols_and_json_events(self) -> None:
        entrypoint = ROOT / "v1" / "wcb-mimocode"
        self.assertTrue(os.access(entrypoint, os.X_OK))
        source = entrypoint.read_text(encoding="utf-8")
        for api in (
            "openai-responses",
            "openai-chat-completions",
            "anthropic-messages",
        ):
            self.assertIn(api, source)
        self.assertIn("--format json", source)
        self.assertNotIn("sk-", source)


if __name__ == "__main__":
    unittest.main()
