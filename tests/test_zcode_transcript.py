from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agents.zcode.transcript import (
    ZCodeTraceFormatError,
    convert_trace,
    write_conversion,
)


FIXTURE = Path(__file__).parent / "fixtures" / "zcode" / "trace.jsonl"


class ZCodeTranscriptTests(unittest.TestCase):
    def test_convert_trace_maps_stream_tools_and_usage(self) -> None:
        result = convert_trace(FIXTURE, prompt="Solve it")

        self.assertEqual(result.messages[0]["message"]["role"], "user")
        self.assertEqual(result.source["event_count"], 8)
        self.assertTrue(result.source["terminal_complete"])
        tool_uses = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_use"
        ]
        self.assertEqual(tool_uses, [{
            "type": "tool_use",
            "id": "call-1",
            "name": "Bash",
            "input": {"command": "ls"},
        }])
        tool_results = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_result"
        ]
        self.assertEqual(tool_results[0]["status"], "completed")
        self.assertEqual(tool_results[0]["content"], "README.md\n")
        self.assertEqual(result.usage["input_tokens"], 10)
        self.assertEqual(result.usage["output_tokens"], 4)
        self.assertEqual(result.usage["cache_read_tokens"], 3)
        self.assertEqual(result.usage["cache_write_tokens"], 1)
        self.assertEqual(result.usage["reasoning_tokens"], 2)
        self.assertEqual(result.usage["total_tokens"], 18)
        self.assertEqual(result.usage["provider_total_tokens"], 14)
        self.assertEqual(result.usage["request_count"], 2)

    def test_write_conversion_is_readable_by_wcb_parsers(self) -> None:
        from src.utils.grading import extract_usage_from_jsonl
        from src.utils.tool_metrics import _load_tool_pairs

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = write_conversion(FIXTURE, output_dir, prompt="Solve it")
            self.assertEqual(
                extract_usage_from_jsonl(output_dir / "chat.jsonl")["total_tokens"],
                result.usage["total_tokens"],
            )
            self.assertEqual(
                _load_tool_pairs(output_dir / "chat.jsonl"),
                [("Bash", "README.md\n", "completed")],
            )
            manifest = json.loads(
                (output_dir / "conversion_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_format"], "zcode-headless-stream-json-v1")
            self.assertEqual(manifest["terminal_result"]["response"], "Done.")

    def test_rejects_bad_sequence_and_missing_terminal(self) -> None:
        rows = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            rows[2]["seq"] = 1
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(ZCodeTraceFormatError, "increase strictly"):
                convert_trace(path)

            rows = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows[:-1]))
            with self.assertRaisesRegex(ZCodeTraceFormatError, "result row is missing"):
                convert_trace(path)
            partial = convert_trace(path, allow_incomplete=True)
            self.assertIsNone(partial.terminal_result)


if __name__ == "__main__":
    unittest.main()
