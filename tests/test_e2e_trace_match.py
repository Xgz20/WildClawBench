from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval_e2e.trace_match import (
    find_trace,
    parse_usage,
    read_session_meta,
)


def _write_trace(root: Path, name: str, cwd: str, ts: str, extra=()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    rows = [{"timestamp": ts, "type": "session_meta",
             "payload": {"cwd": cwd, "timestamp": ts}}]
    rows.extend(extra)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


class ReadSessionMetaTest(unittest.TestCase):
    def test_reads_cwd_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_trace(Path(tmp), "a.jsonl", "/x/tmp_workspace",
                             "2026-08-10T12:00:00.000Z")
            got = read_session_meta(p)
        self.assertIsNotNone(got)
        self.assertEqual(got.cwd, "/x/tmp_workspace")
        self.assertEqual(got.timestamp, "2026-08-10T12:00:00.000Z")

    def test_returns_none_for_malformed_first_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.jsonl"
            p.write_text("not json\n", encoding="utf-8")
            self.assertIsNone(read_session_meta(p))

    def test_returns_none_when_first_line_is_not_session_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.jsonl"
            p.write_text(json.dumps({"type": "message"}) + "\n", encoding="utf-8")
            self.assertIsNone(read_session_meta(p))


class FindTraceTest(unittest.TestCase):
    def test_matches_by_cwd_and_time_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            want = _write_trace(root, "hit.jsonl", str(proj),
                                "2026-08-10T12:05:00.000Z")
            _write_trace(root, "other_cwd.jsonl", "/y/tmp_workspace",
                         "2026-08-10T12:05:00.000Z")
            _write_trace(root, "out_of_window.jsonl", str(proj),
                         "2026-08-09T12:05:00.000Z")
            got, note = find_trace(root, proj,
                                   "2026-08-10T12:00:00.000Z",
                                   "2026-08-10T12:10:00.000Z")
        self.assertEqual(got, want)
        self.assertEqual(note, "matched")

    def test_returns_none_when_no_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            root.mkdir(parents=True)
            got, note = find_trace(root, Path("/x/tmp_workspace"), "", "")
        self.assertIsNone(got)
        self.assertEqual(note, "trace_missing")

    def test_picks_latest_when_multiple_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            _write_trace(root, "early.jsonl", str(proj),
                         "2026-08-10T12:01:00.000Z")
            latest = _write_trace(root, "late.jsonl", str(proj),
                                  "2026-08-10T12:09:00.000Z")
            got, note = find_trace(root, proj, "", "")
        self.assertEqual(got, latest)
        self.assertEqual(note, "matched_multiple")

    def test_missing_trace_root_reports_explicitly(self) -> None:
        got, note = find_trace(Path("/definitely/not/here"),
                               Path("/x/tmp_workspace"), "", "")
        self.assertIsNone(got)
        self.assertEqual(note, "trace_root_missing")

    def test_empty_window_bounds_do_not_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            want = _write_trace(root, "a.jsonl", str(proj),
                                "1999-01-01T00:00:00.000Z")
            got, _ = find_trace(root, proj, "", "")
        self.assertEqual(got, want)


class ParseUsageTest(unittest.TestCase):
    def test_counts_tool_calls_and_tokens(self) -> None:
        extra = [
            {"type": "function_call", "payload": {"name": "shell"}},
            {"type": "function_call", "payload": {"name": "shell"}},
            {"type": "token_count", "payload": {"total_token_usage": {
                "input_tokens": 100, "output_tokens": 20,
                "cached_input_tokens": 5, "total_tokens": 120}}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_trace(Path(tmp), "a.jsonl", "/x", "2026-08-10T12:00:00Z", extra)
            got = parse_usage(p)
        self.assertEqual(got["tool_calls"], 2)
        self.assertEqual(got["input_tokens"], 100)
        self.assertEqual(got["output_tokens"], 20)
        self.assertEqual(got["cache_read_tokens"], 5)
        self.assertEqual(got["total_tokens"], 120)

    def test_returns_zeros_for_missing_file(self) -> None:
        got = parse_usage(Path("/nope/x.jsonl"))
        self.assertEqual(got["tool_calls"], 0)
        self.assertEqual(got["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
