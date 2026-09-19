from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agents.minimax_code.transcript import (
    McodeTraceFormatError,
    convert_trace,
    write_conversion,
)


FIXTURE = Path(__file__).parent / "fixtures" / "minimax_code" / "trace.jsonl"


class MiniMaxCodeTranscriptTests(unittest.TestCase):
    def test_convert_trace_maps_completed_items_tools_and_usage(self) -> None:
        result = convert_trace(FIXTURE, prompt="Solve it")

        self.assertEqual(result.messages[0]["message"]["role"], "user")
        self.assertEqual(result.source["event_count"], 10)
        self.assertTrue(result.source["terminal_complete"])
        tool_uses = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_use"
        ]
        self.assertEqual(
            [(block["id"], block["name"]) for block in tool_uses],
            [("call-list", "bash"), ("call-bad", "read")],
        )
        self.assertEqual(tool_uses[1]["input"], {"_raw": "{broken"})
        tool_results = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_result"
        ]
        self.assertEqual(
            [block["status"] for block in tool_results],
            ["completed", "error"],
        )
        self.assertEqual(
            result.usage,
            {
                "input_tokens": 10,
                "output_tokens": 4,
                "cache_read_tokens": 3,
                "cache_write_tokens": 1,
                "total_tokens": 18,
                "provider_total_tokens": 14,
                "cost_usd": 0.0,
                "request_count": 1,
                "cost_status": "unavailable",
                "cost_source": "none",
                "cost_scope": "model_tokens_only",
                "cost_reason": "MiniMax Code stream-json exposes aggregate token usage but not provider cost; calculate cost from the model pricing registry when generating the report",
                "usage_source": "completed_responses",
                "usage_complete": True,
                "request_count_source": "minimum_one_from_exec_aggregate",
            },
        )

    def test_write_conversion_is_readable_by_wcb_parsers(self) -> None:
        from src.utils.grading import extract_usage_from_jsonl
        from src.utils.tool_metrics import _load_tool_pairs

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = write_conversion(FIXTURE, output_dir, prompt="Solve it")
            chat_path = output_dir / "chat.jsonl"
            self.assertEqual(
                extract_usage_from_jsonl(chat_path)["total_tokens"],
                result.usage["total_tokens"],
            )
            self.assertEqual(
                _load_tool_pairs(chat_path),
                [
                    ("bash", "README.md\n", "completed"),
                    ("read", '{"message":"not found"}', "error"),
                ],
            )
            manifest = json.loads(
                (output_dir / "conversion_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_format"], "minimax-code-exec-stream-json-v1")
            self.assertEqual(manifest["terminal_result"]["status"], "succeeded")

    def test_rejects_malformed_json_and_reverse_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            path.write_text("{broken}\n", encoding="utf-8")
            with self.assertRaisesRegex(McodeTraceFormatError, "line 1"):
                convert_trace(path)

            rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
            rows[1]["sequence"] = 1
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(McodeTraceFormatError, "increase strictly"):
                convert_trace(path)

    def test_rejects_missing_or_duplicate_terminal(self) -> None:
        rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows[:-1]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(McodeTraceFormatError, "exec.completed is missing"):
                convert_trace(path)

            partial = convert_trace(path, allow_incomplete=True)
            self.assertIsNone(partial.terminal_result)
            self.assertFalse(partial.source["terminal_complete"])

            duplicate = dict(rows[-1])
            duplicate["sequence"] = 11
            duplicate["timestampMs"] = 1010
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in [*rows, duplicate]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(McodeTraceFormatError, "cannot follow"):
                convert_trace(path)

    def test_usage_without_optional_metadata_is_still_complete_aggregate(self) -> None:
        rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
        result = rows[-1]["result"]
        result.pop("usageSource", None)
        result.pop("usageIncomplete", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            converted = convert_trace(path)

        self.assertEqual(converted.usage["usage_source"], "exec_result")
        self.assertTrue(converted.usage["usage_complete"])


if __name__ == "__main__":
    unittest.main()
