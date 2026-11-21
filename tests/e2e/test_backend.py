import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.e2e.agentcube import AgentCubeClient, AgentCubeConfig
from src.e2e.backend import AStudioSandboxDriver, WorkBuddySandboxDriver, GUEST_WORKSPACE, NATIVE_ROOT, powershell, process_cleanup_script
from src.e2e.cli import build_parser, _run
from src.e2e.common import E2EError, digest


class BackendTests(unittest.TestCase):
    def test_workbuddy_diagnostics_accepts_raw_json_and_windows_proxy_envelope(self):
        driver = object.__new__(WorkBuddySandboxDriver)
        driver.client = Mock()
        diagnostics = {"model": "GLM-5.3", "workspace": GUEST_WORKSPACE, "max_mode": False}
        for payload in (diagnostics, {"code": 0, "msg": "", "data": diagnostics}):
            with self.subTest(payload=payload):
                driver.client.windows_download.return_value = json.dumps(payload).encode()
                self.assertEqual(driver._read_workbuddy_diagnostics("sid"), diagnostics)
        driver.client.windows_download.return_value = b'{"code": 10005, "msg": "", "data": null}'
        with self.assertRaisesRegex(E2EError, "WORKBUDDY_DIAGNOSTICS_DOWNLOAD_REJECTED"):
            driver._read_workbuddy_diagnostics("sid")

    def test_workbuddy_requires_explicit_full_access_and_controller_forwarding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = object.__new__(WorkBuddySandboxDriver)
            driver.client = Mock()
            driver._checked_job = Mock()
            driver.batch = root
            driver.staging = root / "staging"
            driver.task = {"input_root": "case"}
            driver.unit = {"model": "GLM-5.3", "timeout_override": 600, "workbuddy_full_access": False}
            public = root / "case/execution"
            (public / "workspace").mkdir(parents=True)
            (public / "PROMPT.md").write_text("test prompt")

            capabilities = {"ui_fields": ["permission", "mode"], "products": ["workbuddy"],
                            "workbuddy_permission_forwarded": False}
            driver.client.checked.return_value = json.dumps(capabilities)
            with self.assertRaisesRegex(E2EError, "GENERAL_E2E_FULL_ACCESS_REQUIRED"):
                driver._prepare_runtime("sid")
            driver.client.upload.assert_not_called()

            driver.unit["workbuddy_full_access"] = True
            with self.assertRaisesRegex(E2EError, "WORKBUDDY_PERMISSION_NOT_SUPPORTED"):
                driver._prepare_runtime("sid")

            capabilities["workbuddy_permission_forwarded"] = True
            driver.client.checked.return_value = json.dumps(capabilities)
            driver._prepare_runtime("sid")
            driver._upload("sid")
            request = json.loads((driver.staging / "metadata/run-request.json").read_text())
            self.assertEqual(request["product_config"]["ui"]["permission"], "full access")
            driver.unit["workbuddy_full_access"] = False
            driver.client.upload.reset_mock()
            with self.assertRaisesRegex(E2EError, "GENERAL_E2E_FULL_ACCESS_REQUIRED"):
                driver._upload("sid")
            driver.client.upload.assert_not_called()
            driver.unit["workbuddy_full_access"] = True
            driver.ui_fields.remove('permission')
            with self.assertRaisesRegex(E2EError, "GENERAL_E2E_FULL_ACCESS_UNVERIFIABLE"):
                driver._upload("sid")

    def test_cleanup_script_fits_windows_command_limit_and_roundtrips(self):
        script = process_cleanup_script(r"C:\Windows\Temp\wcb-cleanup-attempt.json", GUEST_WORKSPACE)
        command = powershell(script)
        self.assertLess(len(command), 8191)
        bootstrap = base64.b64decode(command.rsplit(" ", 1)[1]).decode("utf-16-le")
        compressed = bootstrap.split("FromBase64String('", 1)[1].split("'", 1)[0]
        self.assertEqual(gzip.decompress(base64.b64decode(compressed)).decode("utf-8"), script)
        self.assertIn("already_exited", script)
        self.assertLess(script.index("Save $proof"), script.index("Stop-Process"))
        self.assertIn("$targets=@($proof.before)+$additional", script)
        self.assertIn("CLEANUP_PROOF_IDENTITY_MISMATCH", script)
        self.assertIn("WORKSPACE_PROCESS_IDENTITY_UNAVAILABLE", script)

    def test_chatgpt_cleanup_waits_for_the_original_process_to_disappear(self):
        script = process_cleanup_script(
            r"C:\Windows\Temp\wcb-cleanup-attempt.json",
            GUEST_WORKSPACE,
            product="chatgpt-desktop",
        )
        self.assertLess(len(powershell(script)), 8191)
        self.assertIn("$ownedExitGraceMs=15000", script)
        self.assertIn("$_.pid -eq $sample.pid -and $_.created -eq $sample.created", script)
        self.assertIn("if($unexpected.Count -eq 0){$quiet.Reset();continue}", script)
        self.assertIn("if(-not $quiet.IsRunning){$quiet.Start()}", script)
        self.assertIn("quiet_observed_milliseconds=$quiet.ElapsedMilliseconds", script)
        for product in ("astudio", "workbuddy"):
            self.assertIn("$ownedExitGraceMs=0", process_cleanup_script("proof.json", GUEST_WORKSPACE, product=product))

    def test_windows_missing_file_envelope_is_not_an_artifact(self):
        client = AgentCubeClient(AgentCubeConfig(user_id="test", auth_token="test"))
        response = Mock(status_code=200, headers={"Content-Type": "application/json; charset=utf-8"})
        response.json.return_value = {"code": 10005, "msg": "File not found", "data": None}
        client._request = Mock(return_value=response)
        with self.assertRaises(FileNotFoundError):
            client.windows_download("session", "missing.json")
        client.close()

    def test_native_binding_downloads_safe_rollout_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b'{"type":"test"}\n'
            path = NATIVE_ROOT + r"\rollout-test.jsonl"
            driver = object.__new__(AStudioSandboxDriver)
            driver.staging = Path(directory)
            driver.unit = {"model": "spark-x2.6", "reasoning_effort": "high"}
            driver.client = Mock()
            driver.client.windows_download.return_value = raw
            driver._inventory_native = Mock(return_value={path: {"Length": len(raw), "Sha256": hashlib.sha256(raw).hexdigest()}})
            with patch("src.e2e.backend.normalize_rollout", return_value={"verified": True}):
                local, binding = driver._bound_native("sid", {}, {}, {}, "prompt", "before-cleanup")
            self.assertEqual(local.read_bytes(), raw)
            self.assertTrue(binding["verified"])

    def test_cleanup_discovery_can_resume_when_no_mutation_proof_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = object.__new__(AStudioSandboxDriver)
            driver.staging = Path(directory)
            driver.key = "key"
            driver.store = Mock()
            driver.store.get.return_value = {"attempt_id": "exec-test", "process_cleanup_intent": {"at": "earlier"}}
            driver.client = Mock()
            driver.client.windows_download.side_effect = FileNotFoundError
            proof = {"schema": "wildclawbench.agentcube-process-cleanup/v1", "phase": "completed",
                     "supported": True, "success": True, "after": [], "before": [], "root_pid": None,
                     "disposition": "already_exited", "quiet_observed_milliseconds": 5000, "workspace": GUEST_WORKSPACE}
            driver.client.windows_execute.return_value = {"output": base64.b64encode(json.dumps(proof).encode()).decode()}
            self.assertEqual(driver._cleanup_processes("sid"), proof)
            self.assertTrue(driver.client.windows_execute.called)
            driver.client.windows_download.assert_not_called()

    def test_timeout_salvage_quiesces_agent_and_preserves_prior_live_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = object.__new__(AStudioSandboxDriver)
            driver.staging = Path(directory)
            (driver.staging / "metadata").mkdir()
            old = driver.staging / "native/failure/old.jsonl"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"prior live observation")
            driver.key = "key"
            driver.store = Mock()
            driver.store.get.return_value = {"session_id": "sid", "dispatch_armed_at": "earlier", "native_before": {}}
            driver.client = Mock()
            raw = b'{"type":"partial"}\n'
            remote = NATIVE_ROOT + r"\rollout-timeout.jsonl"
            order = []
            driver._cleanup_processes = lambda sid: order.append("cleanup")
            def observe(sid):
                self.assertEqual(order, ["cleanup"])
                order.append("inventory")
                return {remote: {"Length": len(raw), "Sha256": hashlib.sha256(raw).hexdigest()}}
            driver._inventory_native = observe
            driver.client.windows_download.return_value = raw
            driver._checked_job = Mock()
            def download(sid, remote, name):
                target = driver.staging / name
                target.mkdir()
                if name == "failure-quiesced-collect":
                    (target / "manifest.json").write_text(json.dumps({"schema_version": 2, "files": []}))
            driver._download_tree = download
            result = driver.salvage()
            self.assertTrue(result["complete"])
            self.assertTrue(result["components"]["process_cleanup"])
            self.assertEqual(old.read_bytes(), b"prior live observation")
            self.assertEqual((driver.staging / "native/failure-quiesced/rollout-timeout.jsonl").read_bytes(), raw)
            self.assertEqual(driver._checked_job.call_args.args[0], "failure-quiesced-task-collect")
            self.assertIn("/logs/artifacts/failure-quiesced-collect", driver._checked_job.call_args.args[1])

    def test_salvage_keeps_vm_when_owned_process_cleanup_is_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = object.__new__(AStudioSandboxDriver)
            driver.staging = Path(directory)
            (driver.staging / "metadata").mkdir()
            driver.key = "key"
            driver.store = Mock()
            driver.store.get.return_value = {"session_id": "sid", "dispatch_armed_at": "earlier"}
            driver._cleanup_processes = Mock(side_effect=E2EError("REMOTE_PROCESS_CLEANUP_UNVERIFIED"))
            driver._inventory_native = Mock()
            result = driver.salvage()
            self.assertFalse(result["complete"])
            self.assertFalse(result["components"]["process_cleanup"])
            driver._inventory_native.assert_not_called()

    def test_cli_timeout_override_wins_over_each_plan_unit(self):
        raw = {"units": [{"timeout_override": 100}, {"timeout_override": 200}], "timeout_override": 300}
        args = build_parser().parse_args(["run", "--workspace-root", "/tmp/work", "--plan", "/tmp/plan.json",
                                          "--timeout-override", "600", "--dry-run"])
        with patch("src.e2e.cli.read_json", return_value=raw), patch("src.e2e.preparation.prepare_batch") as prepare:
            prepare.side_effect = E2EError("PREPARATION_STOP")
            with self.assertRaisesRegex(E2EError, "PREPARATION_STOP"):
                _run(args)
        captured = prepare.call_args.args[2]
        self.assertEqual(captured["timeout_override"], 600)
        self.assertEqual([unit["timeout_override"] for unit in captured["units"]], [600, 600])

    def test_resume_observes_original_job_without_resetting_its_control_budget(self):
        driver = object.__new__(AStudioSandboxDriver)
        driver.key = "key"
        command = "original command"
        job = {"job_id": "original-job", "command_sha256": digest(command), "submission": "confirmed",
               "created_at": "2000-01-01T00:00:00+00:00"}
        row = {"session_id": "original-session", "phase": "RUNNING", "jobs": {"task-run": job}}
        driver.store = Mock()
        driver.store.get.return_value = row
        driver.client = Mock()
        driver.client.await_job.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
        driver.checkpoint = Mock()
        driver._phase = Mock()
        result = driver._job("task-run", command, timeout=600)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(driver.client.await_job.call_args.kwargs["control_timeout"], 0)
        driver.client.submit_job.assert_not_called()

    def test_remote_archive_preserves_files_with_unix_epoch_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote"
            remote.mkdir()
            (remote / "epoch.txt").write_bytes(b"original bytes")
            os.utime(remote / "epoch.txt", (0, 0))
            archive = root / "remote.zip"
            driver = object.__new__(AStudioSandboxDriver)
            driver.staging = root / "staging"
            driver.staging.mkdir()
            driver.client = Mock()

            def execute_archive(name, command, timeout):
                script = shlex.split(command)[2].replace(repr("/tmp/wcb-collect.zip"), repr(str(archive)))
                subprocess.run([sys.executable, "-c", script], check=True)

            driver._checked_job = execute_archive
            driver.client.download_to.side_effect = lambda sid, path, target: shutil.copyfile(archive, target)
            result = driver._download_tree("sid", str(remote), "collect")
            self.assertEqual((result / "epoch.txt").read_bytes(), b"original bytes")
            self.assertEqual(result.stat().st_mode & 0o222, 0)
            self.assertEqual((result / "epoch.txt").stat().st_mode & 0o222, 0)


if __name__ == "__main__":
    unittest.main()
