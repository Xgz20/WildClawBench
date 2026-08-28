from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "claudecode" / "v3" / "Dockerfile"
MANIFEST = REPO_ROOT / "docker" / "claudecode" / "versions.json"


class ClaudeCodeImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_pins_latest_official_cli_and_clean_base(self) -> None:
        entry = self.manifest["versions"]["v0.3"]
        self.assertEqual("2.1.250", entry["build_args"]["CLAUDE_CODE_VERSION"])
        self.assertEqual(
            "wildclawbench-codex-ubuntu:v0.0",
            entry["build_args"]["EVAL_BASE_IMAGE"],
        )
        self.assertNotIn("v0.2-patched", self.dockerfile)
        self.assertIn(
            "ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0",
            self.dockerfile,
        )

    def test_installs_global_cli_with_node_24(self) -> None:
        self.assertIn(
            "ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim",
            self.dockerfile,
        )
        self.assertIn("node --version | grep '^v24\\.'", self.dockerfile)
        self.assertIn(
            '"@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"',
            self.dockerfile,
        )
        self.assertIn(
            'claude --version | grep "${CLAUDE_CODE_VERSION}"',
            self.dockerfile,
        )

    def test_preserves_evaluation_auxiliary_tools(self) -> None:
        for command in ("google-chrome", "agent-browser", "git", "jq"):
            with self.subTest(command=command):
                self.assertIn(f"command -v {command}", self.dockerfile)
        self.assertIn("import fitz, playwright", self.dockerfile)

    def test_ships_no_credentials_or_legacy_env_file(self) -> None:
        self.assertNotRegex(
            self.dockerfile,
            r"(?i)(ANTHROPIC_API_KEY|OPENROUTER_API_KEY|sk-[a-z0-9])",
        )
        self.assertNotRegex(self.dockerfile, r"(?im)^\s*(COPY|ADD)\s+.*\.env")
        self.assertIn("test ! -e /claude_code/.env", self.dockerfile)
        self.assertIn("rm -rf /root/.claude /root/.claude.json", self.dockerfile)


if __name__ == "__main__":
    unittest.main()
