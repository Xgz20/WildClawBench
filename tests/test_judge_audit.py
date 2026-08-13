from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.utils.judge_audit import write_attempt


class JudgeAuditTest(unittest.TestCase):
    def test_write_attempt_redacts_credentials_and_image_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_attempt(
                Path(tmp),
                1,
                {"headers": {"authorization": "Bearer secret", "x-api-key": "raw-secret"}, "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": "OPENROUTER_API_KEY=sk-live-secret Bearer abc.def.ghi"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    ]}
                ]},
                {"content": [{"type": "text", "text": "{}"}], "api_key": "secret"},
                {},
            )
            request = json.loads((Path(tmp) / "attempt-001/request.json").read_text())
            response = json.loads((Path(tmp) / "attempt-001/response.json").read_text())
            self.assertEqual(request["headers"]["authorization"], "[REDACTED]")
            self.assertEqual(request["headers"]["x-api-key"], "[REDACTED]")
            self.assertNotIn("sk-live-secret", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("abc.def.ghi", request["messages"][0]["content"][0]["text"])
            self.assertEqual(request["messages"][0]["content"][1]["image_url"]["url"], "[IMAGE_DATA_OMITTED]")
            self.assertEqual(response["api_key"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
