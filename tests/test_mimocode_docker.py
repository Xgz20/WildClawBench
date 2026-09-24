from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "docker" / "mimocode"


class MiMoCodeDockerTests(unittest.TestCase):
    def test_manifest_and_dockerfile_pin_cli_and_codex_base(self) -> None:
        manifest = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["default"], "v0.1")
        entry = manifest["versions"]["v0.1"]
        self.assertEqual(entry["image"], "wildclawbench-mimocode-ubuntu:v0.1")
        self.assertEqual(entry["build_args"]["MIMOCODE_VERSION"], "0.1.15")
        self.assertEqual(
            entry["build_args"]["EVAL_BASE_IMAGE"], "wildclawbench-codex-ubuntu:v0.0"
        )
        dockerfile = (ROOT / entry["dockerfile"]).read_text(encoding="utf-8")
        self.assertIn("ARG MIMOCODE_VERSION=0.1.15", dockerfile)
        self.assertIn("@mimo-ai/cli", dockerfile)
        self.assertIn("npm install --global", dockerfile)
        self.assertIn("wildclawbench-codex-ubuntu:v0.0", dockerfile)

    def test_entrypoint_supports_all_protocols_and_json_events(self) -> None:
        entrypoint = ROOT / "v2" / "wcb-mimocode"
        self.assertTrue(os.access(entrypoint, os.X_OK))
        source = entrypoint.read_text(encoding="utf-8")
        for api in (
            "openai-responses",
            "openai-chat-completions",
            "anthropic-messages",
        ):
            self.assertIn(api, source)
        self.assertIn("--format json", source)
        self.assertNotIn("sk-", source)

    def test_old_image_identity_and_runtime_contract_are_preserved(self):
        manifest = json.loads((ROOT / "versions.json").read_text())
        old = manifest["versions"]["v0.0"]
        self.assertFalse(old["buildable"])
        self.assertEqual(old["build_args"]["MIMOCODE_VERSION"], "0.1.14")
        self.assertEqual(old["context"], "v1")
        self.assertIn(
            "ARG MIMOCODE_VERSION=0.1.14", (ROOT / old["dockerfile"]).read_text()
        )
        self.assertEqual(
            (ROOT / "v1/wcb-mimocode").read_bytes(),
            (ROOT / "v2/wcb-mimocode").read_bytes(),
        )

    def run_builder(self, args=(), overrides=None):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            docker = tmp / "docker"
            log = tmp / "events.jsonl"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json,os,sys\n"
                'with open(os.environ["DOCKER_TEST_LOG"],"a") as stream: stream.write(json.dumps(sys.argv[1:])+"\\n")\n'
                'if sys.argv[1]=="run": print(os.environ.get("TEST_CLI_VERSION","0.1.15"))\n'
            )
            docker.chmod(0o755)
            env = os.environ.copy()
            for key in (
                "MIMOCODE_VERSION",
                "SKIP_SAVE",
                "NPM_REGISTRY",
                "HTTP_PROXY_INNER",
                "HTTPS_PROXY_INNER",
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

    def test_builder_default_and_explicit_v01_match(self):
        for args in ((), ("--version", "v0.1")):
            with self.subTest(args=args):
                result, events = self.run_builder(args)
                self.assertEqual(result.returncode, 0, result.stderr)
                build = next(event for event in events if event[0] == "build")
                self.assertEqual(build[-1], str(ROOT / "v2"))
                self.assertIn("wildclawbench-mimocode-ubuntu:v0.1", build)
                self.assertIn("MIMOCODE_VERSION=0.1.15", build)
                self.assertFalse(any(event[0] == "save" for event in events))

    def test_unavailable_old_version_stops_before_docker(self):
        result, events = self.run_builder(("--version", "v0.0"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no longer available", result.stderr)
        self.assertEqual(events, [])

    def test_conflicting_cli_version_stops_before_docker(self):
        result, events = self.run_builder(overrides={"MIMOCODE_VERSION": "0.1.14"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 0.1.15", result.stderr)
        self.assertEqual(events, [])

    def test_installed_cli_version_is_verified(self):
        result, _ = self.run_builder(overrides={"TEST_CLI_VERSION": "0.1.14"})
        self.assertEqual(result.returncode, 3)
        self.assertIn("Unexpected installed MiMoCode version", result.stderr)


if __name__ == "__main__":
    unittest.main()
