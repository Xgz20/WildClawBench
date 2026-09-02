import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v6" / "Dockerfile"
SEARCH_AGENT_VERIFIER = DOCKERFILE.with_name("verify_search_agent.py")
BUILD_MANIFEST = REPO_ROOT / "docker" / "astroncode" / "versions.json"


class AstronCodeV6ImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = DOCKERFILE.read_text(encoding="utf-8")
        cls.verifier = SEARCH_AGENT_VERIFIER.read_text(encoding="utf-8")
        cls.manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))

    def test_pins_astroncode_0042_on_node22_codex_base(self) -> None:
        self.assertIn("FROM wildclawbench-codex-ubuntu:v0.0", self.content)
        self.assertIn("ARG ASTRON_CODE_VERSION=0.0.42", self.content)
        self.assertIn("ARG NODEJS_VERSION=22.23.2-1nodesource1", self.content)
        self.assertIn('"@iflytek/astron-code@${ASTRON_CODE_VERSION}"', self.content)
        self.assertIn("astron-code --version", self.content)
        self.assertIn("if (major < 22) process.exit(1)", self.content)

    def test_preserves_search_fetch_browser_and_ppt_capabilities(self) -> None:
        for fragment in (
            "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}",
            "install-search doctor --full",
            "/opt/astroncode/search-agent.config.toml",
            "PLAYWRIGHT_BROWSERS_PATH",
            "libreoffice-impress",
            "soffice --version",
            "import fitz",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.content)
        self.assertIn('require_tool("web-search", "web-search")', self.verifier)
        self.assertIn('call_tool("fetch"', self.verifier)

    def test_does_not_bake_credentials_or_model_catalog(self) -> None:
        for fragment in (
            "ASTRON_API_KEY",
            "ASTRON_SPARK_API_KEY",
            "ONE_IFLYTEK_API_KEY",
            "OPENROUTER_API_KEY",
            "ASTRON_MODELS_BASE_URL",
            "astronstudio-api-volces-prod.xf-yun.com",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.content)

    def test_manifest_registers_v06_as_default(self) -> None:
        self.assertEqual("v0.6", self.manifest["default"])
        entry = self.manifest["versions"]["v0.6"]
        self.assertEqual("wildclawbench-astroncode-ubuntu:v0.6", entry["image"])
        self.assertEqual("v6", entry["context"])
        self.assertEqual("v6/Dockerfile", entry["dockerfile"])
        self.assertEqual(
            {
                "ASTRON_CODE_VERSION": "0.0.42",
                "NODEJS_VERSION": "22.23.2-1nodesource1",
                "SEARCH_UPDATER_VERSION": "0.1.17",
            },
            entry["build_args"],
        )


if __name__ == "__main__":
    unittest.main()
