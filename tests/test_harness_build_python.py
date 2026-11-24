"""Exercise builders without a system Python or uv on PATH, using fake Docker."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESSES = ("codex", "deepseek-harness", "claudecode", "opencode")


class HarnessBuildPythonTests(unittest.TestCase):
    def _run(self, harness: str, interpreter: str):
        with tempfile.TemporaryDirectory(prefix="wcb build python ") as temp:
            repo = Path(temp).resolve()
            target = repo / "docker" / harness
            shutil.copytree(REPO_ROOT / "docker" / harness, target)
            manifest = json.loads((target / "versions.json").read_text())
            entry = manifest["versions"][manifest["default"]]
            cli_version = next(
                value for key, value in entry["build_args"].items()
                if key.endswith("_VERSION")
            )

            bin_dir = repo / "bin"
            bin_dir.mkdir()
            # Keep only the builder's shell utilities on PATH, with no python3/uv.
            for name in ("dirname", "basename", "head"):
                (bin_dir / name).symlink_to(shutil.which(name))

            if interpreter in {"venv-python3", "venv-python", "venv-first"}:
                venv_bin = repo / ".venv" / "bin"
                venv_bin.mkdir(parents=True)
                name = "python" if interpreter == "venv-python" else "python3"
                (venv_bin / name).symlink_to(sys.executable)
            if interpreter == "system":
                (bin_dir / "python3").symlink_to(sys.executable)
            elif interpreter == "venv-first":
                system_stub = bin_dir / "python3"
                system_stub.write_text("#!/bin/sh\nexit 99\n")
                system_stub.chmod(0o755)
            elif interpreter == "uv":
                uv_stub = bin_dir / "uv"
                uv_stub.write_text(
                    f"#!{sys.executable}\n"
                    "import os, sys\n"
                    "assert sys.argv[1:3] == ['run', 'python']\n"
                    f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[3:]])\n"
                )
                uv_stub.chmod(0o755)

            event_log = repo / "docker-events.jsonl"
            docker_stub = bin_dir / "docker"
            docker_stub.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "with open(os.environ['DOCKER_EVENT_LOG'], 'a') as stream:\n"
                "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if sys.argv[1] == 'run':\n"
                "    print(os.environ['TEST_CLI_VERSION'])\n"
            )
            docker_stub.chmod(0o755)

            env = os.environ.copy()
            for key in (
                "CODEX_VERSION", "DSH_VERSION", "CLAUDE_CODE_VERSION", "OPENCODE_VERSION",
                "EVAL_BASE_IMAGE", "NODE_RUNTIME_IMAGE", "IMAGE_TAG", "SKIP_SAVE",
                "NPM_REGISTRY", "HTTP_PROXY_INNER", "HTTPS_PROXY_INNER", "NO_PROXY_INNER",
                "WCB_LEGACY_BUILD_WRAPPER",
            ):
                env.pop(key, None)
            env.update({
                "PATH": str(bin_dir),
                "DOCKER_EVENT_LOG": str(event_log),
                "TEST_CLI_VERSION": cli_version,
            })
            result = subprocess.run(
                [shutil.which("bash"), str(target / "build.sh"), "--skip-save"],
                # Interpreter selection must work even when invoked outside the repo.
                cwd=bin_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            events = ([json.loads(line) for line in event_log.read_text().splitlines()]
                      if event_log.exists() else [])
            return result, events, entry["image"]

    def test_venv_python_works_without_system_python_or_uv(self):
        for harness in HARNESSES:
            for interpreter in ("venv-python3", "venv-python", "venv-first"):
                with self.subTest(harness=harness, interpreter=interpreter):
                    result, events, image = self._run(harness, interpreter)
                    self.assertEqual(0, result.returncode, result.stderr)
                    build = next(event for event in events if event[0] == "build")
                    self.assertEqual(image, build[build.index("-t") + 1])
                    self.assertFalse(any(event[0] == "save" for event in events))

    def test_system_python_fallback(self):
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                result, _, _ = self._run(harness, "system")
                self.assertEqual(0, result.returncode, result.stderr)

    def test_uv_fallback(self):
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                result, _, _ = self._run(harness, "uv")
                self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_python_fails_before_docker_with_actionable_message(self):
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                result, events, _ = self._run(harness, "none")
                self.assertEqual(2, result.returncode)
                self.assertIn(".venv/bin/python", result.stderr)
                self.assertIn("uv", result.stderr)
                self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
