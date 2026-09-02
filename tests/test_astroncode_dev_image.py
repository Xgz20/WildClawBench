import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v5-dev" / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "docker" / "astroncode" / "versions.json"


class AstronCodeDevImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = DOCKERFILE.read_text(encoding="utf-8")
        cls.manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))

    def test_inherits_v05_capabilities_and_installs_dev_cli(self) -> None:
        self.assertIn(
            "FROM wildclawbench-astroncode-ubuntu:v0.5",
            self.content,
        )
        self.assertIn("ARG ASTRON_CODE_DEV_VERSION=0.0.35", self.content)
        self.assertIn(
            'npm install -g "@iflytek/astron-code-dev@${ASTRON_CODE_DEV_VERSION}"',
            self.content,
        )
        self.assertIn("command -v astron-code-dev", self.content)
        self.assertIn("astron-code-dev --version", self.content)
        self.assertIn("! command -v astron-code", self.content)

    def test_does_not_bake_credentials_or_model_catalog(self) -> None:
        forbidden = (
            "ASTRON_API_KEY",
            "ASTRON_SPARK_API_KEY",
            "ASTRON_UID",
            "ONE_IFLYTEK_API_KEY",
            "OPENROUTER_API_KEY",
            "ASTRON_MODELS_BASE_URL",
            "astronstudio-api-volces-prod.xf-yun.com",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.content)

    def test_manifest_registers_v05_dev_without_changing_default(self) -> None:
        self.assertEqual("v0.6", self.manifest["default"])
        entry = self.manifest["versions"]["v0.5-dev"]
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.5-dev",
            entry["image"],
        )
        self.assertEqual("v5-dev", entry["context"])
        self.assertEqual("v5-dev/Dockerfile", entry["dockerfile"])
        self.assertEqual("astron-code-dev", entry["cli_command"])
        self.assertEqual(
            {"ASTRON_CODE_DEV_VERSION": "0.0.35"},
            entry["build_args"],
        )


if __name__ == "__main__":
    unittest.main()
