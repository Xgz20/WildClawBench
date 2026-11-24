from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1] / "docker" / "opencode"


class OpenCodeDockerTests(unittest.TestCase):
    def test_manifest_preserves_v00_and_selects_v01(self) -> None:
        manifest = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["default"], "v0.1")
        self.assertEqual(set(manifest["versions"]), {"v0.0", "v0.1"})
        self.assertEqual(manifest["versions"]["v0.0"]["context"], "v1")
        self.assertEqual(
            manifest["versions"]["v0.0"]["build_args"]["OPENCODE_VERSION"],
            "1.18.4",
        )
        latest = manifest["versions"]["v0.1"]
        self.assertEqual(latest["context"], "v2")
        self.assertEqual(latest["dockerfile"], "v2/Dockerfile")
        self.assertEqual(latest["image"], "wildclawbench-opencode-ubuntu:v0.1")
        self.assertEqual(latest["build_args"]["OPENCODE_VERSION"], "1.19.6")
        self.assertTrue((ROOT / "v1/Dockerfile").is_file())
        self.assertTrue((ROOT / "v2/Dockerfile").is_file())
        self.assertFalse((ROOT / "Dockerfile").exists())

    def test_latest_dockerfile_pins_cli_and_base(self) -> None:
        dockerfile = (ROOT / "v2/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", dockerfile)
        self.assertIn("ARG OPENCODE_VERSION=1.19.6", dockerfile)
        self.assertIn('npm install -g "opencode-ai@${OPENCODE_VERSION}"', dockerfile)
        self.assertIn('opencode --version', dockerfile)

    def _run_builder(self, args=(), overrides=None):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            docker = tmp / "docker"
            log = tmp / "events.jsonl"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                'with open(os.environ["DOCKER_TEST_LOG"], "a") as stream:\n'
                '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                'if sys.argv[1] == "run":\n'
                '    print(os.environ.get("TEST_CLI_VERSION", "1.19.6"))\n'
                'if sys.argv[1] == os.environ.get("TEST_FAIL_COMMAND"):\n'
                '    sys.exit(7)\n',
                encoding="utf-8",
            )
            docker.chmod(0o755)
            env = os.environ.copy()
            for key in (
                "EVAL_BASE_IMAGE",
                "NPM_REGISTRY",
                "OPENCODE_VERSION",
                "SKIP_SAVE",
                "HTTP_PROXY_INNER",
                "HTTPS_PROXY_INNER",
                "NO_PROXY_INNER",
                "TEST_CLI_VERSION",
                "TEST_FAIL_COMMAND",
            ):
                env.pop(key, None)
            env.update(
                {
                    "PATH": str(tmp) + os.pathsep + env["PATH"],
                    "DOCKER_TEST_LOG": str(log),
                }
            )
            env.update(overrides or {})
            result = subprocess.run(
                ["bash", str(ROOT / "build.sh"), "--skip-save", *args],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            events = (
                [json.loads(line) for line in log.read_text().splitlines()]
                if log.exists()
                else []
            )
            return result, events

    def test_builder_default_uses_latest_context_and_tag(self) -> None:
        for args in ((), ("--version", "v0.1")):
            with self.subTest(args=args):
                result, events = self._run_builder(args)
                self.assertEqual(result.returncode, 0, result.stderr)
                build = next(event for event in events if event[0] == "build")
                self.assertEqual(build[-1], str(ROOT / "v2"))
                self.assertEqual(build[build.index("-f") + 1], str(ROOT / "v2/Dockerfile"))
                self.assertEqual(build[build.index("-t") + 1], "wildclawbench-opencode-ubuntu:v0.1")
                self.assertIn("OPENCODE_VERSION=1.19.6", build)
                self.assertIn("EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", build)
                self.assertFalse(any(event[0] == "save" for event in events))

    def test_builder_can_rebuild_historical_v00(self) -> None:
        result, events = self._run_builder(("--version", "v0.0"), {"TEST_CLI_VERSION": "1.18.4"})
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(event for event in events if event[0] == "build")
        self.assertEqual(build[-1], str(ROOT / "v1"))
        self.assertIn("wildclawbench-opencode-ubuntu:v0.0", build)
        self.assertIn("OPENCODE_VERSION=1.18.4", build)

    def test_conflicting_cli_version_stops_before_docker(self) -> None:
        result, events = self._run_builder(overrides={"OPENCODE_VERSION": "1.18.4"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 1.19.6", result.stderr)
        self.assertEqual(events, [])

    def test_installed_cli_version_is_verified(self) -> None:
        for version in ("1.18.4", "11.19.60", "1.19.6-dev", ""):
            with self.subTest(version=version):
                result, _ = self._run_builder(overrides={"TEST_CLI_VERSION": version})
                self.assertEqual(result.returncode, 3)
                self.assertIn("Unexpected installed OpenCode version", result.stderr)

    def test_invalid_arguments_stop_before_docker(self) -> None:
        for args in (("--version", "v9.9"), ("--version",), ("--unknown",)):
            with self.subTest(args=args):
                result, events = self._run_builder(args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(events, [])

    def test_conflicting_base_stops_before_docker(self) -> None:
        result, events = self._run_builder(overrides={"EVAL_BASE_IMAGE": "other-base:latest"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("EVAL_BASE_IMAGE must be wildclawbench-codex-ubuntu:v0.0", result.stderr)
        self.assertEqual(events, [])

    def test_missing_base_stops_before_build(self) -> None:
        result, events = self._run_builder(overrides={"TEST_FAIL_COMMAND": "image"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Base image not found locally", result.stderr)
        self.assertEqual([event[0] for event in events], ["image"])

    def test_build_failure_stops_before_version_check(self) -> None:
        result, events = self._run_builder(overrides={"TEST_FAIL_COMMAND": "build"})
        self.assertEqual(result.returncode, 7)
        self.assertEqual([event[0] for event in events], ["image", "build"])

    def test_failed_version_command_is_rejected_even_with_matching_stdout(self) -> None:
        result, _ = self._run_builder(overrides={"TEST_FAIL_COMMAND": "run"})
        self.assertEqual(result.returncode, 3)
        self.assertIn("Failed to verify installed OpenCode version", result.stderr)

    def test_registry_and_proxy_arguments_reach_docker(self) -> None:
        overrides = {
            "NPM_REGISTRY": "https://registry.npmmirror.com",
            "HTTP_PROXY_INNER": "http://proxy.example:8080",
            "HTTPS_PROXY_INNER": "http://proxy.example:8081",
            "NO_PROXY_INNER": "localhost,127.0.0.1",
        }
        result, events = self._run_builder(overrides=overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(event for event in events if event[0] == "build")
        self.assertIn("NPM_REGISTRY=https://registry.npmmirror.com", build)
        for source, destination in (
            ("HTTP_PROXY_INNER", "http_proxy"),
            ("HTTPS_PROXY_INNER", "https_proxy"),
            ("NO_PROXY_INNER", "no_proxy"),
        ):
            self.assertIn(f"{destination}={overrides[source]}", build)
            self.assertIn(f"{destination.upper()}={overrides[source]}", build)


if __name__ == "__main__":
    unittest.main()
