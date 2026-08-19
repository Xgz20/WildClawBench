from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.maas_proxy import (
    MAAS_PROXY_AUDIT_NAME,
    MAAS_PROXY_BASE_URL,
    collect_maas_request_audit,
    start_maas_request_proxy,
)
from src.utils.maas_request_proxy import inject_max_tokens


class MaasRequestProxyTests(unittest.TestCase):
    def test_inject_max_tokens_adds_and_overrides_field(self) -> None:
        for request, previous in (
            ({"model": "xopglm52", "input": []}, None),
            ({"model": "xopglm52", "max_tokens": 2048}, 2048),
        ):
            with self.subTest(previous=previous):
                body, actual_previous = inject_max_tokens(
                    json.dumps(request).encode("utf-8"), 4096
                )
                self.assertEqual(actual_previous, previous)
                self.assertEqual(json.loads(body)["max_tokens"], 4096)

    def test_start_proxy_copies_starts_and_waits_for_readiness(self) -> None:
        success = subprocess.CompletedProcess([], 0, "", "")
        with patch("src.utils.maas_proxy.subprocess.run", side_effect=[success] * 3) as run:
            base_url = start_maas_request_proxy(
                "case-id",
                upstream_base_url="https://maas-api.example/v1",
                max_tokens=8192,
            )

        self.assertEqual(base_url, MAAS_PROXY_BASE_URL)
        start_command = run.call_args_list[1].args[0]
        self.assertIn("--max-tokens", start_command)
        self.assertEqual(start_command[start_command.index("--max-tokens") + 1], "8192")
        self.assertNotIn("OPENROUTER_API_KEY", " ".join(start_command))

    def test_collect_audit_is_optional_and_uses_atomic_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            missing = subprocess.CompletedProcess([], 1, "", "missing")
            with patch("src.utils.maas_proxy.subprocess.run", return_value=missing):
                self.assertFalse(collect_maas_request_audit("case-id", output_dir))
            self.assertFalse((output_dir / MAAS_PROXY_AUDIT_NAME).exists())


if __name__ == "__main__":
    unittest.main()
