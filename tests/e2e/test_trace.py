import json
from pathlib import Path
import tempfile
import unittest

from src.e2e.common import E2EError
from src.e2e.trace import normalize_rollout
from tests.e2e.test_scheduler import GUEST, native_fixture


class NativeMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rollout.jsonl"
        self.rows = [json.loads(line) for line in native_fixture("prompt", "session", "turn").splitlines()]
        call = self.rows[3]["payload"]
        call.update(name="mcp__acode_apps__connector_sites__manage_site", arguments='{"operation":"create"}')
        self.end = {"type": "mcp_tool_call_end", "call_id": "call-1",
                    "invocation": {"server": "acode_apps", "tool": "manage_site", "arguments": {"operation": "create"}},
                    "result": {"Ok": {"content": [{"type": "text", "text": "created"}]}}}
        self.rows.insert(4, {"type": "event_msg", "payload": self.end})

    def tearDown(self):
        self.temp.cleanup()

    def normalize(self):
        self.path.write_text("\n".join(json.dumps(row) for row in self.rows), encoding="utf-8")
        return normalize_rollout(self.path, identity={"batch_id": "b", "unit_id": "u", "task_id": "t", "attempt_id": "a"},
                                 prompt="prompt", guest_cwd=GUEST, requested_model="spark-x2.6", requested_effort="high",
                                 report={"usage": {"input_tokens": 100, "output_tokens": 10, "cache_tokens": 50}})

    def test_mcp_end_keeps_native_metadata_without_duplicating_tools(self):
        value = self.normalize()
        self.assertEqual(value["missing"], [])
        self.assertEqual(len(value["calls"]), 1)
        meta = next(event for event in value["events"] if event.get("content") == "mcp_tool_call_end")
        self.assertEqual(meta["native_status"], self.end)

    def test_mcp_end_with_wrong_invocation_is_rejected(self):
        self.end["invocation"]["arguments"] = {"operation": "delete"}
        with self.assertRaisesRegex(E2EError, "MCP_INVOCATION_MISMATCH"):
            self.normalize()

    def test_mcp_end_without_canonical_pair_marks_trace_incomplete(self):
        self.end["call_id"] = "unbound-call"
        self.assertIn("mcp-end-without-canonical-pair", self.normalize()["missing"])
