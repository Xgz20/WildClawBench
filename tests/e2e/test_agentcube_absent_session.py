import unittest
from unittest.mock import Mock

from src.e2e.agentcube import AgentCubeClient, AgentCubeConfig, PlatformError


class AbsentSessionTests(unittest.TestCase):
    def client(self, message, code=10001):
        client = AgentCubeClient(AgentCubeConfig())
        self.addCleanup(client.close)
        response = Mock(status_code=200, content=b"json")
        response.json.return_value = {"code": code, "msg": message, "data": None}
        client._request = Mock(return_value=response)
        return client

    def test_exact_session_absence_is_idempotent_cleanup(self):
        c = self.client("sessionId original not found")
        self.assertEqual(c.delete_session("original")["disposition"], "already_absent")

    def test_other_identity_or_error_never_releases_resource(self):
        for message, code in [("sessionId other not found", 10001),
                              ("permission denied", 10001),
                              ("sessionId original not found", 20008)]:
            with self.subTest(message=message, code=code):
                with self.assertRaises(PlatformError):
                    self.client(message, code).delete_session("original")

    def test_read_only_absence_requires_exact_session_and_platform_response(self):
        client = self.client("sessionId original not found")
        self.assertTrue(client.confirm_session_absent("original")["confirmed"])
        self.assertEqual(client._request.call_args.args[0], "GET")
        for message, code in [("sessionId other not found", 10001), ("permission denied", 10001),
                              ("sessionId original not found", 10005)]:
            with self.subTest(message=message, code=code), self.assertRaises(PlatformError):
                self.client(message, code).confirm_session_absent("original")
