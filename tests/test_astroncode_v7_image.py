import json
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = REPO_ROOT / "docker" / "astroncode" / "v7"
DOCKERFILE = IMAGE_DIR / "Dockerfile"
SEARCH_AGENT_CONFIG = IMAGE_DIR / "search-agent.config.toml"
SEARCH_AGENT_VERIFIER = IMAGE_DIR / "verify_search_agent.py"
BUILD_MANIFEST = REPO_ROOT / "docker" / "astroncode" / "versions.json"


class AstronCodeV7ImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = DOCKERFILE.read_text(encoding="utf-8")
        cls.config = tomllib.loads(SEARCH_AGENT_CONFIG.read_text(encoding="utf-8"))
        cls.verifier = SEARCH_AGENT_VERIFIER.read_text(encoding="utf-8")
        cls.manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))

    def test_pins_astroncode_0042_on_node22_codex_base(self) -> None:
        self.assertIn("FROM wildclawbench-codex-ubuntu:v0.0", self.content)
        self.assertIn("ARG ASTRON_CODE_VERSION=0.0.42", self.content)
        self.assertIn("ARG NODEJS_VERSION=22.23.2-1nodesource1", self.content)
        self.assertIn('"@iflytek/astron-code@${ASTRON_CODE_VERSION}"', self.content)
        self.assertIn("astron-code --version", self.content)
        self.assertIn("rm -rf /root/.acode", self.content)
        self.assertIn("if (major < 22) process.exit(1)", self.content)

    def test_bundles_only_the_new_local_web_fetch_mcp(self) -> None:
        server = self.config["mcp_servers"]["web_fetch"]
        self.assertEqual(
            {
                "enabled": True,
                "command": "/opt/astroncode/web-fetch/start-mcp.sh",
                "startup_timeout_sec": 60,
                "tool_timeout_sec": 300,
                "default_tools_approval_mode": "approve",
            },
            server,
        )
        self.assertEqual({"web_fetch"}, set(self.config["mcp_servers"]))
        self.assertIn("COPY --from=web_fetch", self.content)
        self.assertIn("sha256sum --check --quiet -", self.content)
        self.assertIn("python\\/share\\/terminfo", self.content)
        self.assertIn("./check-system-deps.sh", self.content)
        self.assertNotIn("@iflytek/install-search-updater", self.content)
        self.assertNotIn("install-search", self.content)

    def test_build_verifier_checks_all_tools_and_fetches_a_local_page(self) -> None:
        for tool_name in (
            "open_session",
            "close_session",
            "list_sessions",
            "get",
            "fetch",
            "stealthy_fetch",
            "screenshot",
        ):
            with self.subTest(tool_name=tool_name):
                self.assertIn(f'"{tool_name}"', self.verifier)
        self.assertIn('session.call_tool("fetch", {"url": url})', self.verifier)
        self.assertIn("ThreadingHTTPServer", self.verifier)
        self.assertNotIn('require_tool("web-search"', self.verifier)

    def test_preserves_ppt_capabilities(self) -> None:
        for fragment in (
            "libreoffice-impress",
            "soffice --version",
            "import fitz",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.content)

    def test_does_not_bake_credentials_or_remote_connector_config(self) -> None:
        for fragment in (
            "ASTRON_API_KEY",
            "ASTRON_SPARK_API_KEY",
            "ONE_IFLYTEK_API_KEY",
            "OPENROUTER_API_KEY",
            "ASTRON_MODELS_BASE_URL",
            "bootstrap_personal_access_token",
            "web-search@astron-plugin-hub",
            "mcp_servers.acode_apps",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.content)
                self.assertNotIn(fragment, SEARCH_AGENT_CONFIG.read_text(encoding="utf-8"))

    def test_manifest_registers_v07_without_changing_default(self) -> None:
        self.assertEqual("v0.6", self.manifest["default"])
        entry = self.manifest["versions"]["v0.7"]
        self.assertEqual("wildclawbench-astroncode-ubuntu:v0.7", entry["image"])
        self.assertEqual("v7", entry["context"])
        self.assertEqual("v7/Dockerfile", entry["dockerfile"])
        self.assertEqual("linux/amd64", entry["platform"])
        self.assertEqual(
            {
                "ASTRON_CODE_VERSION": "0.0.42",
                "NODEJS_VERSION": "22.23.2-1nodesource1",
            },
            entry["build_args"],
        )


if __name__ == "__main__":
    unittest.main()
