import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker" / "astroncode" / "v4" / "Dockerfile"
SEARCH_AGENT_VERIFIER = (
    REPO_ROOT
    / "docker"
    / "astroncode"
    / "v4"
    / "verify_search_agent.py"
)
BUILD_SCRIPT = REPO_ROOT / "docker" / "astroncode" / "build.sh"
BUILD_MANIFEST = REPO_ROOT / "docker" / "astroncode" / "versions.json"
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
        cls.run_content = "\n".join(cls.run_instructions)

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

    def test_persists_uv_bin_at_path_front_before_search_agent_installation(self):
        path_instruction = 'ENV PATH="/root/.local/bin:${PATH}"'
        self.assertIn(path_instruction, self.instructions)
        path_index = self.instructions.index(path_instruction)
        last_arg_index = self.instructions.index(
            "ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/"
        )
        install_index = self.instructions.index(self.run_instructions[0])

        self.assertLess(last_arg_index, path_index)
        self.assertLess(path_index, install_index)

    def test_installs_and_verifies_astroncode_then_resets_private_home(self):
        expected_fragments = (
            "npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true",
            'npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}"',
            '--registry="${NPM_REGISTRY}"',
            "astron-code --version",
            "rm -rf /root/.acode",
            "install -d -m 700 /root/.acode",
        )
        self._assert_fragments_in_order(self.run_content, expected_fragments)

    def test_resets_acode_once_before_search_agent_installation(self):
        self._assert_acode_cleanup_precedes_search_agent(self.run_content)

    def test_cleanup_guard_rejects_cleanup_after_fragment_copy(self):
        mutated_instruction = (
            f"{self.run_content} && rm -rf /root/.acode"
        )
        with self.assertRaises(AssertionError):
            self._assert_acode_cleanup_precedes_search_agent(mutated_instruction)

    def test_bootstraps_search_agent_browser_runs_fetch_smoke_and_doctor(self):
        install_instruction = self.run_content
        expected_fragments = (
            "install -d -m 700 /root/.acode",
            'npm install -g "@iflytek/install-search-updater@${SEARCH_UPDATER_VERSION}"',
            "--foreground-scripts",
            '--registry="${NPM_REGISTRY}"',
            "/tmp/verify_search_agent.py",
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
        self.assertNotIn("install-search bootstrap", install_instruction)
        self.assertNotIn("--skip-browser-install", install_instruction)
        self.assertNotIn("--skip-prewarm", install_instruction)

    def test_pins_scrapling_playwright_browser_path_in_runtime_fragment(self):
        expected_fragments = (
            'Path("/root/.acode/config.toml")',
            'marker = "[mcp_servers.scrapling.env]\\n"',
            'PLAYWRIGHT_BROWSERS_PATH',
            '\\"/ms-playwright\\"',
            'p.write_text(s, encoding="utf-8")',
        )
        self._assert_fragments_in_order(self.run_content, expected_fragments)

    def test_fetch_verifier_checks_browser_and_real_scrapling_tool(self):
        self.assertTrue(
            SEARCH_AGENT_VERIFIER.is_file(),
            f"missing {SEARCH_AGENT_VERIFIER}",
        )
        content = SEARCH_AGENT_VERIFIER.read_text(encoding="utf-8")
        expected_fragments = (
            'os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/root/.cache/ms-playwright")',
            'glob("chromium-*/chrome-linux*/chrome")',
            "os.access(candidate, os.X_OK)",
            'Path("/root/.acode/config.toml")',
            '["mcp_servers"][name]',
            "StdioServerParameters",
            "stdio_client",
            "ClientSession",
            'session.list_tools()',
            'server_parameters("scrapling")',
            'call_tool("fetch"',
            'require_tool("web-search", "web-search")',
        )
        self._assert_fragments_in_order(content, expected_fragments)
        self.assertIn("SEARCH_AGENT_FETCH_OK", content)
        self.assertIn("127.0.0.1", content)
        self.assertEqual(1, content.count("http://"))
        self.assertNotIn("https://", content)

    def test_copies_only_build_time_fetch_verifier(self):
        copy_instructions = [
            instruction
            for instruction in self.instructions
            if instruction.startswith(("COPY ", "ADD "))
        ]
        self.assertEqual(
            ["COPY verify_search_agent.py /tmp/verify_search_agent.py"],
            copy_instructions,
        )

    def test_toml_validation_requires_mcp_servers_table(self):
        self.assertIn(
            'isinstance(config[\"mcp_servers\"], dict)',
            self.run_content,
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
        expected_fragments = (
            "install -d -o root -g root -m 755 /opt/astroncode",
            "install -o root -g root -m 644 /root/.acode/config.toml "
            "/opt/astroncode/search-agent.config.toml",
        )
        self._assert_fragments_in_order(self.run_content, expected_fragments)

    def test_contains_no_credentials_or_runtime_model_configuration(self):
        self.assertTrue(DOCKERFILE.is_file(), f"missing {DOCKERFILE}")
        for name in CREDENTIAL_AND_RUNTIME_ENV_NAMES:
            with self.subTest(name=name):
                self.assertNotRegex(
                    self.instruction_content,
                    rf"(?i)\b{re.escape(name)}\b",
                )

    def _toml_validation_script(self):
        match = re.search(
            r"python3 -c '([^']+)' /root/\.acode/config\.toml",
            self.run_content,
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
        self.assertEqual(1, install_instruction.count(cleanup))
        cleanup_index = install_instruction.index(cleanup)
        updater_index = install_instruction.index(updater)
        self.assertLess(cleanup_index, updater_index)
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
        cls.manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))

    def test_defaults_to_v5_image_tag(self):
        self.assertEqual("v0.5", self.manifest["default"])
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.5",
            self.manifest["versions"]["v0.5"]["image"],
        )

    def test_defaults_to_v5_docker_variant(self):
        self.assertEqual(
            "v5",
            self.manifest["versions"]["v0.5"]["context"],
        )
        self.assertNotIn('BUILD_CONTEXT="${REPO_ROOT}/docker/astroncode/', self.content)

    def test_documents_v5_default_and_historical_overrides(self):
        result = subprocess.run(
            ["bash", str(BUILD_SCRIPT), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("docker/astroncode/build.sh", result.stdout)
        self.assertEqual(
            {"v0.1-test.8", "v0.2", "v0.3", "v0.4-ppt", "v0.5"},
            set(self.manifest["versions"]),
        )

    def test_propagates_optional_version_and_registry_build_args(self):
        variables = (
            "ASTRON_CODE_VERSION",
            "NODEJS_VERSION",
            "SEARCH_UPDATER_VERSION",
            "NPM_REGISTRY",
        )
        for variable in variables:
            with self.subTest(variable=variable):
                self.assertIn(variable, self.content)
                self.assertRegex(self.content, rf'--build-arg\s+"{variable}=')

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
        self.assertIn("Unknown AstronCode image version", self.content)
        self.assertIn("Missing AstronCode Dockerfile", self.content)
        self.assertIn("Invalid AstronCode build context", self.content)

    def test_whitelists_variants_before_constructing_paths(self):
        expected_contexts = {
            "v0.1-test.8": "v1",
            "v0.2": "v2",
            "v0.3": "v3",
            "v0.4-ppt": "v4",
            "v0.5": "v5",
        }
        for version, entry in self.manifest["versions"].items():
            with self.subTest(version=version):
                self.assertEqual(
                    f"wildclawbench-astroncode-ubuntu:{version}",
                    entry["image"],
                )
                self.assertEqual(expected_contexts[version], entry["context"])

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
                    "DOCKER_CALLED_MARKER": str(docker_marker),
                    "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                ["bash", str(BUILD_SCRIPT), "--version", "v4/../v3"],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "Unknown AstronCode image version: v4/../v3",
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

    def test_default_build_maps_to_v5_context(self):
        entry = self.manifest["versions"][self.manifest["default"]]
        self.assertEqual("v5/Dockerfile", entry["dockerfile"])
        self.assertEqual("0.0.34", entry["build_args"]["ASTRON_CODE_VERSION"])
        self.assertEqual(
            "22.23.2-1nodesource1",
            entry["build_args"]["NODEJS_VERSION"],
        )
        self.assertEqual("0.1.17", entry["build_args"]["SEARCH_UPDATER_VERSION"])

    def test_manifest_disallows_unregistered_review_tag(self):
        self.assertNotIn("v0.3-review", self.manifest["versions"])
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.3",
            self.manifest["versions"]["v0.3"]["image"],
        )

    def test_docker_build_uses_selected_file_context_and_tag(self):
        self.assertRegex(
            self.compact_content,
            r'docker build\s+-f "\$\{DOCKERFILE\}"\s+'
            r'"\$\{BUILD_ARGS\[@\]\}"\s+-t '
            r'"\$\{IMAGE_REF\}"\s+'
            r'"\$\{BUILD_CONTEXT\}"',
        )

    def test_exports_selected_image_to_gzipped_tar_path(self):
        self.assertRegex(
            self.compact_content,
            r'docker save\s+"\$\{IMAGE_REF\}"\s*'
            r'\|\s*gzip\s*>\s*"\$\{TEMP_TAR_PATH\}"',
        )


if __name__ == "__main__":
    unittest.main()
