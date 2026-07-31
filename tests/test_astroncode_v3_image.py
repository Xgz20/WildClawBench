import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v3" / "Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "script" / "build-astroncode-image.sh"
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


class AstronCodeBuildScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = BUILD_SCRIPT.read_text(encoding="utf-8")
        logical_content = re.sub(r"\\\s*\n\s*", " ", cls.content)
        cls.compact_content = re.sub(r"\s+", " ", logical_content)

    def test_defaults_to_v3_image_tag(self):
        self.assertRegex(
            self.content,
            re.escape('IMAGE_TAG="${IMAGE_TAG:-v0.3}"'),
        )

    def test_defaults_to_v3_docker_variant(self):
        self.assertRegex(
            self.content,
            re.escape(
                'ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v3}"'
            ),
        )

    def test_documents_v3_default_and_v1_v2_overrides(self):
        self.assertRegex(
            self.content,
            r"(?m)^#\s*用法：bash script/build-astroncode-image\.sh\s*$",
        )
        self.assertRegex(
            self.content,
            r"(?m)^#\s*默认构建 v3.*AstronCode 0\.0\.13.*$",
        )
        for variant in ("v1", "v2"):
            with self.subTest(variant=variant):
                self.assertRegex(
                    self.content,
                    rf"(?m)^#\s*{variant}\s+覆盖：.*"
                    rf"ASTRONCODE_DOCKER_VARIANT={variant}.*"
                    r"bash script/build-astroncode-image\.sh\s*$",
                )

    def test_propagates_version_and_registry_build_args(self):
        for variable in ("ASTRON_CODE_VERSION", "NPM_REGISTRY"):
            with self.subTest(variable=variable):
                self.assertIn(f'"${{{variable}:-}}"', self.content)
                self.assertRegex(
                    self.content,
                    rf'--build-arg\s+"{variable}=\$\{{{variable}\}}"',
                )

    def test_propagates_proxy_build_args(self):
        proxy_contracts = {
            "HTTP_PROXY_INNER": ("http_proxy", "HTTP_PROXY"),
            "HTTPS_PROXY_INNER": ("https_proxy", "HTTPS_PROXY"),
            "NO_PROXY_INNER": ("no_proxy", "NO_PROXY"),
        }
        for source_variable, build_args in proxy_contracts.items():
            with self.subTest(source_variable=source_variable):
                self.assertIn(f'"${{{source_variable}:-}}"', self.content)
                for build_arg in build_args:
                    self.assertRegex(
                        self.content,
                        rf'--build-arg\s+"{build_arg}=\$\{{{source_variable}\}}"',
                    )

    def test_rejects_unknown_docker_variant(self):
        self.assertRegex(
            self.compact_content,
            r'if \[\[ ! -f "\$\{DOCKERFILE\}" \]\]; then',
        )
        self.assertIn(
            "Unknown AstronCode docker variant: ${ASTRONCODE_DOCKER_VARIANT}",
            self.content,
        )
        self.assertIn("Expected Dockerfile at: ${DOCKERFILE}", self.content)
        self.assertRegex(self.compact_content, r"Expected Dockerfile.*exit 1 fi")

    def test_whitelists_variants_before_constructing_paths(self):
        whitelist = re.search(
            r'case\s+"\$\{ASTRONCODE_DOCKER_VARIANT\}"\s+in\s+v1\|v2\|v3\)',
            self.compact_content,
        )
        self.assertIsNotNone(whitelist)
        self.assertLess(
            whitelist.start(),
            self.compact_content.index('BUILD_CONTEXT="${REPO_ROOT}'),
        )

    def test_traversal_variant_is_rejected_without_invoking_docker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            docker_marker = temp_path / "docker-called"
            docker_stub = bin_dir / "docker"
            docker_stub.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" > "${DOCKER_CALLED_MARKER:?}"\n'
                "exit 97\n",
                encoding="utf-8",
            )
            docker_stub.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "ASTRONCODE_DOCKER_VARIANT": "v3/../v2",
                    "DOCKER_CALLED_MARKER": str(docker_marker),
                    "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                ["bash", str(BUILD_SCRIPT)],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "Unknown AstronCode docker variant: v3/../v2",
                result.stderr,
            )
            docker_calls = (
                docker_marker.read_text(encoding="utf-8")
                if docker_marker.exists()
                else ""
            )
            self.assertFalse(
                docker_marker.exists(),
                f"docker was invoked with: {docker_calls}",
            )

    def test_docker_build_uses_selected_file_context_and_tag(self):
        self.assertRegex(
            self.content,
            r'BUILD_CONTEXT\s*=\s*"\$\{REPO_ROOT\}/docker/astroncode/'
            r'\$\{ASTRONCODE_DOCKER_VARIANT\}"',
        )
        self.assertRegex(
            self.content,
            r'DOCKERFILE\s*=\s*"\$\{BUILD_CONTEXT\}/Dockerfile"',
        )
        self.assertRegex(
            self.compact_content,
            r'docker build\s+-f "\$\{DOCKERFILE\}"\s+'
            r'"\$\{BUILD_ARGS\[@\]\}"\s+-t '
            r'"\$\{IMAGE_NAME\}:\$\{IMAGE_TAG\}"\s+'
            r'"\$\{BUILD_CONTEXT\}"',
        )

    def test_exports_selected_image_to_gzipped_tar_path(self):
        self.assertRegex(
            self.compact_content,
            r'docker save\s+"\$\{IMAGE_NAME\}:\$\{IMAGE_TAG\}"\s*'
            r'\|\s*gzip\s*>\s*"\$\{TAR_PATH\}"',
        )


if __name__ == "__main__":
    unittest.main()
