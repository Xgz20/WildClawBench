import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.e2e.common import E2EError, digest
from src.e2e.windows_runtime import installer_script, prepare_runtime, read_session, validate_runtime


def specification():
    return {"version": "3.6.3", "download_url": "https://example.test/installer.exe",
            "size": 1234, "sha512": "a" * 128, "sync_clock": False}


class WindowsRuntimeTests(unittest.TestCase):
    def test_invalid_release_is_rejected_before_remote_action(self):
        for change in [{"download_url": "http://example.test/file"}, {"sha512": "short"}, {"size": 0}]:
            with self.subTest(change=change), self.assertRaises(E2EError):
                validate_runtime({**specification(), **change})

    def test_session_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps({"uid": "user", "token": "login-secret", "modelBearerToken": "model-secret"}))
            path.chmod(0o644)
            with self.assertRaises(E2EError):
                read_session(path)
            path.chmod(0o600)
            self.assertEqual(json.loads(read_session(path))["uid"], "user")

    def test_unknown_launch_is_observed_without_installing_again(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = specification()
            state = {"identity": digest({**spec, "model": "auto", "session_sha256": None}), "launch_intent": "earlier"}
            driver = SimpleNamespace(config=SimpleNamespace(astudio_runtime=spec), store=Mock(), key="key",
                                     staging=Path(directory), client=Mock(), checkpoint=Mock(), _phase=Mock(), _checked_job=Mock())
            driver.store.get.return_value = {"attempt_id": "exec-test", "runtime_prepare": state}
            driver.client.windows_execute.return_value = {"output": json.dumps({"version": "3.6.3", "stage": "ready", "identity": state["identity"]})}
            prepare_runtime(driver, "sid", "wgui", lambda s: s)
            driver.client.upload.assert_not_called()
            driver._checked_job.assert_not_called()
            self.assertEqual(driver.client.windows_execute.call_count, 1)
            self.assertIn("Get-Content", driver.client.windows_execute.call_args.args[1])
            self.assertTrue(driver._phase.call_args.kwargs["runtime_prepare"]["ready"])

    def test_changed_runtime_cannot_replace_an_existing_intent(self):
        driver = SimpleNamespace(config=SimpleNamespace(astudio_runtime=specification()), store=Mock(), key="key")
        driver.store.get.return_value = {"runtime_prepare": {"identity": "different", "launch_intent": "earlier"}}
        with self.assertRaisesRegex(E2EError, "INPUT_DRIFT"):
            prepare_runtime(driver, "sid", "wgui", lambda s: s)

    def test_failed_preparation_is_reported_without_being_swallowed_as_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = specification()
            state = {"identity": digest({**spec, "model": "auto", "session_sha256": None}), "launch_intent": "earlier"}
            driver = SimpleNamespace(config=SimpleNamespace(astudio_runtime=spec), store=Mock(), key="key",
                                     staging=Path(directory), client=Mock(), checkpoint=Mock(), _phase=Mock())
            driver.store.get.return_value = {"runtime_prepare": state}
            driver.client.windows_execute.return_value = {"output": json.dumps({"version": "3.6.3", "identity": state["identity"], "stage": "failed", "details": {"error": "test-error"}})}
            with self.assertRaisesRegex(E2EError, "PREPARATION_FAILED: test-error"):
                prepare_runtime(driver, "sid", "wgui", lambda s: s)
            self.assertEqual(driver.client.windows_execute.call_count, 1)

    def test_windows_script_upload_preserves_unicode_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = specification()
            identity = digest({**spec, "model": "auto", "session_sha256": None})
            driver = SimpleNamespace(config=SimpleNamespace(astudio_runtime=spec), store=Mock(), key="key",
                                     staging=Path(directory), client=Mock(), checkpoint=Mock(), _phase=Mock(), _checked_job=Mock())
            driver.store.get.return_value = {"attempt_id": "exec-test", "phase": "PREPARING"}
            driver.client.windows_execute.return_value = {"output": json.dumps({"version": "3.6.3", "identity": identity, "stage": "ready"})}
            prepare_runtime(driver, "sid", "wgui", lambda s: s)
            raw = driver.client.upload.call_args.args[2]
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn("原合同", raw.decode("utf-8-sig"))

    def test_installer_is_verified_before_execution_and_uses_private_backup(self):
        script = installer_script(specification())
        self.assertLess(script.index("ASTUDIO_INSTALLER_DIGEST_MISMATCH"), script.index("Start-Process $file"))
        self.assertIn("backup-before-install", script)
        self.assertIn("/KEEP_APP_DATA", script)
        self.assertNotIn("login-secret", script)

    def test_session_override_requires_explicit_snapshot_request(self):
        template = installer_script(specification())
        self.assertIn("$restoreSession=$false", template)
        self.assertIn("if($restoreSession){", template)
        self.assertIn("sessionRestored=$restoreSession", template)
        self.assertIn("loginSource=", template)
        explicit = installer_script({**specification(), "session_file": "/private/session.json"})
        self.assertIn("$restoreSession=$true", explicit)
        self.assertIn("ASTRON_REQUESTED_SESSION_FILE_MISSING", explicit)
