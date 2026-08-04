"""Codex CLI 升级层镜像的静态契约测试。

只校验 Dockerfile / 构建脚本的文本契约，不触发 docker build。
"""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "codex" / "Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "script" / "build-codex-image.sh"
TAOBAO_REGISTRY = "https://registry.npmmirror.com"
CREDENTIAL_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "ASTRON_API_KEY",
    "BRAVE_API_KEY",
)


def docker_instructions(content):
    logical_content = re.sub(r"\\\s*\n\s*", " ", content)
    return [
        line.strip()
        for line in logical_content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class CodexUpgradeDockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (
            DOCKERFILE.read_text(encoding="utf-8") if DOCKERFILE.exists() else ""
        )
        cls.instructions = docker_instructions(cls.content)
        cls.instruction_content = "\n".join(cls.instructions)

    def test_dockerfile_exists(self):
        self.assertTrue(DOCKERFILE.is_file(), f"missing {DOCKERFILE}")

    def test_builds_on_official_eval_base_image(self):
        self.assertRegex(
            self.instruction_content,
            r"(?m)^ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0\.0\s*$",
        )
        self.assertRegex(
            self.instruction_content,
            r"(?m)^FROM \$\{EVAL_BASE_IMAGE\}\s*$",
        )

    def test_pins_codex_version(self):
        self.assertRegex(
            self.instruction_content,
            r"(?m)^ARG CODEX_VERSION=0\.146\.0\s*$",
        )

    def test_defaults_to_taobao_npm_registry(self):
        self.assertRegex(
            self.instruction_content,
            rf"(?m)^ARG NPM_REGISTRY={re.escape(TAOBAO_REGISTRY)}/?\s*$",
        )
        self.assertNotIn("registry.npmjs.org", self.instruction_content)
        self.assertNotIn("depend.iflytek.com", self.instruction_content)

    def test_persists_registry_into_image_npmrc(self):
        self.assertIn(
            'npm config set registry "${NPM_REGISTRY}"',
            self.instruction_content,
        )

    def test_replaces_old_cli_with_pinned_version_from_registry(self):
        self.assertIn(
            "npm uninstall -g @openai/codex >/dev/null 2>&1 || true",
            self.instruction_content,
        )
        self.assertIn(
            'npm install -g "@openai/codex@${CODEX_VERSION}"',
            self.instruction_content,
        )
        self.assertIn('--registry="${NPM_REGISTRY}"', self.instruction_content)

    def test_verifies_installed_version_during_build(self):
        self.assertIn("codex --version", self.instruction_content)

    def test_uninstall_precedes_install_and_verification(self):
        install_instruction = next(
            instruction
            for instruction in self.instructions
            if instruction.startswith("RUN ") and "npm install -g" in instruction
        )
        self.assertLess(
            install_instruction.index("npm uninstall -g @openai/codex"),
            install_instruction.index("npm install -g"),
        )
        self.assertLess(
            install_instruction.index("npm install -g"),
            install_instruction.index("codex --version"),
        )

    def test_resets_baked_codex_home_after_verification(self):
        install_instruction = next(
            instruction
            for instruction in self.instructions
            if instruction.startswith("RUN ") and "npm install -g" in instruction
        )
        remove_runtime_config = "rm -rf /root/.codex"
        recreate_private_home = "install -d -m 700 /root/.codex"
        self.assertIn(remove_runtime_config, install_instruction)
        self.assertIn(recreate_private_home, install_instruction)
        self.assertLess(
            install_instruction.index("codex --version"),
            install_instruction.index(remove_runtime_config),
        )
        self.assertLess(
            install_instruction.index(remove_runtime_config),
            install_instruction.index(recreate_private_home),
        )

    def test_ships_no_runtime_config_or_credentials(self):
        self.assertNotRegex(self.instruction_content, r"(?im)^\s*(COPY|ADD)\s")

        run_instructions = "\n".join(
            instruction
            for instruction in self.instructions
            if re.match(r"(?i)^RUN\b", instruction)
        )
        self.assertNotRegex(run_instructions, r"(?i)\bconfig\.toml\b")

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


class CodexBuildScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (
            BUILD_SCRIPT.read_text(encoding="utf-8") if BUILD_SCRIPT.exists() else ""
        )
        logical_content = re.sub(r"\\\s*\n\s*", " ", cls.content)
        cls.compact_content = re.sub(r"\s+", " ", logical_content)

    def test_build_script_exists_and_is_executable(self):
        self.assertTrue(BUILD_SCRIPT.is_file(), f"missing {BUILD_SCRIPT}")
        self.assertTrue(os.access(BUILD_SCRIPT, os.X_OK), "build script not executable")

    def test_defaults_to_upgraded_image_tag(self):
        self.assertIn('IMAGE_NAME="wildclawbench-codex-ubuntu"', self.content)
        self.assertIn('IMAGE_TAG="${IMAGE_TAG:-v0.1}"', self.content)

    def test_defaults_to_official_base_image(self):
        self.assertIn(
            'BASE_IMAGE="${EVAL_BASE_IMAGE:-wildclawbench-codex-ubuntu:v0.0}"',
            self.content,
        )

    def test_uses_codex_build_context_and_dockerfile(self):
        self.assertIn('BUILD_CONTEXT="${REPO_ROOT}/docker/codex"', self.content)
        self.assertIn('DOCKERFILE="${BUILD_CONTEXT}/Dockerfile"', self.content)

    def test_propagates_version_and_registry_build_args(self):
        for variable in ("CODEX_VERSION", "NPM_REGISTRY"):
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

    def test_pins_base_image_into_build_args(self):
        self.assertRegex(
            self.compact_content,
            r'BUILD_ARGS=\(--build-arg "EVAL_BASE_IMAGE=\$\{BASE_IMAGE\}"\)',
        )

    def test_docker_build_uses_selected_file_context_and_tag(self):
        self.assertRegex(
            self.compact_content,
            r'docker build\s+-f "\$\{DOCKERFILE\}"\s+'
            r'"\$\{BUILD_ARGS\[@\]\}"\s+-t '
            r'"\$\{IMAGE_NAME\}:\$\{IMAGE_TAG\}"\s+'
            r'"\$\{BUILD_CONTEXT\}"',
        )

    def test_exports_image_to_gzipped_tar_path(self):
        self.assertIn(
            'TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"',
            self.content,
        )
        self.assertRegex(
            self.compact_content,
            r'docker save\s+"\$\{IMAGE_NAME\}:\$\{IMAGE_TAG\}"\s*'
            r'\|\s*gzip\s*>\s*"\$\{TAR_PATH\}"',
        )

    def test_supports_skipping_tar_export(self):
        self.assertRegex(self.compact_content, r'\$\{SKIP_SAVE:-\}" == "1"')

    def test_reports_enabling_env_var(self):
        self.assertIn("DOCKER_IMAGE_CODEX", self.content)

    def test_rejects_self_referential_base_image(self):
        self.assertRegex(
            self.compact_content,
            r'if \[\[ "\$\{BASE_IMAGE\}" == "\$\{IMAGE_NAME\}:\$\{IMAGE_TAG\}" \]\]',
        )

    def test_self_referential_base_is_rejected_without_invoking_docker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            docker_marker = temp_path / "docker-called"
            docker_stub = bin_dir / "docker"
            docker_stub.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "${DOCKER_CALLED_MARKER:?}"\n'
                "exit 97\n",
                encoding="utf-8",
            )
            docker_stub.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "EVAL_BASE_IMAGE": "wildclawbench-codex-ubuntu:v0.1",
                    "IMAGE_TAG": "v0.1",
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
            self.assertIn("on top of itself", result.stderr)
            docker_calls = (
                docker_marker.read_text(encoding="utf-8")
                if docker_marker.exists()
                else ""
            )
            self.assertFalse(
                docker_marker.exists(),
                f"docker was invoked with: {docker_calls}",
            )

    def test_missing_base_image_fails_before_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            docker_marker = temp_path / "docker-called"
            docker_stub = bin_dir / "docker"
            # image inspect 失败（模拟底座未加载），build/save 若被调用则记录。
            docker_stub.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "${DOCKER_CALLED_MARKER:?}"\n'
                'if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then exit 1; fi\n'
                "exit 0\n",
                encoding="utf-8",
            )
            docker_stub.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
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
            self.assertIn("Base image not found locally", result.stderr)
            docker_calls = (
                docker_marker.read_text(encoding="utf-8")
                if docker_marker.exists()
                else ""
            )
            self.assertNotIn("build", docker_calls)
            self.assertNotIn("save", docker_calls)


class CodexRunnerDefaultImageTest(unittest.TestCase):
    """runner 默认镜像须与构建脚本产出的 tag 一致（v0.1）。"""

    @classmethod
    def setUpClass(cls):
        cls.runner_source = (REPO_ROOT / "src" / "agents" / "codex" / "runner.py").read_text(
            encoding="utf-8"
        )
        cls.build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    def test_runner_defaults_to_upgraded_image(self):
        self.assertIn(
            'os.environ.get("DOCKER_IMAGE_CODEX") or "wildclawbench-codex-ubuntu:v0.1"',
            self.runner_source,
        )

    def test_runner_default_matches_build_script_output_tag(self):
        name = re.search(r'IMAGE_NAME="([^"]+)"', self.build_script)
        tag = re.search(r'IMAGE_TAG="\$\{IMAGE_TAG:-([^}]+)\}"', self.build_script)
        self.assertIsNotNone(name, "build script lost IMAGE_NAME")
        self.assertIsNotNone(tag, "build script lost IMAGE_TAG default")
        expected = f"{name.group(1)}:{tag.group(1)}"
        self.assertIn(f'or "{expected}"', self.runner_source)

    def test_env_example_enables_upgraded_image(self):
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(
            env_example,
            r"(?m)^DOCKER_IMAGE_CODEX=wildclawbench-codex-ubuntu:v0\.1\s*$",
        )


if __name__ == "__main__":
    unittest.main()
