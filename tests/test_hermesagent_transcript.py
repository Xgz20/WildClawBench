from __future__ import annotations

import json
import unittest

from src.agents.hermesagent.compat_transcript import _to_openclaw_messages


class HermesAgentTranscriptTest(unittest.TestCase):
    def test_tool_result_is_nested_in_standard_user_message(self) -> None:
        converted = _to_openclaw_messages([
            {
                "role": "assistant",
                "content": "checking",
                "tool_calls": [{
                    "id": "call-1",
                    "function": {
                        "name": "execute_code",
                        "arguments": json.dumps({"code": "print('ok')"}),
                    },
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": '{"status":"success","output":"ok"}',
            },
        ])

        self.assertEqual(converted[1]["type"], "message")
        self.assertEqual(converted[1]["message"]["role"], "user")
        block = converted[1]["message"]["content"][0]
        self.assertEqual(block["type"], "tool_result")
        self.assertEqual(block["tool_use_id"], "call-1")
        self.assertIn('"status":"success"', block["content"])


if __name__ == "__main__":
    unittest.main()
