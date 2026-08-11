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

    def test_offset_timestamp_inside_utc_window_matches(self) -> None:
        # +08:00 的 20:05 即 12:05Z，落在 UTC 窗 [12:00Z, 12:10Z] 内，应匹配。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            want = _write_trace(root, "hit.jsonl", str(proj),
                                "2026-08-10T20:05:00+08:00")
            got, note = find_trace(root, proj,
                                   "2026-08-10T12:00:00.000Z",
                                   "2026-08-10T12:10:00.000Z")
        self.assertEqual(got, want)
        self.assertEqual(note, "matched")

    def test_mixed_precision_timestamp_and_bounds(self) -> None:
        # 带毫秒事件与不带毫秒的窗口边界比较，行为正确。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            inside = _write_trace(root, "inside.jsonl", str(proj),
                                  "2026-08-10T12:05:00.500Z")
            _write_trace(root, "before.jsonl", str(proj),
                         "2026-08-10T11:59:59.999Z")
            got, note = find_trace(root, proj,
                                   "2026-08-10T12:00:00Z",
                                   "2026-08-10T12:10:00Z")
        self.assertEqual(got, inside)
        self.assertEqual(note, "matched")

    def test_latest_across_offset_and_z_uses_real_instant(self) -> None:
        # 一个写 +08:00 一个写 Z，取最新须按真实时刻：
        # 19:00+08:00 = 11:00Z（较早），12:00Z（较晚）→ 应取后者。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            _write_trace(root, "offset_early.jsonl", str(proj),
                         "2026-08-10T19:00:00+08:00")
            later = _write_trace(root, "utc_late.jsonl", str(proj),
                                 "2026-08-10T12:00:00Z")
            got, note = find_trace(root, proj, "", "")
        self.assertEqual(got, later)
        self.assertEqual(note, "matched_multiple")

    def test_ancestor_cwd_does_not_match(self) -> None:
        # 会话开在项目目录上层（工作区根），不应被错算给用例。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            _write_trace(root, "root_open.jsonl", "/work/eval",
                         "2026-08-10T12:05:00.000Z")
            got, note = find_trace(root, Path("/work/eval/task_alpha"), "", "")
        self.assertIsNone(got)
        self.assertEqual(note, "trace_missing")

    def test_descendant_cwd_matches(self) -> None:
        # 会话 cwd 在项目目录子目录内（打开后 cd 进子目录），应匹配。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/work/eval/task_alpha")
            want = _write_trace(root, "sub.jsonl", "/work/eval/task_alpha/src",
                                "2026-08-10T12:05:00.000Z")
            got, note = find_trace(root, proj, "", "")
        self.assertEqual(got, want)
        self.assertEqual(note, "matched")


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
