import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from src.e2e.agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from src.e2e.backend import WorkBuddySandboxDriver
from src.e2e.common import E2EError


class AgentCubeConfigurationTests(unittest.TestCase):
    def load(self, values):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            path.write_text(json.dumps({"user_id": "synthetic", **values}))
            with patch.dict(os.environ, {"AGENTCUBE_AUTH_TOKEN": "synthetic"}, clear=True):
                return AgentCubeConfig.load(path)

    def test_configured_namespace_and_creation_wait_reach_wire_contract(self):
        config = self.load({"namespace": "agentcube-windows", "template": "winarena-pc-20261116-b", "create_timeout_seconds": 1800})
        client = AgentCubeClient(config)
        self.addCleanup(client.close)
        response = Mock(status_code=200)
        response.json.return_value = {"code": 0, "data": {"sessionId": "original-session"}}
        client.http.request = Mock(return_value=response)
        self.assertEqual(client.create_session(), "original-session")
        call = client.http.request.call_args
        self.assertEqual(call.kwargs["timeout"], (10, 1800))
        self.assertEqual(call.kwargs["json"]["namespace"], "agentcube-windows")
        self.assertEqual(call.kwargs["json"]["name"], "winarena-pc-20261116-b")
        self.assertIn("/v1/namespaces/agentcube-windows/code-interpreters/", client.picod)
        self.assertIn("/v1/namespaces/agentcube-windows/code-interpreters/", client.windows)

    def test_legacy_preprocessing_registration_field_is_ignored(self):
        config = self.load({"preprocessing_profiles": [{"legacy": "entry"}]})
        self.assertEqual(config, self.load({}))

    def test_uncertain_creation_is_not_retried(self):
        client = AgentCubeClient(self.load({"create_timeout_seconds": 1800}))
        self.addCleanup(client.close)
        client.http.request = Mock(side_effect=requests.ReadTimeout("creation wait expired"))
        with self.assertRaises(PlatformError) as raised:
            client.create_session()
        self.assertTrue(raised.exception.uncertain)
        client.http.request.assert_called_once()

    def test_invalid_creation_wait_is_rejected(self):
        for value in [0, -1, True, 1.5, "1800", None]:
            with self.subTest(value=value), self.assertRaisesRegex(E2EError, "AGENTCUBE_CREATE_TIMEOUT_INVALID"):
                self.load({"create_timeout_seconds": value})

    def test_default_runtime_fingerprint_stays_compatible(self):
        legacy = {"workload_manager_url": "http://eval-agent-prod.maas.private", "router_url": "http://eval-agent-prod.maas.private", "namespace": "default", "template": "winarena-pc-20261104-a", "app_id": "AstronEval", "user_id": "synthetic", "active_ttl": 10800, "expire_ttl": 14400, "trust_env": False}
        self.assertEqual(AgentCubeConfig(**legacy).public(), legacy)
        config = self.load({"create_timeout_seconds": 1800})
        self.assertEqual(config.public()["create_timeout_seconds"], 1800)
        self.assertEqual(AgentCubeConfig(**config.public()).public(), config.public())

    def test_longer_creation_wait_requires_more_lifetime(self):
        driver = object.__new__(WorkBuddySandboxDriver)
        driver.unit = {"model": "GLM-5.3", "timeout_override": 600}
        driver.config = self.load({"active_ttl": 3600, "expire_ttl": 3600, "create_timeout_seconds": 1800})
        with self.assertRaisesRegex(E2EError, "PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT"):
            driver.preflight()
        self.assertEqual(self.load({}).required_expire_ttl(600), 3000)
        self.assertEqual(driver.config.required_expire_ttl(600), 3900)


    def test_private_upload_does_not_include_the_gateway_error_body(self):
        client = AgentCubeClient(self.load({}))
        self.addCleanup(client.close)
        response = Mock(status_code=502, text="synthetic-secret")
        client.http.request = Mock(return_value=response)
        with self.assertRaisesRegex(PlatformError, "^AGENTCUBE_PRIVATE_UPLOAD_FAILED$"):
            client.upload_private("session", "/run/wgui/.key", b"synthetic-secret")
        self.assertEqual(client.http.request.call_args.kwargs["data"], {
            "path": "/run/wgui/.key", "mode": "0600",
        })

    def test_chatgpt_gateway_requires_a_credential_free_https_url(self):
        good = "https://gateway.example/v1"
        self.assertEqual(self.load({"chatgpt_gateway_url": good}).public()["chatgpt_gateway_url"], good)
        for url in (2, "", "http://gateway/v1", "https://u:p@gateway/v1", "https://gateway/v1?token=secret"):
            with self.subTest(url=url), self.assertRaisesRegex(E2EError, "CHATGPT_GATEWAY_URL_INVALID"):
                self.load({"chatgpt_gateway_url": url})
