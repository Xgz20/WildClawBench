from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.agents.mimocode.transcript import (
    MiMoCodeTraceFormatError,
    convert_trace,
    write_conversion,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mimocode" / "trace.jsonl"


class MiMoCodeTranscriptTests(unittest.TestCase):
    def test_convert_trace_maps_text_tool_and_usage(self) -> None:
        result = convert_trace(FIXTURE, prompt="Solve it", exit_code=0)
        self.assertEqual(result.messages[0]["message"]["role"], "user")
        self.assertTrue(result.source["terminal_complete"])
        self.assertEqual(result.source["tool_use_count"], 1)
        self.assertEqual(result.usage["input_tokens"], 10)
        self.assertEqual(result.usage["output_tokens"], 6)
        self.assertEqual(result.usage["reasoning_tokens"], 2)
        self.assertEqual(result.usage["total_tokens"], 20)
        self.assertEqual(result.usage["provider_total_tokens"], 20)
        self.assertEqual(result.usage["request_count"], 1)
        self.assertEqual(result.usage["usage_source"], "mimocode_step_finish")

    def test_write_conversion_is_readable_by_wcb_parsers(self) -> None:
        from src.utils.grading import extract_usage_from_jsonl
        from src.utils.tool_metrics import (
            _load_tool_pairs,
            parse_report_tool_metrics,
            parse_tool_metrics,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            result = write_conversion(FIXTURE, output, prompt="Solve it", exit_code=0)
            self.assertEqual(
                extract_usage_from_jsonl(output / "chat.jsonl")["total_tokens"],
                result.usage["total_tokens"],
            )
            self.assertEqual(
                _load_tool_pairs(output / "chat.jsonl"),
                [("bash", "README.md\n", "completed")],
            )
            self.assertEqual(
                parse_tool_metrics(output / "chat.jsonl", "mimocode")["success"], 1
            )
            self.assertEqual(
                parse_report_tool_metrics(output / "chat.jsonl", "mimocode")["success"],
                1,
            )
            manifest = json.loads(
                (output / "conversion_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_format"], "mimocode-run-json-v1")

    def test_rejects_missing_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            path.write_text(
                '{"type":"text","sessionID":"session-1","part":{"id":"text-1","text":"x"}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MiMoCodeTraceFormatError, "did not complete"):
                convert_trace(path)
            self.assertFalse(
                convert_trace(path, allow_incomplete=True).source["terminal_complete"]
            )

    def convert_rows(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return convert_trace(path, **kwargs)

    def rows(self):
        return [json.loads(line) for line in FIXTURE.read_text().splitlines()]

    def test_zero_exit_with_native_error_is_not_success(self):
        rows = self.rows() + [
            {
                "type": "error",
                "sessionID": "session-1",
                "error": {"name": "APIError", "data": {"message": "401 Unauthorized"}},
            }
        ]
        with self.assertRaisesRegex(MiMoCodeTraceFormatError, "did not complete"):
            self.convert_rows(rows, exit_code=0)
        result = self.convert_rows(rows, exit_code=0, allow_incomplete=True)
        self.assertEqual(result.terminal_result["status"], "failed")
        self.assertFalse(result.usage["usage_complete"])

    def test_tool_calls_finish_is_not_terminal_success(self):
        rows = self.rows()
        rows[-1]["part"]["reason"] = "tool-calls"
        with self.assertRaisesRegex(MiMoCodeTraceFormatError, "did not complete"):
            self.convert_rows(rows, exit_code=0)

    def test_timeout_preserves_partial_usage(self):
        result = convert_trace(FIXTURE, exit_code=124, allow_incomplete=True)
        self.assertEqual(result.terminal_result["status"], "timeout")
        self.assertFalse(result.usage["usage_complete"])
        self.assertEqual(result.usage["total_tokens"], 20)

    def test_duplicate_part_does_not_duplicate_usage_or_tools(self):
        rows = self.rows()
        result = self.convert_rows(rows + [rows[3], rows[-1]], exit_code=0)
        self.assertEqual(result.usage["request_count"], 1)
        self.assertEqual(result.source["tool_use_count"], 1)

    def test_rejects_mixed_sessions_and_negative_usage(self):
        rows = self.rows()
        rows[-1]["sessionID"] = "another-session"
        with self.assertRaisesRegex(MiMoCodeTraceFormatError, "sessionID changed"):
            self.convert_rows(rows, exit_code=0)
        rows = self.rows()
        rows[-1]["part"]["tokens"]["input"] = -1
        with self.assertRaisesRegex(MiMoCodeTraceFormatError, "non-negative"):
            self.convert_rows(rows, exit_code=0)

    def test_absent_provider_total_is_unknown_not_input_plus_output(self):
        rows = self.rows()
        del rows[-1]["part"]["tokens"]["total"]
        result = self.convert_rows(rows, exit_code=0)
        self.assertIsNone(result.usage["provider_total_tokens"])
        self.assertEqual(result.usage["total_tokens"], 20)

    def test_nonzero_bash_exit_is_tool_failure(self):
        rows = self.rows()
        rows[3]["part"]["state"]["metadata"] = {"exit": 1}
        result = self.convert_rows(rows, exit_code=0)
        results = [
            b
            for m in result.messages
            for b in m["message"]["content"]
            if b["type"] == "tool_result"
        ]
        self.assertEqual(results[0]["status"], "error")

    def test_native_database_adds_descendants_but_not_unrelated_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mimocode.db"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE session (id TEXT, parent_id TEXT)")
                db.execute(
                    "CREATE TABLE part (id TEXT, session_id TEXT, time_created INTEGER, data TEXT)"
                )
                db.executemany(
                    "INSERT INTO session VALUES (?,?)",
                    [("session-1", None), ("child-1", "session-1"), ("other", None)],
                )
                for sid in ("session-1", "child-1", "other"):
                    for index, row in enumerate(self.rows()):
                        db.execute(
                            "INSERT INTO part VALUES (?,?,?,?)",
                            (
                                sid + row["part"]["id"],
                                sid,
                                index,
                                json.dumps(row["part"]),
                            ),
                        )
            result = convert_trace(FIXTURE, exit_code=0, database_path=path)
            self.assertEqual(result.usage["total_tokens"], 40)
            self.assertEqual(result.usage["request_count"], 2)
            self.assertEqual(result.usage["session_count"], 2)
            self.assertEqual(
                result.usage["usage_scope"], "session_tree_completed_steps"
            )
            self.assertTrue(result.usage["usage_complete"])
            self.assertEqual(
                result.source["native_database"]["other_root_session_count"], 1
            )
            # Only usage is aggregated; child replies must not become the root answer.
            self.assertEqual(result.source["tool_use_count"], 1)
            with sqlite3.connect(path) as db:
                db.execute(
                    "INSERT INTO part VALUES (?,?,?,?)",
                    ("pending-child", "child-1", 9, json.dumps({"type": "step-start"})),
                )
            self.assertFalse(
                convert_trace(FIXTURE, exit_code=0, database_path=path).usage[
                    "usage_complete"
                ]
            )


if __name__ == "__main__":
    unittest.main()
