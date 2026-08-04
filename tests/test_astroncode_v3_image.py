import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v3" / "Dockerfile"
CREDENTIAL_ENV_NAMES = (
    "ASTRON_API_KEY",
    "ASTRON_SPARK_API_KEY",
    "ONE_IFLYTEK_API_KEY",
    "OPENROUTER_API_KEY",
    "experimental_bearer_token",
)


def docker_instructions(content):
    logical_content = re.sub(r"\\\s*\n\s*", " ", content)
    return [
        line.strip()
        for line in logical_content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class AstronCodeV3DockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (
            DOCKERFILE.read_text(encoding="utf-8") if DOCKERFILE.exists() else ""
        )
        cls.instructions = docker_instructions(cls.content)
        cls.instruction_content = "\n".join(cls.instructions)

    def test_dockerfile_exists(self):
        self.assertTrue(DOCKERFILE.is_file(), f"missing {DOCKERFILE}")

    def test_uses_codex_base_image(self):
        self.assertRegex(
            self.instruction_content,
            r"(?m)^FROM wildclawbench-codex-ubuntu:v0\.0\s*$",
        )

    def test_defaults_to_astron_code_0_0_13(self):
        self.assertRegex(
            self.instruction_content,
            r"(?m)^ARG ASTRON_CODE_VERSION=0\.0\.13\s*$",
        )

    def test_installs_exact_requested_package_from_registry(self):
        self.assertIn(
            "ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/",
            self.instruction_content,
        )
        self.assertIn(
            "npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true",
            self.instruction_content,
        )
        self.assertIn(
            'npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}"',
            self.instruction_content,
        )
        self.assertIn('--registry="${NPM_REGISTRY}"', self.instruction_content)

    def test_verifies_installed_version_during_build(self):
        self.assertIn("astron-code --version", self.instruction_content)

    def test_prepares_private_acode_home_without_runtime_config(self):
        self.assertNotRegex(self.instruction_content, r"(?im)^\s*(COPY|ADD)\s")

        env_instructions = "\n".join(
            instruction
            for instruction in self.instructions
            if re.match(r"(?i)^ENV\b", instruction)
        )
        for env_name in CREDENTIAL_ENV_NAMES:
            with self.subTest(env_name=env_name):
                self.assertNotRegex(
                    env_instructions,
                    rf"(?i)\b{re.escape(env_name)}\b\s*(?:=|\s|$)",
                )

        run_instructions = "\n".join(
            instruction
            for instruction in self.instructions
            if re.match(r"(?i)^RUN\b", instruction)
        )
        self.assertNotRegex(run_instructions, r"(?i)\bconfig\.toml\b")

        install_instruction = next(
            instruction
            for instruction in self.instructions
            if instruction.startswith("RUN ")
            and "npm install -g" in instruction
        )
        remove_runtime_config = "rm -rf /root/.acode"
        recreate_private_home = "install -d -m 700 /root/.acode"
        self.assertIn(remove_runtime_config, install_instruction)
        self.assertIn(recreate_private_home, install_instruction)
        self.assertLess(
            install_instruction.index("npm install -g"),
            install_instruction.index("astron-code --version"),
        )
        self.assertLess(
            install_instruction.index("astron-code --version"),
            install_instruction.index(remove_runtime_config),
        )
        self.assertLess(
            install_instruction.index(remove_runtime_config),
            install_instruction.index(recreate_private_home),
        )


if __name__ == "__main__":
    unittest.main()
