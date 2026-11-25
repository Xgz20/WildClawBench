import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.e2e import desktop_score_runtime as runtime
from src.e2e import preprocess_windows_guest

with patch.dict(sys.modules, {"preprocess_windows_guest": preprocess_windows_guest,
                             "desktop_score_runtime": runtime}):
    from src.e2e import desktop_score_guest as guest


class DesktopScoreRuntimeTests(unittest.TestCase):
    def test_uv_reuse_rejects_changed_executable_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "uv.exe").write_bytes(b"changed")
            with patch.object(runtime.urllib.request, "urlopen") as download:
                with self.assertRaisesRegex(ValueError, "UV_DIGEST_MISMATCH"):
                    runtime.uv_executable(directory, lambda: 60)
            download.assert_not_called()

    def test_corrupt_uv_download_does_not_publish_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with patch.object(runtime.urllib.request, "urlopen", return_value=io.BytesIO(b"broken wheel")):
                with self.assertRaisesRegex(ValueError, "UV_DIGEST_MISMATCH"):
                    runtime.uv_executable(directory, lambda: 60)
            self.assertFalse((directory / "uv.exe").exists())
            self.assertFalse((directory / "uv.whl.part").exists())

    def fixture(self, root):
        skill = root / "skill"
        (skill / "references").mkdir(parents=True)
        lock = {"python": {"major": 3, "minor": 11},
                "dependencies": [{"import_roots": ["playwright"], "runtime_assets": [{"name":"chromium"}]},
                                 {"import_roots": ["openpyxl"]}]}
        (skill / "references/scoring-runtime-lock.json").write_text(json.dumps(lock))
        tooling = root / "work/tooling"
        tooling.mkdir(parents=True)
        probe = {"status": "PASS", "runtime_lock_sha256": "a" * 64,
                 "probe": {"python": {"major": 3, "minor": 11, "in_virtualenv": True}}}
        return skill, tooling, probe

    def test_runtime_is_bootstrapped_and_probed_with_the_frozen_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            skill, tooling, probe = self.fixture(Path(temp))
            responses = [Mock(returncode=0, stdout=b'{"status":"PASS"}'),
                         Mock(returncode=0, stdout=json.dumps(probe).encode())]
            with patch.object(runtime, "uv_executable", return_value=tooling / "uv.exe"), \
                    patch.object(runtime.subprocess, "run", side_effect=responses) as run:
                result = runtime.prepare_runtime(skill, tooling, 120)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("bootstrap-runtime", commands[0])
            self.assertIn("probe-runtime", commands[1])
            self.assertIn(str(skill / "references/scoring-runtime-lock.json"), commands[1])
            self.assertIn("playwright", commands[1])
            self.assertIn("openpyxl", commands[1])
            bootstrap_cwd = run.call_args_list[0].kwargs["cwd"]
            self.assertFalse(bootstrap_cwd.is_relative_to(tooling.parent))
            self.assertIn("pypi.tuna.tsinghua.edu.cn/simple", (bootstrap_cwd / "uv.toml").read_text())
            self.assertTrue(result["python"].endswith("runtime/Scripts/python.exe"))
            self.assertFalse(Path(result["python"]).is_relative_to(tooling.parent))
            self.assertEqual(json.loads((tooling / "general-runtime.json").read_text()), result)

    def test_text_rules_do_not_download_or_claim_a_browser_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            skill, tooling, probe = self.fixture(Path(temp))
            with patch.object(runtime, "requires_browser", return_value=False), \
                    patch.object(runtime, "uv_executable", return_value=tooling / "uv.exe"), \
                    patch.object(runtime.subprocess, "run", side_effect=[
                        Mock(returncode=0, stdout=b'{"status":"PASS"}'),
                        Mock(returncode=0, stdout=json.dumps(probe).encode())]) as run:
                result = runtime.prepare_runtime(skill, tooling, 120, contract={"automated_checks":"import json"})
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("--skip-browser", commands[0])
            self.assertNotIn("--playwright-browsers-path", commands[1])
            self.assertNotIn("playwright", commands[1])
            self.assertIn("openpyxl", commands[1])
            self.assertFalse(result["browser_required"])

    def test_browser_scope_uses_the_frozen_core_and_is_conservative_when_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp)
            source = Path(__file__).resolve().parents[2] / "src/wildclawbench_grading_core"
            shutil.copytree(source, skill / "vendor/e2e-shared/wildclawbench_grading_core",
                            ignore=shutil.ignore_patterns("__pycache__"))
            self.assertFalse(runtime.requires_browser(skill, {"automated_checks":"import json, csv"}))
            self.assertTrue(runtime.requires_browser(skill, {"automated_checks":"from playwright.sync_api import sync_playwright"}))
            self.assertTrue(runtime.requires_browser(skill, {"automated_checks":"__import__('unknown')"}))

    def test_resume_verifies_existing_environment_and_preserves_failure_code(self):
        with tempfile.TemporaryDirectory() as temp:
            skill, tooling, _ = self.fixture(Path(temp))
            lock_sha = hashlib.sha256((skill / "references/scoring-runtime-lock.json").read_bytes()).hexdigest()
            (tooling.parent.parent / ".desktop-scoring-runtime" / lock_sha[:16] / "runtime").mkdir(parents=True)
            response = Mock(returncode=2, stdout=b"", stderr=json.dumps({
                "error": {"code": "RUNTIME_PYTHON_MISMATCH", "detail": "private-provider-secret"}}).encode())
            with patch.object(runtime, "uv_executable") as download, \
                    patch.object(runtime.subprocess, "run", return_value=response) as run:
                with self.assertRaisesRegex(ValueError, "RUNTIME_PYTHON_MISMATCH"):
                    runtime.prepare_runtime(skill, tooling, 120)
            download.assert_not_called()
            self.assertEqual(run.call_count, 1)
            self.assertIn("probe-runtime", run.call_args.args[0])
            self.assertFalse((tooling / "general-runtime.json").exists())
            self.assertNotIn("private-provider-secret", (tooling / "general-runtime-steps.jsonl").read_text())

    def test_download_failure_is_explicit_and_never_runs_the_system_python_as_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            skill, tooling, _ = self.fixture(Path(temp))
            with patch.object(runtime, "uv_executable", side_effect=OSError("private-proxy-secret")), \
                    patch.object(runtime.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "DESKTOP_SCORING_UV_DOWNLOAD_FAILED"):
                    runtime.prepare_runtime(skill, tooling, 120)
            run.assert_not_called()
            log = (tooling / "general-runtime-steps.jsonl").read_text()
            self.assertIn("download-uv", log)
            self.assertNotIn("private-proxy-secret", log)

    def test_general_installation_publishes_verified_python_and_web_keeps_its_route(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = {"scene": "general", "name": "score-general-e2e", "version": "fixture",
                       "inventory_sha256": "b" * 64, "timeout_seconds": 120}
            verified = {"python": str(root / "runtime/Scripts/python.exe"), "status": "PASS"}
            with patch.object(guest, "prepare_general", return_value=(True, verified)) as general, patch("builtins.print"):
                guest.describe_installation(root, root, request, root, None, "installed")
            result = json.loads((root / "installation.json").read_text())
            self.assertEqual(general.call_args.args[-1], request)
            self.assertEqual(result["python"], verified["python"])
            self.assertTrue(result["rules_only"])
            with patch.object(guest, "prepare_runtime") as provision, patch.object(guest, "prepare_general") as general, \
                    patch("builtins.print"):
                guest.describe_installation(root, root, {**request, "scene": "web"}, root, "node", "installed")
            web = json.loads((root / "installation.json").read_text())
            provision.assert_not_called()
            general.assert_not_called()
            self.assertEqual(web["python"], sys.executable)

    def test_automated_rules_receive_the_verified_runtime_instead_of_system_python(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            attempt = work / "attempts/fixture"
            (attempt / "private").mkdir(parents=True)
            (attempt / "attempt-manifest.json").write_text('{}')
            (attempt / "private/contract.json").write_text('{"grading_type":"automated"}')
            runtime_python = work / "runtime/Scripts/python.exe"
            with patch.object(guest.subprocess, "run", return_value=Mock(returncode=0)) as run, \
                    patch.object(guest.shutil, "make_archive"), \
                    patch.object(guest, "prepare_runtime", return_value={"python":str(runtime_python)}):
                ready, _ = guest.prepare_general(work, work, work, {"attempt":"fixture", "timeout_seconds":60})
                self.assertTrue(ready)
            command = next(call.args[0] for call in run.call_args_list if "run-rules" in call.args[0])
            self.assertEqual(command[command.index("--runtime-python") + 1], str(runtime_python))
            actions = [call.args[0][4] for call in run.call_args_list]
            self.assertLess(actions.index("prepare-semantics"), actions.index("finalize"))


if __name__ == "__main__":
    unittest.main()
