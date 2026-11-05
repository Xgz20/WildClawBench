import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
import zipfile

from src.e2e import DEFAULT_EXECUTION_CONCURRENCY
from src.e2e.poc import (EXPECTED_CWD, bind_rollout, redact, require_known_creation_state,
                         reference_client_options, reference_protocol, run_poc, seal_result,
                         strict_answer, validate_members, windows_execution_result)


class PocTests(unittest.TestCase):
    def test_controller_v2_injects_client_configuration_and_keeps_v1_shape(self):
        legacy = SimpleNamespace()
        modern = SimpleNamespace(RUN_REQUEST={"schema_version": 2})
        config = {name.upper(): name for name in (
            "workload_manager_url", "router_url", "namespace", "template", "app_id", "user_id",
            "auth_token", "active_ttl", "expire_ttl")}
        self.assertEqual(reference_protocol(legacy), 1)
        self.assertEqual(reference_client_options(legacy, config), {})
        self.assertEqual(reference_client_options(modern, config)["user_id"], "user_id")
        with self.assertRaisesRegex(ValueError, "PROTOCOL_UNSUPPORTED"):
            reference_protocol(SimpleNamespace(RUN_REQUEST={"schema_version": 3}))

    def test_windows_execute_unwraps_observed_platform_envelope(self):
        raw = {"output": "encoded-native-inventory", "returncode": 0, "status": "success"}
        self.assertEqual(windows_execution_result({"code": 0, "data": raw}), raw)
        self.assertEqual(windows_execution_result(raw), raw)
        with self.assertRaisesRegex(ValueError, "BUSINESS_ERROR"):
            windows_execution_result({"code": 401, "data": raw})
        with self.assertRaisesRegex(ValueError, "RESPONSE_INVALID"):
            windows_execution_result({"code": 0, "data": {}})

    def test_answer_rejects_wrong_digits_and_failure_messages(self):
        self.assertTrue(strict_answer("3\n"))
        for answer in ("999", "失败于2026年", "3 files", "٣"):
            self.assertFalse(strict_answer(answer))
        self.assertEqual(DEFAULT_EXECUTION_CONCURRENCY, 3)

    def test_binding_requires_native_user_message_and_cwd(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "native-1", "cwd": EXPECTED_CWD}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "原始题目"}},
        ]
        data = "\n".join(json.dumps(row) for row in rows).encode()
        self.assertTrue(bind_rollout(data, "原始题目")["verified"])
        self.assertFalse(bind_rollout(data, "另一道题目")["verified"])
        rows[0]["payload"]["cwd"] = r"C:\other\project"
        self.assertFalse(bind_rollout("\n".join(json.dumps(row) for row in rows).encode(), "原始题目")["verified"])

    def test_secret_redaction_in_nested_errors(self):
        value = {"AUTH_TOKEN": "secret", "details": ["Bearer secret", "request secret failed"]}
        result = json.dumps(redact(value, "secret"))
        self.assertNotIn("secret", result)
        self.assertIn("[REDACTED]", result)

    def test_zip_rejects_traversal_and_duplicate_members(self):
        for name in ("../escaped", "/absolute", r"dir\file", "C:/absolute"):
            with self.subTest(name=name):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr(name, "data")
                with zipfile.ZipFile(buffer) as archive:
                    with self.assertRaises(ValueError):
                        validate_members(archive)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive, warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            archive.writestr("same", "one")
            archive.writestr("same", "two")
        with zipfile.ZipFile(buffer) as archive:
            with self.assertRaises(ValueError):
                validate_members(archive)

    def test_backup_preserves_exact_bytes_and_detectable_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch = Path(temporary)
            staging = batch / "staging"
            (staging / "workspace").mkdir(parents=True)
            payload = b"original\r\n\x00bytes"
            (staging / "workspace/answer.md").write_bytes(payload)
            receipt = seal_result(batch, staging)
            archive_path = batch / receipt["archive"]
            self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), receipt["sha256"])
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.read("workspace/answer.md"), payload)
            self.assertEqual((batch / "original/workspace/answer.md").read_bytes(), payload)

    def test_unknown_create_prevents_another_session_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = root / "batches/previous/poc-state.json"
            previous.parent.mkdir(parents=True)
            config = {"WORKLOAD_MANAGER_URL": "http://platform", "TEMPLATE": "windows"}
            previous.write_text(json.dumps({"session_creation": "uncertain", "configuration": config}))
            with self.assertRaisesRegex(ValueError, "UNRESOLVED_SESSION_CREATION"):
                require_known_creation_state(root, config)

    def test_transport_failure_is_persisted_once_and_backed_up(self):
        calls = []

        class ReferenceClient:
            def __init__(self):
                self.http = SimpleNamespace(close=lambda: None)

            def create_session(self):
                calls.append("create")
                raise ConnectionError("lost response")

        class ReferenceFlow:
            def __init__(self, client, run_dir, keep):
                self.client, self.sid = client, None

            def create_session(self):
                self.sid = self.client.create_session()

        reference = SimpleNamespace(AgentCubeClient=ReferenceClient, BvtFlow=ReferenceFlow,
                                    STEPS=[("create_session", "create")])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reference.py"
            source.write_text("CONFIG = {'AUTH_TOKEN': 'test-secret'}\n")
            args = SimpleNamespace(reference_script=source, agentcube_config=None, template=None,
                                   batch_id="failure", workspace_root=root, trust_env=False,
                                   keep_on_failure=False)
            with patch("src.e2e.poc.load_reference", return_value=reference), patch("builtins.print"):
                self.assertEqual(run_poc(args), 3)
            state = json.loads((root / "batches/failure/poc-state.json").read_text())
            self.assertEqual(calls, ["create"])
            self.assertEqual(state["session_creation"], "uncertain")
            self.assertEqual(state["cleanup"], "unknown_session_may_exist")
            self.assertTrue((root / "batches/failure/backups/backup-receipt.json").is_file())
            self.assertNotIn("test-secret", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
