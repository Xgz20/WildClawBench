import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from src.e2e.agentcube import AgentCubeConfig, PlatformError
from src.e2e.artifacts import verify_execution
from src.e2e.common import E2EError, atomic_json, file_sha256
from src.e2e.creation_recovery import reconcile_absent_creation
from src.e2e.store import BatchStore


class CreationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "batch"
        self.root.mkdir()
        self.key = "unit/run-0001/task"
        self.item = {"key": self.key, "unit_id": "unit", "run_index": 1, "task_id": "task",
                     "attempt_id": "exec-one", "execution_root": "units/unit/runs/run-0001/tasks/task/executions/exec-one"}
        manifest = {"schema": "wildclawbench.sandbox-batch/v1", "plan": {"batch_id": "batch"}, "units": [], "tasks": []}
        atomic_json(self.root / "batch.json", manifest)
        self.store = BatchStore(self.root)
        self.store.initialize(manifest, [self.item])
        self.config = AgentCubeConfig(user_id="test", auth_token="synthetic", namespace="agentcube-windows", template="winarena-pc-20261116-b")
        self.intent_at = "2026-11-17T19:57:32.818190+08:00"
        self.original_error = {"code": "PlatformError", "message": "Read timed out"}
        self.store.update(self.key, "NEEDS_ATTENTION", resource_held=True,
                          runtime=self.config.public(), creation_intent_at=self.intent_at, error=self.original_error)
        self.proof = {"schema": "wildclawbench.agentcube-creation-observation/v1",
                      "identity": {"batch_id": "batch-r0001", "unit_id": "unit", "task_id": "task", "attempt_id": "exec-one"},
                      "creation_intent_at": self.intent_at, "session_id": "known-session", "observed_state": "destroyed",
                      "app_id": "AstronEval", "user_id": "test", "namespace": "agentcube-windows", "template": "winarena-pc-20261116-b",
                      "created_at": "2026-11-17T19:57:32+08:00", "destroyed_at": "2026-11-17T20:12:33+08:00",
                      "observed_at": "2026-11-17T20:20:00+08:00", "source_url": "https://sandbox.example/console/sandboxes",
                      "matching_session_count": 1}
        self.path = Path(self.temp.name) / "observation.json"
        self.client = Mock()
        self.absence = {"confirmed": True, "session_id": "known-session", "http_status": 200, "platform_code": 10001, "disposition": "already_absent"}
        self.client.confirm_session_absent.return_value = self.absence

    def tearDown(self):
        for path in self.root.rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        self.temp.cleanup()

    def reconcile(self, proof=None, config=None, expected_sha=None):
        atomic_json(self.path, proof or self.proof)
        return reconcile_absent_creation(self.root, self.key, self.path, expected_sha or file_sha256(self.path),
                                         config or self.config, client_factory=lambda frozen: self.client)

    def test_confirmed_absence_is_sealed_once_without_dispatch_or_remote_mutation(self):
        original_manifest = (self.root / "batch.json").read_bytes()
        self.reconcile()
        row = self.store.get(self.key)
        self.assertEqual(row["phase"], "FAILED")
        self.assertFalse(row["resource_held"])
        execution = self.root / self.item["execution_root"]
        receipt = verify_execution(execution)
        failure = json.loads((execution / "original/metadata/failure.json").read_text())
        self.assertEqual(failure["prior_error"], self.original_error)
        self.assertEqual((self.root / "batch.json").read_bytes(), original_manifest)
        self.assertFalse((execution / "execution-ready.json").exists())
        self.assertEqual(self.store.scoring_rows(), [])
        self.reconcile()
        self.assertEqual(verify_execution(execution)["archive_sha256"], receipt["archive_sha256"])
        self.assertEqual(self.store.get(self.key), row)
        self.client.create_session.assert_not_called()
        self.client.delete_session.assert_not_called()

    def test_mismatched_observation_never_releases_the_reservation(self):
        for field, value in [("namespace", "default"), ("user_id", "other"), ("template", "other"),
                             ("created_at", "2026-11-17T19:58:32+08:00"), ("observed_state", "running"),
                             ("matching_session_count", 2), ("matching_session_count", True)]:
            proof = copy.deepcopy(self.proof)
            proof[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(E2EError):
                self.reconcile(proof)
            self.assertTrue(self.store.get(self.key)["resource_held"])
        self.client.confirm_session_absent.assert_not_called()

    def test_live_or_unavailable_platform_state_does_not_release(self):
        self.client.confirm_session_absent.side_effect = PlatformError("SESSION_ABSENCE_NOT_CONFIRMED")
        with self.assertRaises(PlatformError):
            self.reconcile()
        self.assertIsNone(self.store.get(self.key).get("session_id"))
        self.assertTrue(self.store.get(self.key)["resource_held"])

    def test_dispatched_or_other_account_is_rejected(self):
        with self.assertRaisesRegex(E2EError, "ACCOUNT_MISMATCH"):
            self.reconcile(config=AgentCubeConfig(user_id="other"))
        self.store.update(self.key, "NEEDS_ATTENTION", dispatch_armed_at=self.intent_at)
        with self.assertRaisesRegex(E2EError, "DISPATCHED_EXECUTION"):
            self.reconcile()
        self.client.confirm_session_absent.assert_not_called()

    def test_tampered_input_proof_does_not_release(self):
        with self.assertRaisesRegex(E2EError, "SHA256_MISMATCH"):
            self.reconcile(expected_sha="0" * 64)
        self.assertTrue(self.store.get(self.key)["resource_held"])
