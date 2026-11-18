from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.e2e.agentcube import AgentCubeConfig, PlatformError
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
    def run_fixture(self, driver, *, admitted=True, script_error=None):
        config = AgentCubeConfig(user_id="test-user")
        if admitted:
            config = AgentCubeConfig(user_id="test-user", preprocessing_profiles=({
                "namespace": config.namespace, "template": PROFILE["template"], "app_id": config.app_id,
                "user_id": config.user_id, "actions": ["powershell"], "isolation_receipt": "b" * 64,
            },))
        with (TemporaryDirectory() as directory,
              patch("src.e2e.preprocess_validation.profiles", return_value=[PROFILE]),
              patch("src.e2e.preprocess_validation.AgentCubeConfig.load", return_value=config),
              patch("src.e2e.preprocess_validation.apply_recipe", side_effect=script_error)):
            root = Path(directory) / "validation-fixture"
            root.mkdir()
            result = run_validation(root, REQUEST, None, driver_factory=Mock(return_value=driver))
            self.assertEqual(result, read_json(root / "validation.json"))
            return result

    def test_validation_checks_exact_steps_then_releases_without_dispatch(self):
        driver = Mock()
        driver.client.create_session.return_value = "original-session"
        driver.client.delete_session.return_value = {"confirmed": True}
        result = self.run_fixture(driver)
        self.assertEqual((result["status"], result["cleanup"]), ("passed", "released"))
        self.assertEqual(result["planned_steps"], ["powershell"])
        driver.execute.assert_not_called()
        driver.client.delete_session.assert_called_once_with("original-session")
        self.assertIn(("preprocessing", "passed"), [(row["stage"], row["status"]) for row in result["events"]])

    def test_validation_does_not_create_sandbox_until_admitted(self):
        driver = Mock()
        result = self.run_fixture(driver, admitted=False)
        self.assertEqual((result["status"], result["cleanup"]), ("failed", "not_created"))
        self.assertEqual(result["error"], "PREPROCESS_SANDBOX_ISOLATION_NOT_VERIFIED")
        driver.client.create_session.assert_not_called()

    def test_step_failure_and_cleanup_failure_are_separate_diagnostics(self):
        driver = Mock()
        driver.client.create_session.return_value = "original-session"
        driver.client.delete_session.side_effect = [
            PlatformError("provider diagnostic: private body"), {"confirmed": False}, {"confirmed": False},
        ]
        with patch("src.e2e.preprocess_validation.time.sleep"):
            result = self.run_fixture(driver, script_error=E2EError("PREPROCESS_STEP_FAILED: private output"))
        self.assertEqual((result["status"], result["outcome"], result["cleanup"]), ("failed", "failed", "unconfirmed"))
        self.assertEqual(result["error"], "PREPROCESS_STEP_FAILED")
        self.assertNotIn("private", str(result))
        self.assertEqual(result["events"][-2]["error"], "PREPROCESS_VALIDATION_CLEANUP_UNCONFIRMED")

    def test_structured_powershell_diagnostics_only_keep_known_fields(self):
        result = public_diagnostics({"line": 2, "category": "NotSpecified", "exception": "WriteErrorException",
                                     "error_id": "PREPROCESS_ASSERTION_FAILED",
                                     "stderr": "credential", "winerror": "invalid", "rpc_code": -32602})
        self.assertEqual(result, {"line": 2, "category": "NotSpecified", "exception": "WriteErrorException",
                                  "error_id": "PREPROCESS_ASSERTION_FAILED",
                                  "rpc_code": -32602})
