from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agents.deepseek_harness.transcript import (
    DshSessionFormatError,
    convert_sessions,
    write_conversion,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "deepseek_harness"


class DeepSeekHarnessTranscriptTests(unittest.TestCase):
    def test_convert_sessions_maps_messages_tools_and_usage(self) -> None:
        result = convert_sessions(FIXTURE_ROOT)

        self.assertEqual(
            result.usage,
            {
                "input_tokens": 18,
                "output_tokens": 7,
                "cache_read_tokens": 2,
                "cache_write_tokens": 4,
                "total_tokens": 31,
                "cost_usd": 0.0,
                "request_count": 3,
                "cost_status": "unavailable",
                "cost_source": "none",
                "cost_scope": "model_tokens_only",
                "cost_reason": "DSH sessions expose token usage but not provider cost; calculate cost from the model pricing registry when generating the report",
            },
        )
        self.assertEqual(
            [session["id"] for session in result.sessions],
            ["root-session", "child-session"],
        )
        self.assertEqual(result.messages[0]["message"]["role"], "user")

        tool_uses = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_use"
        ]
        self.assertEqual([block["id"] for block in tool_uses].count("call-list"), 1)
        self.assertEqual(tool_uses[0]["input"], {"command": "ls"})
        self.assertEqual(tool_uses[1]["input"], {"_raw": "{broken"})
        self.assertEqual(tool_uses[2]["input"], {"_value": 42})

        tool_results = [
            block
            for entry in result.messages
            for block in entry["message"]["content"]
            if block.get("type") == "tool_result"
        ]
        self.assertEqual(
            [(block["tool_use_id"], block["status"]) for block in tool_results],
            [
                ("call-list", "completed"),
                ("call-invalid", "error"),
                ("call-child", "error"),
            ],
        )
        self.assertIn("README.md", tool_results[0]["content"])
        self.assertEqual(tool_results[2]["content"], '{"answer":42}')

    def test_write_conversion_writes_jsonl_usage_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = write_conversion(FIXTURE_ROOT, output_dir)

            chat_rows = [
                json.loads(line)
                for line in (output_dir / "chat.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            usage = json.loads((output_dir / "usage.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (output_dir / "conversion_manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(chat_rows, result.messages)
            self.assertEqual(usage, result.usage)
            self.assertEqual(manifest["source_sessions"], result.sessions)
            self.assertEqual(manifest["message_count"], len(result.messages))

    def test_generated_chat_is_readable_by_wcb_usage_and_tool_parsers(self) -> None:
        try:
            from src.utils.grading import extract_usage_from_jsonl
        except ModuleNotFoundError as exc:
            if exc.name == "dotenv":
                self.skipTest("python-dotenv is unavailable in the base interpreter")
            raise
        from src.utils.tool_metrics import _load_tool_pairs

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = write_conversion(FIXTURE_ROOT, output_dir)
            chat_path = output_dir / "chat.jsonl"

            parsed_usage = extract_usage_from_jsonl(chat_path)
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
                "cost_usd",
                "request_count",
            ):
                self.assertEqual(parsed_usage[field], result.usage[field])
            self.assertEqual(
                [(name, status) for name, _content, status in _load_tool_pairs(chat_path)],
                [
                    ("bash", "completed"),
                    ("custom_tool", "error"),
                    ("child_tool", "error"),
                ],
            )

    def test_convert_sessions_rejects_malformed_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / "session.jsonl"
            session_file.write_text(
                '{"type":"session","version":0,"id":"bad","createdAt":1}\n'
                "{not-json}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DshSessionFormatError, "line 2"):
                convert_sessions(Path(temp_dir))

    def test_convert_sessions_rejects_missing_session_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / "session.jsonl"
            session_file.write_text(
                '{"type":"user/message","data":{"content":[]}}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DshSessionFormatError, "session header"):
                convert_sessions(Path(temp_dir))

    def test_convert_sessions_rejects_direct_compressed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            compressed_file = Path(temp_dir) / "session.jsonl.zst"
            compressed_file.write_bytes(b"not a decompressed jsonl stream")

            with self.assertRaisesRegex(DshSessionFormatError, "compressed session"):
                convert_sessions(compressed_file)

    def test_convert_sessions_rejects_negative_header_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / "session.jsonl"
            session_file.write_text(
                '{"type":"session","version":0,"id":"bad","createdAt":-1}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DshSessionFormatError, "createdAt"):
                convert_sessions(Path(temp_dir))


if __name__ == "__main__":
    unittest.main()
