import gzip
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v4" / "Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "script" / "build-astroncode-image.sh"
CREDENTIAL_AND_RUNTIME_ENV_NAMES = (
    "ASTRON_API_KEY",
    "ASTRON_SPARK_API_KEY",
    "ONE_IFLYTEK_API_KEY",
    "OPENROUTER_API_KEY",
    "experimental_bearer_token",
    "ASTRON_MODEL",
    "ASTRONCODE_MODEL_PROVIDER",
    "ASTRON_MODELS_BASE_URL",
)
BUILD_OVERRIDE_ENV_NAMES = (
    "IMAGE_TAG",
    "ASTRONCODE_DOCKER_VARIANT",
    "ASTRON_CODE_VERSION",
    "SEARCH_UPDATER_VERSION",
    "NPM_REGISTRY",
    "HTTP_PROXY_INNER",
    "HTTPS_PROXY_INNER",
    "NO_PROXY_INNER",
)


def docker_instructions(content):
    logical_content = re.sub(r"\\\s*\n\s*", " ", content)
    return [
        line.strip()
        for line in logical_content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class AstronCodeV4DockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (
            DOCKERFILE.read_text(encoding="utf-8") if DOCKERFILE.exists() else ""
        )
        cls.instructions = docker_instructions(cls.content)
        cls.instruction_content = "\n".join(cls.instructions)
        cls.run_instructions = [
            instruction
            for instruction in cls.instructions
            if instruction.startswith("RUN ")
        ]

    def test_dockerfile_exists(self):
        self.assertTrue(DOCKERFILE.is_file(), f"missing {DOCKERFILE}")

    def test_uses_codex_base_image_directly(self):
        self.assertRegex(
            self.instruction_content,
            r"(?m)^FROM wildclawbench-codex-ubuntu:v0\.0\s*$",
        )
        self.assertNotIn("wildclawbench-astroncode-ubuntu:v0.3", self.content)

    def test_declares_required_build_arg_defaults(self):
        expected_args = (
            "ARG ASTRON_CODE_VERSION=0.0.13",
            "ARG SEARCH_UPDATER_VERSION=latest",
            "ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/",
        )
        for expected_arg in expected_args:
            with self.subTest(expected_arg=expected_arg):
                self.assertIn(expected_arg, self.instructions)

    def test_installs_and_verifies_astroncode_then_resets_private_home(self):
        install_instruction = self._single_run_instruction()
        expected_fragments = (
            "npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true",
            'npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}"',
            '--registry="${NPM_REGISTRY}"',
            "astron-code --version",
            "rm -rf /root/.acode",
            "install -d -m 700 /root/.acode",
        )
        self._assert_fragments_in_order(install_instruction, expected_fragments)

    def test_resets_acode_once_before_search_agent_installation(self):
        self._assert_acode_cleanup_precedes_search_agent(
            self._single_run_instruction()
        )

    def test_cleanup_guard_rejects_cleanup_after_fragment_copy(self):
        mutated_instruction = (
            f"{self._single_run_instruction()} && rm -rf /root/.acode"
        )
        with self.assertRaises(AssertionError):
            self._assert_acode_cleanup_precedes_search_agent(mutated_instruction)

    def test_installs_search_agent_runs_doctor_and_validates_generated_toml(self):
        install_instruction = self._single_run_instruction()
        expected_fragments = (
            "install -d -m 700 /root/.acode",
            'npm install -g "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}"',
            "--foreground-scripts",
            '--registry="${NPM_REGISTRY}"',
            "install-search",
            "install-search doctor --full",
            "python3 -c",
            "import tomllib",
            "sys.exit(0 if",
            'set(config) == {\"mcp_servers\"}',
            'config[\"mcp_servers\"]',
            "/root/.acode/config.toml",
            "/opt/astroncode/search-agent.config.toml",
        )
        self._assert_fragments_in_order(install_instruction, expected_fragments)

    def test_toml_validation_requires_mcp_servers_table(self):
        install_instruction = self._single_run_instruction()
        self.assertIn(
            'isinstance(config[\"mcp_servers\"], dict)',
            install_instruction,
        )

    def test_toml_validation_requires_each_mcp_server_table(self):
        validation_script = self._toml_validation_script()
        self.assertIn(
            'all(isinstance(server, dict) for server in '
            'config[\"mcp_servers\"].values())',
            validation_script,
        )

    def test_toml_validation_rejects_non_table_mcp_server(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                'mcp_servers = { search = "not-a-table" }\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    self._toml_validation_script(),
                    str(config_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid SearchAgent config", result.stderr)

    def test_search_agent_fragment_is_root_owned_and_not_user_writable(self):
        install_instruction = self._single_run_instruction()
        expected_fragments = (
            "install -d -o root -g root -m 755 /opt/astroncode",
            "install -o root -g root -m 644 /root/.acode/config.toml "
            "/opt/astroncode/search-agent.config.toml",
        )
        self._assert_fragments_in_order(install_instruction, expected_fragments)

    def test_contains_no_credentials_or_runtime_model_configuration(self):
        self.assertTrue(DOCKERFILE.is_file(), f"missing {DOCKERFILE}")
        self.assertNotRegex(self.instruction_content, r"(?im)^\s*(COPY|ADD)\s")
        for name in CREDENTIAL_AND_RUNTIME_ENV_NAMES:
            with self.subTest(name=name):
                self.assertNotRegex(
                    self.instruction_content,
                    rf"(?i)\b{re.escape(name)}\b",
                )

    def _single_run_instruction(self):
        self.assertEqual(1, len(self.run_instructions), self.run_instructions)
        return self.run_instructions[0]

    def _toml_validation_script(self):
        match = re.search(
            r"python3 -c '([^']+)' /root/\.acode/config\.toml",
            self._single_run_instruction(),
        )
        self.assertIsNotNone(match, "missing Python TOML validation command")
        return match.group(1)

    def _assert_fragments_in_order(self, content, fragments):
        previous_index = -1
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                current_index = content.find(fragment, previous_index + 1)
                self.assertNotEqual(-1, current_index, f"missing {fragment!r}")
                self.assertGreater(current_index, previous_index)
                previous_index = current_index

    def _assert_acode_cleanup_precedes_search_agent(self, install_instruction):
        cleanup = "rm -rf /root/.acode"
        updater = (
            'npm install -g "@iflytek/install-search-updater@'
            '${SEARCH_UPDATER_VERSION}"'
        )
        install_search = re.search(
            r"\s&&\s+install-search\s+&&",
            install_instruction,
        )

        self.assertEqual(1, install_instruction.count(cleanup))
        cleanup_index = install_instruction.index(cleanup)
        updater_index = install_instruction.index(updater)
        self.assertIsNotNone(install_search)
        self.assertLess(cleanup_index, updater_index)
        self.assertLess(cleanup_index, install_search.start())
        self.assertNotIn(
            cleanup,
            install_instruction[cleanup_index + len(cleanup) :],
        )


class AstronCodeBuildScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = BUILD_SCRIPT.read_text(encoding="utf-8")
        logical_content = re.sub(r"\\\s*\n\s*", " ", cls.content)
        cls.compact_content = re.sub(r"\s+", " ", logical_content)

    def test_defaults_to_v4_image_tag(self):
        self.assertRegex(
            self.content,
            re.escape('IMAGE_TAG="${IMAGE_TAG:-v0.4}"'),
        )

    def test_defaults_to_v4_docker_variant(self):
        self.assertRegex(
            self.content,
            re.escape(
                'ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v4}"'
            ),
        )

    def test_documents_v4_default_and_v1_v2_v3_overrides(self):
        self.assertRegex(
            self.content,
            r"(?m)^#\s*用法：bash script/build-astroncode-image\.sh\s*$",
        )
        self.assertRegex(
            self.content,
            r"(?m)^#\s*默认构建 v4.*AstronCode 0\.0\.13.*SearchAgent.*$",
        )
        for variant in ("v1", "v2", "v3"):
            with self.subTest(variant=variant):
                self.assertRegex(
                    self.content,
                    rf"(?m)^#\s*{variant}\s+覆盖：.*"
                    rf"ASTRONCODE_DOCKER_VARIANT={variant}.*"
                    r"bash script/build-astroncode-image\.sh\s*$",
                )

    def test_propagates_optional_version_and_registry_build_args(self):
        variables = (
            "ASTRON_CODE_VERSION",
            "SEARCH_UPDATER_VERSION",
            "NPM_REGISTRY",
        )
        for variable in variables:
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
            r'case\s+"\$\{ASTRONCODE_DOCKER_VARIANT\}"\s+in\s+'
            r"v1\|v2\|v3\|v4\)",
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
                    "ASTRONCODE_DOCKER_VARIANT": "v4/../v3",
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
                "Unknown AstronCode docker variant: v4/../v3",
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

    def test_default_build_executes_v4_build_save_and_writes_archive(self):
        execution = self._run_isolated_build()
        context = execution["repo_root"] / "docker" / "astroncode" / "v4"
        image = "wildclawbench-astroncode-ubuntu:v0.4"

        self.assertEqual(
            [
                [
                    "build",
                    "-f",
                    str(context / "Dockerfile"),
                    "-t",
                    image,
                    str(context),
                ],
                ["save", image],
            ],
            execution.get("events"),
        )
        self.assertEqual(f"fake image: {image}\n", execution["archive_content"])
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu_v0.4.tar.gz",
            execution["archive_name"],
        )

    def test_overrides_execute_selected_build_with_all_build_args(self):
        overrides = {
            "ASTRONCODE_DOCKER_VARIANT": "v3",
            "IMAGE_TAG": "v0.3-review",
            "ASTRON_CODE_VERSION": "0.0.99",
            "SEARCH_UPDATER_VERSION": "1.2.3",
            "NPM_REGISTRY": "https://registry.example.test/npm/",
            "HTTP_PROXY_INNER": "http://proxy.example.test:8080",
            "HTTPS_PROXY_INNER": "https://proxy.example.test:8443",
            "NO_PROXY_INNER": "localhost,127.0.0.1",
        }
        execution = self._run_isolated_build(overrides)
        context = execution["repo_root"] / "docker" / "astroncode" / "v3"
        image = "wildclawbench-astroncode-ubuntu:v0.3-review"

        self.assertEqual(
            [
                [
                    "build",
                    "-f",
                    str(context / "Dockerfile"),
                    "--build-arg",
                    "ASTRON_CODE_VERSION=0.0.99",
                    "--build-arg",
                    "SEARCH_UPDATER_VERSION=1.2.3",
                    "--build-arg",
                    "NPM_REGISTRY=https://registry.example.test/npm/",
                    "--build-arg",
                    "http_proxy=http://proxy.example.test:8080",
                    "--build-arg",
                    "HTTP_PROXY=http://proxy.example.test:8080",
                    "--build-arg",
                    "https_proxy=https://proxy.example.test:8443",
                    "--build-arg",
                    "HTTPS_PROXY=https://proxy.example.test:8443",
                    "--build-arg",
                    "no_proxy=localhost,127.0.0.1",
                    "--build-arg",
                    "NO_PROXY=localhost,127.0.0.1",
                    "-t",
                    image,
                    str(context),
                ],
                ["save", image],
            ],
            execution.get("events"),
        )
        self.assertEqual(f"fake image: {image}\n", execution["archive_content"])
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu_v0.3-review.tar.gz",
            execution["archive_name"],
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

    def _run_isolated_build(self, overrides=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            script_dir = repo_root / "script"
            script_dir.mkdir(parents=True)
            isolated_script = script_dir / BUILD_SCRIPT.name
            isolated_script.write_text(self.content, encoding="utf-8")

            for variant in ("v3", "v4"):
                context = repo_root / "docker" / "astroncode" / variant
                context.mkdir(parents=True)
                (context / "Dockerfile").write_text(
                    "FROM scratch\n",
                    encoding="utf-8",
                )

            bin_dir = Path(temp_dir) / "bin"
            log_dir = Path(temp_dir) / "docker-log"
            bin_dir.mkdir()
            log_dir.mkdir()
            docker_stub = bin_dir / "docker"
            docker_stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                '{ printf "%s\\000" "$#"; printf "%s\\000" "$@"; } '
                '>> "${DOCKER_EVENT_LOG:?}"\n'
                'case "${1:-}" in\n'
                "  build)\n"
                "    ;;\n"
                "  save)\n"
                '    printf "fake image: %s\\n" "${2:-}"\n'
                "    ;;\n"
                "  *)\n"
                '    printf "unexpected docker command: %s\\n" "${1:-}" >&2\n'
                "    exit 64\n"
                "    ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            docker_stub.chmod(0o755)

            environment = os.environ.copy()
            for variable in BUILD_OVERRIDE_ENV_NAMES:
                environment.pop(variable, None)
            environment.update(overrides or {})
            event_log = log_dir / "events.bin"
            environment.update(
                {
                    "DOCKER_EVENT_LOG": str(event_log),
                    "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                ["bash", str(isolated_script)],
                cwd=repo_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(
                0,
                result.returncode,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertTrue(event_log.is_file(), "docker was not called")
            events = self._read_docker_events(event_log)

            image_tag = (overrides or {}).get("IMAGE_TAG", "v0.4")
            archive = (
                repo_root
                / "Images"
                / f"wildclawbench-astroncode-ubuntu_{image_tag}.tar.gz"
            )
            self.assertTrue(archive.is_file(), f"missing archive: {archive}")
            with gzip.open(archive, mode="rt", encoding="utf-8") as archive_file:
                archive_content = archive_file.read()

            return {
                "repo_root": repo_root,
                "events": events,
                "archive_content": archive_content,
                "archive_name": archive.name,
            }

    def _read_docker_events(self, event_log):
        fields = event_log.read_bytes().split(b"\0")
        self.assertEqual(b"", fields.pop(), "unterminated docker event log")
        events = []
        offset = 0
        while offset < len(fields):
            argument_count = int(fields[offset].decode("ascii"))
            event_end = offset + argument_count + 1
            self.assertLessEqual(event_end, len(fields), "truncated docker event")
            events.append(
                [
                    argument.decode("utf-8")
                    for argument in fields[offset + 1 : event_end]
                ]
            )
            offset = event_end
        return events


if __name__ == "__main__":
    unittest.main()
