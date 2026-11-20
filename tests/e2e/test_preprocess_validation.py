from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from requests.exceptions import ReadTimeout

from src.e2e.agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from src.e2e.common import E2EError, read_json
from src.e2e.preprocess_validation import run_validation
from src.e2e.windows_preprocess import public_diagnostics


PROFILE = {"id": "fixture", "harness": "astronstudio", "template": "fixture-template",
           "enabled": True, "models": [{"id": "fixture-model"}]}
REQUEST = {
    "profile_id": "fixture", "model": "fixture-model",
    "recipe": {"version_id": 1, "version": 1, "name": "fixture", "steps": [
        {"kind": "powershell", "timeout": 20, "attachments": [],
         "asset": {"kind": "powershell", "name": "fixture.ps1", "size": 1, "sha256": "a" * 64}},
    ]},
}


class ValidationTests(unittest.TestCase):
    def run_fixture(self, driver, *, config=None, script_error=None, request=REQUEST):
        config = config or AgentCubeConfig(user_id="test-user")
        with (TemporaryDirectory() as directory,
              patch("src.e2e.preprocess_validation.profiles", return_value=[PROFILE]),
              patch("src.e2e.preprocess_validation.AgentCubeConfig.load", return_value=config),
              patch("src.e2e.preprocess_validation.apply_recipe", side_effect=script_error)):
            root = Path(directory) / "validation-fixture"
            root.mkdir()
            result = run_validation(root, request, None, driver_factory=Mock(return_value=driver))
            self.assertEqual(result, read_json(root / "validation.json"))
            return result

    def test_validation_creates_sandbox_using_standard_config_and_releases_without_dispatch(self):
        driver = Mock()
        driver.client.create_session.return_value = "original-session"
        driver.client.delete_session.return_value = {"confirmed": True}
        driver.client.windows_execute.return_value = {"output": "3.6.3\n"}
        result = self.run_fixture(driver)
        self.assertEqual((result["status"], result["cleanup"]), ("passed", "released"))
        self.assertEqual(result["planned_steps"], ["powershell"])
        self.assertEqual(result["target"]["client_version"], "3.6.3")
        driver.execute.assert_not_called()
        driver.client.create_session.assert_called_once_with()
        driver.client.delete_session.assert_called_once_with("original-session")
        self.assertIn(("preprocessing", "passed"), [(row["stage"], row["status"]) for row in result["events"]])

    def test_managed_template_is_used_and_recorded(self):
        driver = Mock()
        driver.client.create_session.return_value = "fixture-session"
        driver.client.delete_session.return_value = {"confirmed": True}
        binding = {"id": 1, "namespace": "managed-windows", "image_digest": "sha256:" + "f" * 64,
                   "profile_id": PROFILE["id"], "waa_revision": "a" * 40}
        result = self.run_fixture(driver, request={**REQUEST, "template": "managed-template", "template_binding": binding})
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["target"]["template"], "managed-template")
        self.assertEqual(result["target"]["template_binding"], binding)

    def test_creation_timeout_keeps_release_unconfirmed_and_skips_steps(self):
        client = AgentCubeClient(AgentCubeConfig())
        driver = Mock()
        driver.client.create_session = client.create_session
        with patch.object(client.http, "request", side_effect=ReadTimeout("private request data")):
            result = self.run_fixture(driver)
        client.close()
        self.assertEqual(result["error"], "AGENTCUBE_CREATE_REQUEST_TIMEOUT")
        self.assertEqual(result["cleanup"], "unconfirmed")
        self.assertNotIn("session_id", result)
        self.assertNotIn("private", str(result))
        self.assertFalse(any(row["stage"] == "preprocessing" for row in result["events"]))
        driver.client.delete_session.assert_not_called()

    def test_validation_still_rejects_insufficient_session_lifetime(self):
        driver = Mock()
        result = self.run_fixture(driver, config=AgentCubeConfig(user_id="test-user", active_ttl=100, expire_ttl=100))
        self.assertEqual((result["status"], result["cleanup"]), ("failed", "not_created"))
        self.assertEqual(result["error"], "PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT")
        driver.client.create_session.assert_not_called()

    def test_step_failure_and_cleanup_failure_are_separate_diagnostics(self):
        driver = Mock()
        driver.client.create_session.return_value = "original-session"
        driver.client.windows_execute.side_effect = PlatformError("Version probe unavailable")
        driver.client.delete_session.side_effect = [
            PlatformError("provider diagnostic: private body"), {"confirmed": False}, {"confirmed": False},
        ]
        with patch("src.e2e.preprocess_validation.time.sleep"):
            result = self.run_fixture(driver, script_error=E2EError("PREPROCESS_STEP_FAILED: private output"))
        self.assertEqual((result["status"], result["outcome"], result["cleanup"]), ("failed", "failed", "unconfirmed"))
        self.assertEqual(result["error"], "PREPROCESS_STEP_FAILED")
        self.assertNotIn("client_version", result["target"])
        self.assertNotIn("private", str(result))
        self.assertEqual(result["events"][-2]["error"], "PREPROCESS_VALIDATION_CLEANUP_UNCONFIRMED")

    def test_structured_powershell_diagnostics_only_keep_known_fields(self):
        result = public_diagnostics({"line": 2, "category": "NotSpecified", "exception": "WriteErrorException",
                                     "error_id": "PREPROCESS_ASSERTION_FAILED",
                                     "stderr": "credential", "winerror": "invalid", "rpc_code": -32602})
        self.assertEqual(result, {"line": 2, "category": "NotSpecified", "exception": "WriteErrorException",
                                  "error_id": "PREPROCESS_ASSERTION_FAILED",
                                  "rpc_code": -32602})
