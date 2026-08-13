from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from src.utils import judge_shim


class JudgeShimTest(unittest.TestCase):
    @patch("src.utils.judge_shim.request.urlopen")
    def test_anthropic_json_request_forces_submit_grading_tool(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = json.dumps({
            "id": "msg_1",
            "model": "claude-test",
            "stop_reason": "tool_use",
            "content": [{
                "type": "tool_use",
                "name": "submit_grading",
                "input": {"scores": {"quality": 0.8}, "notes": "ok"},
            }],
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
        }):
            result = judge_shim._anthropic_create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "grade"}],
                response_format={"type": "json_object"},
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["tool_choice"], {"type": "tool", "name": "submit_grading"})
        self.assertEqual(payload["tools"][0]["name"], "submit_grading")
        self.assertEqual(
            json.loads(result.choices[0].message.content),
            {"scores": {"quality": 0.8}, "notes": "ok"},
        )
        self.assertEqual(result.choices[0].finish_reason, "tool_use")
        self.assertEqual(result._raw_response["id"], "msg_1")

    @patch("src.utils.judge_shim.request.urlopen")
    def test_non_json_anthropic_request_does_not_add_tools(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = b'{"content":[{"type":"text","text":"ok"}],"usage":{}}'
        urlopen.return_value.__enter__.return_value = response
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
        }):
            judge_shim._anthropic_create(
                model="anthropic/claude-test",
                messages=[{"role": "user", "content": "hello"}],
            )
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("tools", payload)


if __name__ == "__main__":
    unittest.main()
