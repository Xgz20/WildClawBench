"""Gateway error envelopes must never masquerade as downloaded task artifacts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import requests

from src.e2e.agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from src.e2e.engine import _error_record


JOB = {"remote_directory": "/tmp/wcb-e2e-jobs/original", "submission": "confirmed"}


def response(body, *, attachment=False, content_type="application/json", status=200):
    value = requests.Response()
    value.status_code = status
    value._content = body
    value._content_consumed = True
    value.headers["Content-Type"] = content_type
    if attachment:
        value.headers["Content-Disposition"] = 'attachment; filename="result.json"'
    value.close = Mock()
    return value


def rejected(code=20007):
    return response(json.dumps({"code": code, "msg": "sandbox unreachable private-auth-token", "data": None}).encode())


class AgentCubeFileErrorTests(unittest.TestCase):
    def client(self):
        client = AgentCubeClient(AgentCubeConfig(auth_token="private-auth-token"))
        self.addCleanup(client.close)
        return client

    def test_http_200_error_is_a_platform_fault_with_original_code(self):
        client = self.client()
        client._request = Mock(return_value=rejected())
        with self.assertRaises(PlatformError) as caught:
            client.download("original-session", JOB["remote_directory"] + "/exit_code")
        error = caught.exception
        self.assertEqual(str(error), "AGENTCUBE_SANDBOX_UNREACHABLE")
        self.assertTrue(error.uncertain)
        self.assertEqual(error.platform_code, "20007")
        self.assertEqual(_error_record(error)["fault_domain"], "agentcube")
        self.assertEqual(_error_record(error)["platform_code"], "20007")
        self.assertNotIn("private-auth-token", str(error))
        for operation in (lambda: client.execute("original-session", "true"),
                          lambda: client.windows_download("original-session", "result.json")):
            with self.assertRaisesRegex(PlatformError, "AGENTCUBE_SANDBOX_UNREACHABLE"):
                operation()

    def test_error_stream_does_not_overwrite_existing_artifact_or_leave_partial(self):
        client = self.client()
        value = rejected()
        client._request = Mock(return_value=value)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "backup.zip"
            target.write_bytes(b"original-valid-backup")
            with self.assertRaises(PlatformError):
                client.download_to("original-session", "/backup.zip", target)
            self.assertEqual(target.read_bytes(), b"original-valid-backup")
            self.assertEqual(list(Path(directory).iterdir()), [target])
        value.close.assert_called_once()

    def test_json_attachments_and_large_files_keep_exact_bytes(self):
        client = self.client()
        bodies = [json.dumps({"code": 20007, "msg": "business data", "data": None}).encode(),
                  b'{"data":"' + b"x" * (1024 * 1024 + 17) + b'"}']
        for body in bodies:
            for attachment in (True, False) if len(body) > 65536 else (True,):
                with self.subTest(size=len(body), attachment=attachment), TemporaryDirectory() as directory:
                    client._request = Mock(return_value=response(body, attachment=attachment))
                    target = Path(directory) / "result.json"
                    client.download_to("sid", "/result.json", target)
                    self.assertEqual(target.read_bytes(), body)
                    self.assertEqual(client.download("sid", "/result.json"), body)
        ordinary = b'{"code":500,"data":{"answer":42},"msg":"business"}'
        client._request = Mock(return_value=response(ordinary))
        self.assertEqual(client.download("sid", "/result.json"), ordinary)

    def test_transient_gateway_failure_retries_reading_same_job_without_resending(self):
        client = self.client()
        client._request = Mock(side_effect=[rejected(), response(b"0", content_type="application/octet-stream"),
                                            response(b"done", content_type="text/plain"), response(b"", content_type="text/plain")])
        client.submit_job = Mock(side_effect=AssertionError("must not resend"))
        client.create_session = Mock(side_effect=AssertionError("must not replace session"))
        with patch("src.e2e.agentcube.time.sleep"):
            result = client.await_job("original-session", JOB)
        self.assertEqual(result, {"exit_code": 0, "stdout": "done", "stderr": ""})
        self.assertEqual(client._request.call_count, 4)
        self.assertTrue(all(call.kwargs["sid"] == "original-session" for call in client._request.call_args_list))
        client.submit_job.assert_not_called()
        client.create_session.assert_not_called()

    def test_persistent_router_failure_keeps_platform_code_after_bounded_observation(self):
        client = self.client()
        client._request = Mock(return_value=rejected())
        with patch("src.e2e.agentcube.time.sleep"), self.assertRaises(PlatformError) as caught:
            client.await_job("sid", JOB)
        self.assertIn("REMOTE_JOB_OBSERVATION_UNAVAILABLE", str(caught.exception))
        self.assertEqual(caught.exception.platform_code, "20007")
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(client._request.call_count, 5)

    def test_missing_exit_file_checks_original_pid_and_lost_job_is_not_a_running_job(self):
        client = self.client()
        client.download = Mock(side_effect=[FileNotFoundError("exit_code"), b"123"])
        self.assertIsNone(client.poll_job("sid", JOB))
        client.download = Mock(side_effect=FileNotFoundError("missing"))
        with self.assertRaisesRegex(PlatformError, "REMOTE_JOB_STATE_MISSING") as caught:
            client.poll_job("sid", JOB)
        self.assertTrue(caught.exception.uncertain)

    def test_malformed_exit_codes_are_diagnostic_failures_never_value_error_or_zero(self):
        for body in (b"not a number", b'{"code":20007}', b"\xff", b"9" * 100, b"2147483648"):
            client = self.client()
            client._request = Mock(return_value=response(body, content_type="application/octet-stream"))
            with self.subTest(body=body[:20]), self.assertRaisesRegex(PlatformError, "REMOTE_JOB_EXIT_CODE_INVALID") as caught:
                client.poll_job("sid", JOB)
            self.assertTrue(caught.exception.uncertain)
